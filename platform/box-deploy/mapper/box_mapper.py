#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标准 KubeEdge DMI 多协议 mapper（Modbus RTU / Modbus TCP / OPC-UA / LoRaWAN / 5G）。

链路：仪表/DCS --(RS485 串口 / 以太网 / LoRa 无线 / 5G 蜂窝)--> 本 mapper
      实时双源上行（互相独立、任一可用平台即可取数）：
        A. gRPC(dmi.sock) --> edgecore(deviceTwin/DMI) --> CloudHub(10002) --> 云端 CloudCore --> K3s Device.status.twins
        B. MQTT 实时发布 data/# --> 云端 Broker(41883) --> 平台订阅（毫秒级直报，paho 自动重连）
      云边断连数据不丢：本地 SQLite 缓存，恢复后 MQTT 带真实时间戳回填历史 + DMI 补最新值

特性：
  * 多设备并行采集：config.json 的 devices 数组，每设备独立 协议/周期/点位，互不阻塞
  * 协议：
      - modbus-rtu   ：RS485 串口（termios 直驱，无需 pyserial）
      - modbus-tcp   ：以太网（MBAP + 功能码 0x03 读保持寄存器）
      - opcua        ：以太网（asyncua，需离线装 wheel；未安装时该设备自动告警跳过）
      - lora         ：LoRaWAN（多从站轮询：逐站下发 Modbus 问帧、按站号收应答）
      - cellular     ：5G/4G 模块自监控（AT 命令采信号/ICCID/注册态 + 蜂窝接口计数差分算速率）
  * 实时双源：DMI twins + MQTT data/# 独立直报，任一通道可用平台即可拿到实时数据
  * 自愈：DMI 健康检查周期性重注册，edgecore/CloudHub 重启、dmi.sock 重建后自动恢复
    （盒子运行期无 IP、无法远程运维，全自动恢复不依赖人工干预）
  * 云边协同：本地 SQLite 缓存 + 断点续传（MQTT 带真实时间戳回填历史 + DMI 补最新值），成功才删缓存
  * 断连补传守护线程：与设备采集解耦，云边恢复后自动补传历史缓存（即使采集线程异常也不丢数据）
  * 应用/模型部署：订阅 cmd/{box}/# 命令主题，支持云端下发部署模型/服务
    （model 仅下载存储；service 下载并启动后台进程），周期上报运行服务列表到 state/{box}/services
  * 兼容旧单设备配置：config.json 无 devices 数组时，顶层 serial/modbus/deviceName 自动转单设备

配置：/opt/weight-bridge/config.json（可编辑，改完重启服务生效），格式见 box-deploy/README.md
"""
import os
import re
import sys
import json
import time
import struct
import socket
import shutil
import subprocess
import threading
import sqlite3
import fcntl
import termios
import select
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor

try:
    import grpc
    import api_pb2 as pb
    import api_pb2_grpc as pb_grpc
    from google.protobuf import any_pb2
    from google.protobuf import wrappers_pb2
except ImportError as e:
    print("[error] 缺少 gRPC 依赖: %s（请先执行 deploy_box.sh --deps-only）" % e)
    sys.exit(1)

# OPC-UA 可选：asyncua 未安装时 opcua 设备自动跳过（不影响其他协议）
try:
    import asyncio
    from asyncua import Client as OPCUAClient
    _ASYNCUA_OK = True
except Exception:
    _ASYNCUA_OK = False

# paho-mqtt 可选：云边协同 MQTT 断点续传通道，缺失时降级为仅 DMI 补传
try:
    import paho.mqtt.client as _paho
    _PAHO_OK = True
except Exception:
    _paho = None
    _PAHO_OK = False

# Any type_url -> 解包 message class
_ANY_WRAPPERS = {
    "type.googleapis.com/google.protobuf.StringValue": wrappers_pb2.StringValue,
    "type.googleapis.com/google.protobuf.Int32Value": wrappers_pb2.Int32Value,
    "type.googleapis.com/google.protobuf.Int64Value": wrappers_pb2.Int64Value,
    "type.googleapis.com/google.protobuf.FloatValue": wrappers_pb2.FloatValue,
    "type.googleapis.com/google.protobuf.DoubleValue": wrappers_pb2.DoubleValue,
    "type.googleapis.com/google.protobuf.BoolValue": wrappers_pb2.BoolValue,
    "type.googleapis.com/google.protobuf.BytesValue": wrappers_pb2.BytesValue,
}


def _unwrap_any(v):
    """v1.20 edgecore 的 dataToAny 将 string/int/float/bool 编码为 google.protobuf.Any。
    解包为可打印标量（仅用于日志）。"""
    if not isinstance(v, any_pb2.Any):
        return v
    cls = _ANY_WRAPPERS.get(v.type_url)
    if cls is None:
        return str(v)
    msg = cls()
    v.Unpack(msg)
    return msg.value


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/opt/weight-bridge/config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()
DMI_SOCKET = os.environ.get("DMI_SOCKET", CFG.get("dmiSocket", "/etc/kubeedge/dmi.sock"))
MAPPER_SOCKET = os.environ.get("MAPPER_SOCKET", CFG.get("mapperSocket", "/tmp/box-mapper.sock"))
MAPPER_NAME = CFG.get("mapperName", "nengtan-multi-mapper")
MAPPER_VERSION = CFG.get("mapperVersion", "1.3.0")
API_VERSION = CFG.get("apiVersion", "v1beta1")
# 统一协议注册名：必须与云端 Device YAML 的 protocol.protocolName 一致（平台统一为 nengtan-iot）
MAPPER_PROTOCOL = CFG.get("protocol", "nengtan-iot")
DEVICE_NAMESPACE = CFG.get("deviceNamespace", "default")

# 云边协同：本地缓存 + 断点续传
CACHE_CFG = CFG.get("cache", {}) if isinstance(CFG.get("cache"), dict) else {}
CACHE_DB = os.environ.get("CACHE_DB", CACHE_CFG.get("db", "/opt/weight-bridge/twin_cache.db"))
CACHE_MAX = int(os.environ.get("CACHE_MAX", CACHE_CFG.get("max", 200000)))
CACHE_FLUSH_BATCH = int(os.environ.get("CACHE_FLUSH_BATCH", CACHE_CFG.get("flushBatch", 100)))

# MQTT 补传 + 实时双源直报通道
MQTT_CFG = CFG.get("mqtt", {}) if isinstance(CFG.get("mqtt"), dict) else {}
# 默认启用：只要配置了 broker 地址且 paho 可用即启用（无需显式 enabled:true），
# 显式 enabled:false 才禁用。保证盒子在任意情况下都主动尝试连接云端。
MQTT_ENABLED = _PAHO_OK and (MQTT_CFG.get("enabled", True) is not False) and bool(
    (MQTT_CFG.get("broker") or {}).get("host") or (MQTT_CFG.get("broker") or {}).get("port"))
MQTT_BROKER = MQTT_CFG.get("broker", {}) if isinstance(MQTT_CFG.get("broker"), dict) else {}
MQTT_BOX = MQTT_CFG.get("boxId") or CFG.get("node", "box-nt001")
MQTT_TOPIC_TPL = MQTT_CFG.get("topic", "data/{box}/{device}/{instance}/{property}")

# 命令主题（云端/平台 -> 盒子下发）：订阅 cmd/{box}/#，回报 state/{box}/deploy
MQTT_CMD_TOPIC = MQTT_CFG.get("cmdTopic", "cmd/{box}/#")
MQTT_CMD_ACK_TOPIC = MQTT_CFG.get("cmdAckTopic", "state/{box}/deploy")
# 运行服务状态周期上报主题（平台盒子卡片展示用）
MQTT_SERVICES_TOPIC = MQTT_CFG.get("servicesTopic", "state/{box}/services")
# 生效配置摘要上报主题（三端配置一致性校验：指纹/版本/设备清单）
MQTT_CONFIG_TOPIC = MQTT_CFG.get("configTopic", "state/{box}/config")

# 云端部署的应用/模型安装根目录（子目录 = 应用名）
APP_ROOT = os.environ.get("APP_ROOT", CFG.get("apps", {}).get("dir", "/opt/box-apps"))
# 服务状态上报间隔（秒）
SERVICES_INTERVAL = int(os.environ.get("SERVICES_INTERVAL", 30))

# DMI 健康检查间隔：edgecore/CloudHub 重启、dmi.sock 重建后自动重新注册
# （盒子运行期无 IP、无法远程运维，必须全自动自愈，不依赖人工干预）
HEALTH_INTERVAL = int(os.environ.get("HEALTH_INTERVAL", 30))


def _load_devices(cfg):
    """读取设备列表。配置格式唯一：顶层 devices 数组（见 mapper/config.json 模板）。"""
    devs = cfg.get("devices")
    if not isinstance(devs, list) or not devs:
        raise SystemExit(
            "配置错误：%s 缺少非空的 devices 数组（设备列表）。"
            "参考 mapper/config.json 模板，或重新部署：bash deploy_box.sh --mapper" % CONFIG_PATH)
    return devs


def _collectible(devs):
    """可采集设备：enabled=false 的保留在配置里但不采集。

    多设备共总线场景：某台设备暂时不在/待接回时停用，避免它每周期空等超时
    占用总线、拖慢同一串口上的其它设备。
    """
    return [d for d in devs if (d or {}).get("enabled") is not False]


# ---------------------------------------------------------------------------
# 运行期生效配置（唯一真相源）
# ---------------------------------------------------------------------------
# 设计约束：磁盘 config.json、云端下发的配置、采集线程实际使用的配置必须是同一份，
# 绝不允许分叉。历史故障：平台下发写盘成功、但重启没生效，于是磁盘是新配置、
# 内存还是旧配置，表现为「平台显示盒子有这台设备，盒子却根本没在采集它」。
# 做法：所有读取统一经 current_config()/current_devices()；配置变更时
# apply_runtime_config() 原地替换并递增 version，采集线程在健康检查里发现 version
# 变化后按新配置重建 —— 不依赖 systemctl 重启，即使守护方式变了（手动运行/容器内
# 运行/守护进程异常）也能保证「下发即生效」。
_START_TS = time.time()
_RUNTIME_LOCK = threading.Lock()
_RUNTIME = {"version": 0, "cfg": None, "devices": [], "applied_ts": 0.0,
            "fingerprint": "", "source": "file"}

_CONFIG_FP_KEYS = ("name", "protocol", "interval", "enabled", "serial", "tcp", "modbus",
                   "points", "writes", "opcua", "lora", "cellular")


def config_fingerprint(devices):
    """配置指纹：三端（平台期望配置 / 盒子生效配置 / 云端 CRD）一致性校验用。

    只纳入影响采集行为的字段并做稳定序列化，因此同一份配置在任何一端算出的指纹
    都相同；平台下发前后各算一次即可判定盒子是否真的按新配置在跑。

    口径必须是「配置文件内容」而不是「采集集合」：enabled=false 的设备同样要下发、
    同样要留档，也必须能被比对出来。平台侧 mapper_config_fingerprint 与这里一致，
    任一侧擅自过滤设备都会让两端指纹永远对不上（表现为「下发成功但永远不生效」）。
    """
    norm = []
    for d in sorted((devices or []), key=lambda x: str((x or {}).get("name") or "")):
        norm.append({k: (d or {}).get(k) for k in _CONFIG_FP_KEYS})
    s = json.dumps(norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def apply_runtime_config(cfg, source="file"):
    """把配置设为「运行期生效配置」（幂等）：磁盘写入成功后立刻调用，内存即生效。

    返回新的配置版本号；采集线程据此判断是否需要按新配置重建。
    """
    all_devs = _load_devices(cfg)
    devs = _collectible(all_devs)
    with _RUNTIME_LOCK:
        _RUNTIME["cfg"] = cfg
        _RUNTIME["devices"] = devs
        _RUNTIME["version"] += 1
        _RUNTIME["applied_ts"] = time.time()
        # 指纹覆盖配置里全部设备（含 enabled=false）：它与「实际采集集合」是两件事，
        # 用采集集合算指纹会让停用/删除的设备对指纹不可见，平台便无法发现盒子文件残留。
        _RUNTIME["fingerprint"] = config_fingerprint(all_devs)
        _RUNTIME["source"] = source
        return _RUNTIME["version"]


def current_config():
    """当前生效配置（首次调用时从磁盘装载）。"""
    with _RUNTIME_LOCK:
        cfg = _RUNTIME["cfg"]
    if cfg is None:
        apply_runtime_config(load_config(), source="startup")
        with _RUNTIME_LOCK:
            cfg = _RUNTIME["cfg"]
    return cfg


def current_devices():
    """当前生效设备列表（采集线程唯一来源，与平台下发的配置同源）。"""
    current_config()
    with _RUNTIME_LOCK:
        return list(_RUNTIME["devices"])


def config_version():
    with _RUNTIME_LOCK:
        return _RUNTIME["version"]


def reload_runtime_config():
    """重新从磁盘装载配置（外部直接改了 config.json 时用）。"""
    return apply_runtime_config(load_config(), source="reload")


def _served_names(dev):
    """该配置条目实际在采集/上报的「平台设备名」集合。

    多从站透传 DTU：一个条目服务多台设备（lora.polls[].device），平台侧那几台设备
    是各自独立的卡片，因此一致性校验必须把它们都算作「盒子在采集」——
    只报条目名会让平台误判「盒子缺 humid-1」。
    """
    names = [str(dev.get("name") or "")]
    for p in ((dev.get("lora") or {}).get("polls") or []):
        n = str((p or {}).get("device") or "")
        if n and n not in names:
            names.append(n)
    return [n for n in names if n]


def config_state():
    """生效配置摘要：回报平台做三端一致性校验（指纹 + 设备清单 + 版本）。"""
    cfg = current_config()
    with _RUNTIME_LOCK:
        devs = list(_RUNTIME["devices"])
        fp = _RUNTIME["fingerprint"]
        ver = _RUNTIME["version"]
        applied = _RUNTIME["applied_ts"]
        source = _RUNTIME["source"]
    all_devs = cfg.get("devices") or []
    served: List[str] = []
    for d in _collectible(all_devs):
        for n in _served_names(d):
            if n not in served:
                served.append(n)
    return {
        "box": MQTT_BOX,
        "fingerprint": fp,
        "version": ver,
        "source": source,
        "appliedTs": applied,
        "pid": os.getpid(),
        "startedTs": _START_TS,
        "deviceCount": len(devs),
        "configDeviceCount": len(all_devs),
        "disabled": [d.get("name") for d in all_devs if d.get("enabled") is False],
        # 盒子实际在采集/上报的平台设备名（含多从站 DTU 分流出的各台设备）。
        # 平台三端一致性校验以此为准，避免用「配置条目名」漏判被合并的设备。
        "deviceNames": sorted(served),
        "devices": [{
            "name": d.get("name"),
            "protocol": d.get("protocol"),
            "interval": d.get("interval"),
            "enabled": d.get("enabled") is not False,
            "points": len(d.get("points") or []),
            "writes": len(d.get("writes") or []),
            "polls": len((d.get("lora") or {}).get("polls") or []),
            "served": _served_names(d),
        } for d in devs],
        "ts": time.time(),
    }


DISABLED_DEVICES = [d.get("name") for d in (CFG.get("devices") or []) if d.get("enabled") is False]
# 启动时快照（兼容既有模块级引用；后续变更一律以 current_devices() 为准）
DEVICES = current_devices()
if DISABLED_DEVICES:
    print("[info] 已停用设备（enabled=false）: %s" % ", ".join(str(x) for x in DISABLED_DEVICES))


# ---------------------------------------------------------------------------
# Modbus 基础：CRC16 + 寄存器解码
# ---------------------------------------------------------------------------
def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def decode_regs(data: bytes, dtype: str, byte_order: str = "2143"):
    """寄存器字节流 -> 数值。data 为按寄存器顺序拼接的原始字节（每寄存器 2 字节大端）。

    字节数不足（总线丢帧把响应截断）返回 None 而不是抛 struct.error：异常会让
    整台设备本拍数据全部作废（表现为设备在线但读数长期停更），返回 None 只丢该点位。
    另：'int'/'uint' 是歧义类型，字长按实际字节数推断（1 寄存器=16 位 / 2=32 位 /
    4=64 位），兼容历史上未按寄存器数量具体化的点位配置。
    """
    dtype = (dtype or "float32").lower()
    bo = (byte_order or "2143").upper()
    n = len(data)
    if dtype in ("float32", "float", "real"):
        if n < 4:
            return None
        b = data[0:4]
        if bo == "2143":
            b = b[1:2] + b[0:1] + b[3:4] + b[2:3]
        elif bo == "3412":
            b = b[2:4] + b[0:2]
        elif bo == "4321":
            b = b[::-1]
        return struct.unpack(">f", b)[0]
    if dtype in ("int", "uint"):
        signed = dtype == "int"
        if n >= 8:
            return struct.unpack(">q" if signed else ">Q", data[0:8])[0]
        if n >= 4:
            return struct.unpack(">i" if signed else ">I", data[0:4])[0]
        if n >= 2:
            return struct.unpack(">h" if signed else ">H", data[0:2])[0]
        return None
    if dtype in ("int16", "short"):
        return struct.unpack(">h", data[0:2])[0] if n >= 2 else None
    if dtype in ("uint16", "ushort", "word"):
        return struct.unpack(">H", data[0:2])[0] if n >= 2 else None
    if dtype in ("int32",):
        return struct.unpack(">i", data[0:4])[0] if n >= 4 else None
    if dtype in ("uint32", "dword"):
        return struct.unpack(">I", data[0:4])[0] if n >= 4 else None
    if dtype in ("int64", "long"):
        return struct.unpack(">q", data[0:8])[0] if n >= 8 else None
    if dtype in ("uint64", "ulong"):
        return struct.unpack(">Q", data[0:8])[0] if n >= 8 else None
    raise ValueError("未知数据类型: %s" % dtype)


# ---------------------------------------------------------------------------
# 串口底层（termios，无需 pyserial）
# ---------------------------------------------------------------------------
class SimpleSerial:
    def __init__(self, port, baud, data, parity, stop):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, fl & ~os.O_NONBLOCK)
        attr = termios.tcgetattr(self.fd)
        iflag = attr[0]
        iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                   termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        attr[0] = iflag
        attr[1] = 0  # oflag
        lflag = attr[3]
        lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        attr[3] = lflag
        attr[4] = termios.CLOCAL | termios.CREAD
        if data == 5:
            attr[4] |= termios.CS5
        elif data == 6:
            attr[4] |= termios.CS6
        elif data == 7:
            attr[4] |= termios.CS7
        else:
            attr[4] |= termios.CS8
        if parity == "E":
            attr[4] |= termios.PARENB
        elif parity == "O":
            attr[4] |= termios.PARENB | termios.PARODD
        if stop == 2:
            attr[4] |= termios.CSTOPB
        baud_map = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800,
                    9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
                    57600: termios.B57600, 115200: termios.B115200}
        attr[4] = baud_map.get(baud, termios.B9600)  # ispeed
        attr[5] = baud_map.get(baud, termios.B9600)  # ospeed
        attr[6][termios.VMIN] = 0
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        self._set_lines(False, False)
        time.sleep(0.05)
        self._set_lines(True, True)
        time.sleep(0.05)
        self._set_lines(False, False)
        time.sleep(0.05)

    def _set_lines(self, dtr: bool, rts: bool):
        try:
            status = termios.TIOCM_DTR if dtr else 0
            status |= termios.TIOCM_RTS if rts else 0
            fcntl.ioctl(self.fd, termios.TIOCMSET, struct.pack("I", status))
        except Exception:
            pass

    def write(self, data: bytes):
        self._set_lines(False, True)
        time.sleep(0.001)
        os.write(self.fd, data)
        termios.tcdrain(self.fd)
        time.sleep(0.001)
        self._set_lines(False, False)

    def drain(self):
        """丢弃接收缓冲里的残留字节（上一条请求的迟到响应/总线噪声）。

        同一串口挂多台设备时必须先清残留，否则会读到上一台的应答造成串数据。
        """
        try:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass
        while True:
            try:
                ready, _, _ = select.select([self.fd], [], [], 0.02)
            except Exception:
                break
            if not ready:
                break
            try:
                if not os.read(self.fd, 512):
                    break
            except OSError:
                break

    def read(self, n: int, timeout: float) -> bytes:
        buf = b""
        deadline = time.time() + timeout
        while len(buf) < n and time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], max(0, deadline - time.time()))
            if ready:
                chunk = os.read(self.fd, n - len(buf))
                if chunk:
                    buf += chunk
        return buf

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def modbus_read_regs_rtu(ser: SimpleSerial, slave: int, addr: int, count: int, fc: int = 0x03) -> bytes:
    """Modbus RTU 读寄存器：fc=0x03 保持寄存器 / 0x04 输入寄存器，返回寄存器原始字节。

    每次发送前清空接收缓冲：同一串口挂多台设备时，若不清残留，
    会读到上一条请求的迟到响应（典型症状："响应太短 7/9"、串数据）。
    """
    ser.drain()
    req = struct.pack(">BBHH", slave, fc, addr, count)
    req += struct.pack("<H", modbus_crc(req))
    time.sleep(0.004)
    ser.write(req)
    time.sleep(0.05)
    expected = 5 + count * 2
    resp = ser.read(expected, timeout=1.0)
    if len(resp) < expected:
        extra = ser.read(expected - len(resp), timeout=0.5)
        if extra:
            resp += extra
    if len(resp) < expected:
        raise IOError("响应太短: %d/%d bytes" % (len(resp), expected))
    if resp[0] != slave:
        raise IOError("从站号不符(%d)" % resp[0])
    if resp[1] == (fc | 0x80):
        raise IOError("从站异常码 0x%02X(原因 %d)" % (resp[1], resp[2] if len(resp) > 2 else -1))
    if resp[1] != fc:
        raise IOError("响应头异常: %s" % resp[:4].hex())
    payload = resp[:-2]
    if modbus_crc(payload) != struct.unpack("<H", resp[-2:])[0]:
        raise IOError("CRC 校验失败")
    data = resp[3:3 + resp[2]]
    if len(data) < count * 2:
        raise IOError("数据长度不足")
    return data


def modbus_read_holding_rtu(ser: SimpleSerial, slave: int, addr: int, count: int) -> bytes:
    """Modbus RTU 读保持寄存器（功能码 0x03）。"""
    return modbus_read_regs_rtu(ser, slave, addr, count, 0x03)


def modbus_write_holding_rtu(ser: SimpleSerial, slave: int, addr: int, value: int):
    """Modbus RTU 写单个保持寄存器（功能码 0x06），返回从站回显的 (地址, 值)。"""
    ser.drain()
    req = struct.pack(">BBHH", slave, 0x06, addr, value & 0xFFFF)
    req += struct.pack("<H", modbus_crc(req))
    time.sleep(0.004)
    ser.write(req)
    resp = ser.read(8, timeout=1.0)
    if len(resp) != 8:
        raise IOError("写寄存器响应异常: %s" % resp.hex())
    if resp[0] != slave:
        raise IOError("从站号不符(%d)" % resp[0])
    if resp[1] & 0x80:
        raise IOError("从站异常码 0x%02X(原因 %d)" % (resp[1], resp[2]))
    if modbus_crc(resp[:-2]) != struct.unpack("<H", resp[-2:])[0]:
        raise IOError("CRC 校验失败")
    return struct.unpack(">HH", resp[2:6])


def modbus_write_coil_rtu(ser: SimpleSerial, slave: int, addr: int, on: bool):
    """Modbus RTU 写单个线圈（功能码 0x05）：on=True 写 FF00 置位，False 写 0000 复位。"""
    ser.drain()
    req = struct.pack(">BBH", slave, 0x05, addr) + (b"\xff\x00" if on else b"\x00\x00")
    req += struct.pack("<H", modbus_crc(req))
    time.sleep(0.004)
    ser.write(req)
    resp = ser.read(8, timeout=1.0)
    if len(resp) != 8:
        raise IOError("写线圈响应异常: %s" % resp.hex())
    if resp[0] != slave:
        raise IOError("从站号不符(%d)" % resp[0])
    if resp[1] & 0x80:
        raise IOError("从站异常码 0x%02X(原因 %d)" % (resp[1], resp[2]))
    if modbus_crc(resp[:-2]) != struct.unpack("<H", resp[-2:])[0]:
        raise IOError("CRC 校验失败")
    return struct.unpack(">HH", resp[2:6])


# ---------------------------------------------------------------------------
# Modbus TCP 底层（MBAP + 0x03）
# ---------------------------------------------------------------------------
class ModbusTcpConn:
    def __init__(self, host, port=502, timeout=3.0):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.sock = None
        self._tid = 0

    def connect(self):
        if self.sock is not None:
            return
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise IOError("连接被对端关闭")
            buf += chunk
        return buf

    def read_holding(self, slave: int, addr: int, count: int) -> bytes:
        self.connect()
        self._tid = (self._tid + 1) & 0xFFFF
        tid = self._tid
        pdu = struct.pack(">BHH", slave, 0x03, addr, count)
        mbap = struct.pack(">HHHB", tid, 0, 1 + len(pdu), 0)  # unit=0，兼容多数 DCS/网关
        self.sock.sendall(mbap + pdu)
        hdr = self._recv_exact(7)  # tid(2) pid(2) len(2) unit(1) fc(1) bc(1)
        if hdr[0:2] != struct.pack(">H", tid):
            raise IOError("事务 ID 不匹配")
        if hdr[6] == 0x83 or hdr[5] == 0x83:
            err = self._recv_exact(1)
            raise IOError("Modbus 异常码 0x%02X" % err[0])
        bytecount = hdr[6]
        if bytecount < count * 2:
            raise IOError("数据长度不足: %d/%d" % (bytecount, count * 2))
        return self._recv_exact(bytecount)


# 同一串口多设备（不同 slaveId）共用锁，避免并发串口读写互相干扰
_PORT_LOCKS = {}
_PORT_LOCKS_GUARD = threading.Lock()


def _port_lock(port):
    with _PORT_LOCKS_GUARD:
        if port not in _PORT_LOCKS:
            _PORT_LOCKS[port] = threading.Lock()
        return _PORT_LOCKS[port]


# 同一串口上挂多台设备（不同 slaveId）时共用一条物理连接：
# 每个 Reader 各自 open 同一 tty 会互相抢收字节（典型症状：间歇性"响应太短"），
# 因此按串口缓存 SimpleSerial 实例，配合 _port_lock 串行化所有读写。
_SERIAL_POOL = {}
_SERIAL_POOL_GUARD = threading.Lock()


def _open_serial(port, serial_cfg):
    return SimpleSerial(
        port,
        int(serial_cfg.get("baudrate", 9600)),
        int(serial_cfg.get("databits", 8)),
        serial_cfg.get("parity", "N"),
        int(serial_cfg.get("stopbits", 1)),
    )


def _shared_serial(port, serial_cfg):
    """取当前共享连接（临时使用，不占引用计数；不存在则创建）。"""
    with _SERIAL_POOL_GUARD:
        ent = _SERIAL_POOL.get(port)
        if ent is None or ent.get("ser") is None:
            ent = {"ser": _open_serial(port, serial_cfg), "refs": 0}
            _SERIAL_POOL[port] = ent
        return ent["ser"]


def _acquire_serial(port, serial_cfg):
    """采集线程登记一个使用者：引用计数 +1，返回共享连接。"""
    with _SERIAL_POOL_GUARD:
        ent = _SERIAL_POOL.get(port)
        if ent is None or ent.get("ser") is None:
            ent = {"ser": _open_serial(port, serial_cfg), "refs": 0}
            _SERIAL_POOL[port] = ent
        ent["refs"] += 1
        return ent["ser"]


def _release_serial(port):
    """释放一个使用者：只有最后一个使用者退出时才真正关闭串口。

    这样单台设备（如已拆掉的仪表）反复超时重连，不会把同一串口上
    其它正常设备的连接也一起重建掉。
    """
    with _SERIAL_POOL_GUARD:
        ent = _SERIAL_POOL.get(port)
        if not ent:
            return
        ent["refs"] = max(0, int(ent.get("refs", 0)) - 1)
        if ent["refs"] > 0:
            return
        ser = ent.get("ser")
        _SERIAL_POOL.pop(port, None)
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass


def _reset_serial(port):
    """强制重建该串口连接（连接损坏如 Bad file descriptor 时使用）。"""
    with _SERIAL_POOL_GUARD:
        ent = _SERIAL_POOL.pop(port, None)
    if ent:
        try:
            (ent.get("ser") or None) and ent["ser"].close()
        except Exception:
            pass


def _write_with_retry(fn, ser, port, serial_cfg, attempts=2):
    """执行写操作并抗丢帧重试，返回 fn(ser) 的结果；全部失败抛最后一次异常。

    485 总线上偶发丢帧会让写响应被截断或串入噪声（典型报错"写寄存器响应异常:
    65xxxxxxxx"），与读路径一致地重试几次可显著降低失败率。

    只有连接级故障（OSError，如串口被拔 / Bad file descriptor）才重建共享连接：
    普通丢帧去 _reset_serial 会把同一串口上其它设备正用的连接一起关掉，导致
    一条总线上"一台写失败、全部跟着掉线"。
    """
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(ser)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt >= attempts:
                break
            if isinstance(e, OSError):
                _reset_serial(port)
                ser = _shared_serial(port, serial_cfg)
            else:
                ser.drain()   # 清掉半截帧/迟到应答，避免重试时读到残留
            time.sleep(0.05)
    raise last_err


# ---------------------------------------------------------------------------
# 三类协议 Reader（统一接口: connect/read_all/close）
# ---------------------------------------------------------------------------
def _scale_point(v, p):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v * float(p.get("scale", 1.0))
    return v


class ModbusRtuReader:
    def __init__(self, d):
        self.serial_cfg = d.get("serial") or {}
        self.modbus_cfg = d.get("modbus") or {}
        self.points = d.get("points", [])
        self.slave = int(self.modbus_cfg.get("slaveId", 1))
        self.port = self.serial_cfg.get("port", "/dev/ttyUSB4")
        self.name = d.get("name") or self.port
        self.ser = None
        self._lock = _port_lock(self.port)

    def connect(self):
        # 同一串口多设备共用连接（避免互相抢收字节），引用计数 +1
        self.ser = _acquire_serial(self.port, self.serial_cfg)

    def read_all(self):
        if self.ser is None:
            self.connect()
        res = {}
        with self._lock:
            # 现取现用共享连接：别台设备异常重建后，这里自动拿到新连接（不留陈旧 fd）
            ser = _shared_serial(self.port, self.serial_cfg)
            errors = []
            for p in self.points:
                # 功能码：点位 fc 优先，其次设备级 modbus.fc，默认 3（保持寄存器）；
                # 4 = 输入寄存器（不少设备把实时读数放在输入寄存器，如数控电源回读电压/电流）
                try:
                    fc = int(p.get("fc") if p.get("fc") is not None
                             else self.modbus_cfg.get("fc", 3))
                except (TypeError, ValueError):
                    fc = 3
                if fc not in (3, 4):
                    fc = 3
                addr = int(p.get("registerAddr", 0))
                cnt = int(p.get("registerCount", 2))
                # 抗总线干扰：同一条 485 总线上多台设备时偶发丢帧，失败自动重试 1 次
                data = None
                last_err = None
                for attempt in (1, 2):
                    try:
                        data = modbus_read_regs_rtu(ser, self.slave, addr, cnt, fc)
                        break
                    except Exception as e:  # noqa: BLE001
                        last_err = e
                        if attempt == 2:
                            break
                        # 连接级故障（串口被拔 / Bad file descriptor）：重建连接再重试
                        if isinstance(e, OSError) and getattr(e, "errno", None) == 9:
                            _reset_serial(self.port)
                            ser = _shared_serial(self.port, self.serial_cfg)
                        time.sleep(0.05)
                if data is None:
                    # 单点丢帧（485 偶发"响应太短"/超时）不能拖垮整台设备：跳过该点，
                    # 其余点位照常上报。否则一个读不稳的点位会让整台设备长时间零数据
                    # （设备仍在云端注册=显示在线，但读数永远停在旧值）。
                    errors.append("%s@%d(fc%d): %s"
                                  % (p.get("property"), addr, fc, last_err))
                    continue
                bo = p.get("byteOrder") or self.modbus_cfg.get("byteOrder", "2143")
                try:
                    v = decode_regs(data, p.get("type", "float32"), bo)
                    res[p.get("property")] = None if v is None else _scale_point(v, p)
                except Exception as e:  # noqa: BLE001
                    # 类型/字节数不匹配（配置写错或响应被截断）只丢该点位
                    errors.append("%s 解码失败: %s" % (p.get("property"), e))
            if errors and not res:
                # 全部点位都失败 = 设备确实掉线/总线不可用，交给上层重连退避
                raise IOError("全部点位读取失败: %s" % "; ".join(errors[:3]))
            if errors:
                print("[warn] [%s] 本拍跳过 %d 个点位: %s"
                      % (self.name, len(errors), "; ".join(errors[:3])))
        return res

    def close(self):
        # 共享连接：异常重连时释放本串口的连接，下次 connect 重建。
        # 仅当池中当前连接仍是自己那条时才释放计数，避免把别台设备刚重建的连接关掉
        # （多设备共串口时，一方频繁重连会把另一方正在用的连接 close 掉，双方一起失败）。
        if self.ser is not None:
            with _SERIAL_POOL_GUARD:
                ent = _SERIAL_POOL.get(self.port)
                mine = bool(ent) and ent.get("ser") is self.ser
            if mine:
                _release_serial(self.port)
            self.ser = None


class ModbusTcpReader:
    def __init__(self, d):
        tcp = d.get("tcp") or {}
        self.conn = ModbusTcpConn(
            tcp.get("host", "127.0.0.1"),
            tcp.get("port", 502),
            tcp.get("timeout", 3.0),
        )
        self.modbus_cfg = d.get("modbus") or {}
        self.points = d.get("points", [])
        self.slave = int(self.modbus_cfg.get("slaveId", 1))

    def connect(self):
        self.conn.connect()

    def read_all(self):
        self.conn.connect()
        res = {}
        for p in self.points:
            data = self.conn.read_holding(
                self.slave,
                int(p.get("registerAddr", 0)),
                int(p.get("registerCount", 2)),
            )
            bo = p.get("byteOrder") or self.modbus_cfg.get("byteOrder", "1234")
            v = decode_regs(data, p.get("type", "float32"), bo)
            res[p.get("property")] = None if v is None else _scale_point(v, p)
        return res

    def close(self):
        self.conn.close()


class OpcuaReader:
    """OPC-UA 客户端（asyncua）。read_all 每次建立短连接读全部节点后断开。"""

    def __init__(self, d):
        self.cfg = d.get("opcua") or {}
        self.points = d.get("points", [])

    def connect(self):
        pass  # OPC-UA 短连接，读时即连

    def read_all(self):
        if not _ASYNCUA_OK:
            raise IOError("未安装 asyncua（opcua-asyncio），OPC-UA 设备无法采集")
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._read_all())
        finally:
            loop.close()

    async def _read_all(self):
        client = OPCUAClient(self.cfg.get("url", "opc.tcp://127.0.0.1:4840"))
        if self.cfg.get("username"):
            client.set_user(self.cfg["username"])
        if self.cfg.get("password"):
            client.set_password(self.cfg["password"])
        await client.connect()
        try:
            get_node = getattr(client, "get_node", None)  # 兼容 asyncua 0.9.x / 1.x
            res = {}
            for p in self.points:
                nid = p.get("nodeId")
                if not nid:
                    continue
                node = get_node(nid) if get_node else client.nodes.get(nid)
                val = await node.read_value()
                res[p.get("property")] = _scale_point(val, p)
            return res
        finally:
            await client.disconnect()


# ---------------------------------------------------------------------------
# LoRa 上行原始帧解码（ChirpStack 等 NS 未配 codec 时，由 mapper 直接解帧）
# ---------------------------------------------------------------------------
def _mb_crc16(data):
    """Modbus RTU CRC16（多项式 0xA001，线上低字节在前）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _build_modbus_read_frame(slave, addr, count, fc=3):
    """生成 Modbus RTU 读请求帧（hex 字符串），供 DTU 下行透传使用。

    只给站号/寄存器地址/数量即可，不用自己算 CRC 拼帧——手算 CRC 是现场配置
    最常出错的一步（帧里错一个字节，终端就完全不响应，表现为"设备离线"）。
    """
    body = bytes([int(slave) & 0xFF, int(fc) & 0xFF,
                  (int(addr) >> 8) & 0xFF, int(addr) & 0xFF,
                  (int(count) >> 8) & 0xFF, int(count) & 0xFF])
    crc = _mb_crc16(body)
    return (body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])).hex()


def _decode_modbus_reply(raw, points, decode_cfg=None):
    """解 Modbus RTU 应答帧的数据段 -> {property: 物理值}。

    帧形：站号 功能码 字节数 [数据...] CRC16(2)。识别到标准帧头就剥掉
    「站号+功能码+字节数」和尾部 2 字节 CRC；否则按裸数据段处理（部分
    DTU 透传时已经把帧头摘掉，只给数据）。

    数据段按点位顺序每 2 字节一个 16 位寄存器（大端有符号），可用点的
    regIndex 指定寄存器下标、type=uint16/float32/int32、scale 换算工程量。
    """
    if not raw or not points:
        return {}
    payload = raw
    if len(raw) >= 5 and raw[1] in (1, 2, 3, 4) and raw[2] + 5 == len(raw):
        payload = raw[3:-2]      # 标准应答：剥 站号/功能码/字节数 + 尾部 CRC
    cfg = decode_cfg if isinstance(decode_cfg, dict) else {}
    out = {}
    for i, p in enumerate(points):
        if not isinstance(p, dict):
            continue
        prop = p.get("property")
        if not prop:
            continue
        reg = p.get("regIndex", p.get("offset"))
        off = (int(reg) if reg not in (None, "") else i) * 2
        ptype = str(p.get("type") or "int16").strip().lower()
        wid = 4 if ptype in ("float32", "f32", "uint32", "u32", "int32", "i32") else 2
        if off < 0 or off + wid > len(payload):
            continue
        chunk = payload[off:off + wid]
        endian = str(p.get("endian") or cfg.get("endian") or "big").lower()
        scale = float(p.get("scale", cfg.get("scale", 1)) or 1)
        if ptype in ("float32", "f32"):
            import struct as _struct
            try:
                raw_v = _struct.unpack((">" if endian == "big" else "<") + "f", chunk)[0]
            except Exception:
                continue
            out[prop] = round(raw_v * scale, 6)
            continue
        signed = ptype not in ("uint16", "u16", "uint32", "u32")
        raw_v = int.from_bytes(chunk, endian, signed=signed)
        out[prop] = round(raw_v * scale, 6)
    return out


def _msg_raw_bytes(msg):
    """从 NS 上行 JSON 报文提取 FRMPayload 原始字节。

    兼容各家字段与编码（ChirpStack v4 未配 codec 时 data 为 base64；
    部分 NS 透传为 hex 字符串 / 字节数组）。object/measurements 等
    已解码字典不在此列（那是点位 decode 规则的事）。
    """
    if not isinstance(msg, dict):
        return None
    for k in ("data", "payload", "frmPayload", "raw", "bytes", "b64"):
        v = msg.get(k)
        if v is None or isinstance(v, dict):
            continue
        if isinstance(v, str):
            s = v.strip()
            if not s:
                continue
            if re.fullmatch(r"(?:[0-9A-Fa-f]{2}\s*)+", s):
                try:
                    return bytes.fromhex(re.sub(r"\s+", "", s))
                except Exception:
                    pass
            if re.fullmatch(r"[A-Za-z0-9+/=]+", s) and len(s) % 4 == 0:
                try:
                    return base64.b64decode(s)
                except Exception:
                    pass
        elif isinstance(v, (bytes, bytearray)):
            return bytes(v)
        elif isinstance(v, list) and v and all(isinstance(x, int) for x in v):
            return bytes(int(x) & 0xFF for x in v)
    return None


class LoraReader:
    """LoRaWAN 多从站轮询取数（问-答模型，不是被动上报）。

    读数一律由 mapper 主动下发问帧取得：每拍按 lora.polls 逐站下发各自的 Modbus
    问帧（ChirpStack command/down 或 REST 入队），再等该站的应答帧上行，按站号
    路由解码后缓存，read_all 取用；某站超时未应答就跳过该站，绝不把旧值当实时数据。

    上行订阅（application/{appID}/device/{devEUI}/event/up，外置 NS 网关可用
    lora.topic 覆盖）因此**只用来接应答**，不是"传感器主动上传"的取值通道：
    没有 polls 就没有"问"，上行也无从归属。终端需为 Class C（常开接收窗口，
    下行即时可达）；Class A 只能等终端上行窗口，不在本模型支持范围内。
    """

    _DEFAULT_TOPIC = "application/{applicationID}/device/{devEUI}/event/up"
    # 下行主题：ChirpStack MQTT 入队（外置 NS 网关用 lora.downlink.topic 覆盖）
    _DEFAULT_DOWN_TOPIC = "application/{applicationID}/device/{devEUI}/command/down"

    def __init__(self, d):
        self.cfg = d.get("lora") or {}
        self.name = d.get("name") or "lora"
        self.points = d.get("points", [])
        self.broker = self.cfg.get("broker", "127.0.0.1")
        self.port = int(self.cfg.get("port", 1883) or 1883)
        self.username = str(self.cfg.get("username") or "")
        self.password = str(self.cfg.get("password") or "")
        self.application_id = str(self.cfg.get("applicationID", "+") or "+")
        self.dev_eui = self._norm_eui(self.cfg.get("devEUI", "") or "")
        # 应答有效期：超过该秒数的缓存视为过期不上报（0=不过期）。只用于过滤
        # “本拍没拿到新应答”时残留的旧值，与被动上报无关。
        self.max_age = float(self.cfg.get("maxAge", 0) or 0)   # 秒，0=不过期
        # 多从站透传 DTU：一个 devEUI 下挂多台 485 传感器，用从站号区分。
        # 每拍依次对每个从站下发各自的 Modbus 问帧、按应答的站号路由解码，因此
        # 多台传感器共用一条 LoRa 链路 / 一个 MQTT 连接 / 一个下行队列 —— 不会
        # 出现"多个采集线程抢同一个 DTU 的下行窗口"而互相把对方的应答顶掉。
        self.polls = self._parse_polls(self.cfg.get("polls"))
        self._by_slave = {}      # slave -> {"ts": float, "values": {property: value}}
        self._pending_slave = None   # 本次下发问的是哪个从站（应答不带站号时兜底）
        self.routed = {}         # {平台设备名: {property: value}}，供采集线程分设备上报
        self._topic = self._build_topic(self.cfg.get("topic"))
        self._lock = threading.Lock()
        self._cli = None
        # MQTT 连接就绪事件：connect_async 是异步的，未就绪就 publish 只会入队不发出
        self._conn = threading.Event()

        # 下行（Class C 主动取数）：默认关闭，开启后每拍 read_all 先下发再等新上行
        dl = self.cfg.get("downlink") or {}
        self.dl_enabled = bool(dl.get("enabled", False))
        self.dl_mode = str(dl.get("mode", "poll") or "poll").lower()   # poll（下发后等回传）
        self.dl_topic = str(dl.get("topic") or "").strip()
        self.dl_fport = int(dl.get("fPort", 1) or 1)
        # confirmed 下行会等终端 ACK，主动取数场景一律用 false，避免 ACK 风暴占满下行窗口
        self.dl_confirmed = bool(dl.get("confirmed", False))
        self.dl_data_hex = str(dl.get("hex") or "").strip()      # 下行原始字节（hex，优先）
        self.dl_data_text = str(dl.get("payload") or "")         # 或文本（UTF-8）
        # ChirpStack v4：配了 codec 时可直接下发解码对象（object），由 NS 编码成 data
        self.dl_object = dl.get("object") if isinstance(dl.get("object"), dict) else None
        self.dl_timeout = float(dl.get("timeout", 6.0) or 6.0)   # 下发后等待新上行的秒数
        rest = dl.get("rest") or {}
        self.dl_rest_url = str(rest.get("url") or "").strip()    # 如 http://127.0.0.1:8080/api/devices/{devEUI}/queue
        self.dl_rest_token = str(rest.get("token") or "").strip()
        if self.dl_enabled:
            print("[info] lora %s 主动取数已启用: mode=%s fPort=%s timeout=%.1fs 通道=%s" % (
                self.name, self.dl_mode, self.dl_fport, self.dl_timeout,
                "REST" if self.dl_rest_url else ("MQTT " + self._down_topic(self.dev_eui or "+"))))
        if self.polls:
            print("[info] lora %s 多从站透传模式: %d 个从站 %s" % (
                self.name, len(self.polls),
                "、".join("站%d→%s" % (p["slave"], p["device"] or self.name) for p in self.polls)))
            if not self.dev_eui or self.dev_eui == "+":
                print("[warn] lora %s 配了 polls 多从站却没配 lora.devEUI：无法主动下发取数，"
                      "请补上 DTU 的 devEUI" % self.name)

    # -- 工具 ---------------------------------------------------------------
    @staticmethod
    def _norm_eui(v):
        return str(v or "").strip().lower().replace("-", "").replace(":", "").replace(" ", "")

    def _build_topic(self, tpl):
        """渲染订阅主题：支持 {applicationID}/{appID}、{devEUI} 占位符，空 devEUI 用 +。"""
        tpl = str(tpl or "").strip() or self._DEFAULT_TOPIC
        app = self.application_id or "+"
        eui = self.dev_eui or "+"
        return (tpl.replace("{applicationID}", app).replace("{appID}", app)
                   .replace("{devEUI}", eui).replace("{deveui}", eui)).strip()

    @staticmethod
    def _parse_polls(raw_polls):
        """解析 lora.polls：多从站轮询表。每项字段：

          slave        必填，DTU 后面那台 485 传感器的从站号
          device       必填，读数归属的平台设备名（= 云端 Device/CRD 名）。
                       留空则归到本设备自己名下（等价于单设备）
          hex          下行 Modbus 问帧（hex）。**可省**：省了就按下面三项自动
                       拼帧并算好 CRC，省掉手算 CRC 这个最常见的出错点
          functionCode 读功能码，默认 3（保持寄存器），可用 4（输入寄存器）
          registerAddr 起始寄存器地址，默认 0
          count        读几个寄存器，默认 1
          fPort        该从站专用下行端口，默认沿用 downlink.fPort
          points       该从站的点位（property/type/scale/regIndex...）
          decode       该从站的原始帧解码配置（fields 等）
        """
        out = []
        if not isinstance(raw_polls, list):
            return out
        for i, p in enumerate(raw_polls):
            if not isinstance(p, dict):
                continue
            slave = p.get("slave", p.get("slaveId"))
            if slave in (None, ""):
                print("[warn] lora polls[%d] 缺少 slave（从站号），已跳过" % i)
                continue
            hex_data = str(p.get("hex") or p.get("data") or "").strip()
            if not hex_data:
                hex_data = _build_modbus_read_frame(
                    int(slave), int(p.get("registerAddr", 0) or 0),
                    int(p.get("count", 1) or 1), int(p.get("functionCode", 3) or 3))
            hex_data = re.sub(r"[\s:]+", "", hex_data).lower()
            if len(hex_data) % 2 or not re.fullmatch(r"[0-9a-f]+", hex_data):
                print("[warn] lora polls[%d] 下行 hex 非法: %r，已跳过" % (i, hex_data))
                continue
            out.append({
                "slave": int(slave),
                "hex": hex_data,
                "device": str(p.get("device") or "").strip(),
                "points": p.get("points") or [],
                "decode": p.get("decode") or {},
                "fport": int(p.get("fPort", 0) or 0),
            })
        return out

    # -- MQTT ---------------------------------------------------------------
    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode(errors="replace"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        # 上行只认"本拍问帧的应答"：按站号路由到对应 polls 项缓存，供 _read_polls 取用。
        # 没有 polls 就没有"问"，此时的上行无从归属（读数一律由轮询下发取得），直接忽略。
        if self.polls:
            self._route_uplink(data)

    def _route_uplink(self, data):
        """多从站 DTU 上行路由：把一帧应答归到对应的 polls 项。

        标准 Modbus 应答首字节就是从站号，按它分派；但有些 DTU 透传时会剥掉
        「站号+功能码+字节数」只给数据段，此时首字节是数据，按它匹配会误归到
        站号恰好等于该字节值的另一台。所以先认"本拍正在等的那台"（mapper 是
        一问一答串行下发，收到的上行必然属于刚问的从站），仅当帧是标准应答且
        站号明确不是它时（DTU 主动上报别的站）才改按站号分派。
        """
        raw = _msg_raw_bytes(data)
        if not raw:
            return
        slave = raw[0]
        is_std = len(raw) >= 5 and raw[1] in (1, 2, 3, 4) and raw[2] + 5 == len(raw)
        pending = self._pending_slave
        if pending is not None and (not is_std or slave == pending):
            for poll in self.polls:
                if poll["slave"] == pending:
                    self._cache_slave(poll, raw)
                    return
        for poll in self.polls:
            if poll["slave"] == slave:
                self._cache_slave(poll, raw)
                return

    def _cache_slave(self, poll, raw):
        """按该从站的点位/解码规则解一帧应答并缓存（ts 刷新即视为新数据）。"""
        vals = _decode_modbus_reply(raw, poll["points"], poll["decode"])
        if not vals:
            return
        with self._lock:
            self._by_slave[poll["slave"]] = {"ts": time.time(), "values": vals}

    # -- 下行：Class C 主动取数 ------------------------------------------------
    def _down_topic(self, eui):
        """渲染下行主题，支持 {applicationID}/{devEUI} 占位符。

        默认 ChirpStack 的 command/down；Milesight/RAK 等内置 NS 网关主题各异，
        用 lora.downlink.topic 覆盖（同样支持占位符）。
        """
        tpl = self.dl_topic or self._DEFAULT_DOWN_TOPIC
        app = self.application_id or "+"
        eu = eui or self.dev_eui or "+"
        return (tpl.replace("{applicationID}", app).replace("{appID}", app)
                   .replace("{devEUI}", eu).replace("{deveui}", eu)).strip()

    def _down_payload(self, eui, hex_data=None, fport=None):
        """下行报文（ChirpStack v3/v4 通用 camelCase：devEui/confirmed/fPort/data）。

        配了 object（v4 codec）时直接下发解码对象，由 ChirpStack 编码，此时不带 data。
        hex_data/fport 用于多从站轮询：一个 DTU 下的每个从站各有自己的问帧与端口，
        由调用方逐站传入，不传则沿用 downlink.hex / downlink.fPort 的整机默认值。
        """
        port = int(fport) if fport not in (None, "") else int(self.dl_fport)
        if hex_data is None and self.dl_object:
            return {
                "devEui": eui,
                "confirmed": bool(self.dl_confirmed),
                "fPort": port,
                "object": self.dl_object,
            }
        src = self.dl_data_hex if hex_data is None else str(hex_data)
        if src:
            try:
                raw = bytes.fromhex(re.sub(r"[\s:]+", "", src))
            except ValueError:
                print("[warn] lora %s downlink hex 非法: %s，按空载荷下发" % (self.name, src))
                raw = b""
        elif hex_data is None and self.dl_data_text:
            raw = self.dl_data_text.encode("utf-8")
        else:
            raw = b""   # 空载荷：多数终端把它当作"立即上报一次"
        return {
            "devEui": eui,
            "confirmed": bool(self.dl_confirmed),
            "fPort": port,
            "data": base64.b64encode(raw).decode(),
        }

    def _known_euis(self):
        """已知终端列表：只认配置的 devEUI（上行缓存不再作为节点来源）。"""
        if self.dev_eui and self.dev_eui != "+":
            return [self.dev_eui]
        return []

    def _send_mqtt_down(self, eui, hex_data=None, fport=None):
        topic = self._down_topic(eui)
        # 刚启动 / 断线重连时连接还没就绪：qos=0 的 publish 只入队不发出（返回码
        # MQTT_ERR_NO_CONN），每次重启都会白丢第一拍问帧并刷一条吓人的告警。
        # 等连接就绪再发，等不到就明确说"通道未就绪"，不与"终端没应答"混淆。
        if not self._conn.wait(2.0):
            print("[warn] lora %s 下行通道未就绪（broker %s:%s 未连接），本拍跳过"
                  % (self.name, self.broker, self.port))
            return False
        try:
            info = self._cli.publish(
                topic, json.dumps(self._down_payload(eui, hex_data, fport)), qos=0)
            # qos=0 时 broker 未连接不会抛异常，只体现在返回码上：不检查就会
            # "看着下发成功、实际终端一帧没收到"，表现为设备永远离线却查不出原因。
            rc = getattr(info, "rc", 0)
            if rc != 0:
                print("[warn] lora %s 下行发布失败 rc=%s（broker %s:%s 未连接/主题无权限？）"
                      % (self.name, rc, self.broker, self.port))
                return False
            info.wait_for_publish(0.5)
            return True
        except Exception as e:
            print("[warn] lora %s 下行发布失败 %s: %s" % (self.name, topic, e))
            return False

    def _send_rest_down(self, eui, hex_data=None, fport=None):
        """ChirpStack REST 入队（本地无 MQTT 写权限 / NS 在另一台机器时用）。"""
        try:
            import urllib.request
            url = self.dl_rest_url.format(devEUI=eui, applicationID=self.application_id)
            body = json.dumps({"queueItem": self._down_payload(eui, hex_data, fport)}).encode()
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            if self.dl_rest_token:
                req.add_header("Authorization", "Bearer %s" % self.dl_rest_token)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except Exception as e:
            print("[warn] lora %s 下行 REST 入队失败: %s" % (self.name, e))
            return False

    def send_downlink(self, eui=None, hex_data=None, fport=None):
        """向终端下发一次下行指令（取数请求）。任一通道成功即 True。

        hex_data/fport 用于多从站轮询：逐站下发各自的 Modbus 问帧。
        """
        targets = [eui] if eui else self._known_euis()
        if not targets:
            # 还没收到过任何上行、又没配 devEUI 时无从定位终端，跳过本拍而不是瞎发
            print("[warn] lora %s 尚不知道终端 devEUI（未收到上行且未配置），跳过下发" % self.name)
            return False
        ok = False
        for eu in targets:
            if self.dl_rest_url:
                ok = self._send_rest_down(eu, hex_data, fport) or ok
            elif self._cli is not None:
                ok = self._send_mqtt_down(eu, hex_data, fport) or ok
            else:
                print("[warn] lora %s 下行通道不可用（MQTT 未连接且未配置 rest.url）" % self.name)
        return ok

    def snapshot_values(self):
        """当前缓存里的最新值快照（不触发下行，供命令读取展示）。

        只取轮询应答缓存（_by_slave）；没有 polls 就没有可展示的读数。
        """
        now = time.time()
        with self._lock:
            entries = list(self._by_slave.values())
        vals = {}
        for e in entries:
            if self.max_age > 0 and now - e.get("ts", 0) > self.max_age:
                continue   # 应答过期：不上报，避免把旧值当实时数据
            vals.update(e.get("values", {}))
        return dict(vals)

    def _custom_down(self, eui, hex_data=None, text=None, obj=None, fport=None, confirmed=None):
        """平台「命令执行」自定义下行报文（ChirpStack v3/v4 通用 camelCase）。"""
        base = {
            "devEui": eui,
            "confirmed": bool(self.dl_confirmed if confirmed is None else confirmed),
            "fPort": int(fport) if fport not in (None, "") else int(self.dl_fport),
        }
        if isinstance(obj, dict) and obj:
            base["object"] = obj   # v4 codec 对象：由 ChirpStack 编码，不再带 data
            return base
        if hex_data:
            try:
                raw = bytes.fromhex(str(hex_data).replace(" ", ""))
            except ValueError:
                raise ValueError("hex 非法: %r" % (hex_data,))
        elif text not in (None, ""):
            raw = str(text).encode("utf-8")
        else:
            raise ValueError("下行内容缺失：hex / text / object 至少提供一个")
        base["data"] = base64.b64encode(raw).decode()
        return base

    def send_raw_down(self, hex_data=None, text=None, obj=None, fport=None, eui=None,
                      confirmed=None):
        """向终端发送一次自定义下行（不依赖 downlink.enabled 的轮询载荷）。

        返回 (ok, message)；平台「命令执行」用此做 LoRa 写设定/临时下发。
        """
        targets = [eui] if eui else self._known_euis()
        if not targets:
            return False, "尚不知终端 devEUI（未收到过上行且未配置 devEUI），无法下发"
        sent, errs = 0, []
        for eu in targets:
            try:
                body = self._custom_down(eu, hex_data, text, obj, fport, confirmed)
            except ValueError as e:
                return False, str(e)
            try:
                if self.dl_rest_url:
                    import urllib.request
                    url = self.dl_rest_url.format(devEUI=eu, applicationID=self.application_id)
                    req = urllib.request.Request(
                        url, data=json.dumps({"queueItem": body}).encode(), method="POST",
                        headers={"Content-Type": "application/json"})
                    if self.dl_rest_token:
                        req.add_header("Authorization", "Bearer %s" % self.dl_rest_token)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        ok = 200 <= getattr(resp, "status", 200) < 300
                elif self._cli is not None:
                    topic = self._down_topic(eu)
                    info = self._cli.publish(topic, json.dumps(body), qos=0)
                    info.wait_for_publish(0.5)
                    ok = True
                else:
                    ok = False
                    errs.append("下行通道不可用（MQTT 未连接且未配置 rest.url）")
            except Exception as e:  # noqa: BLE001
                ok = False
                errs.append(str(e))
            if ok:
                sent += 1
        if sent:
            return True, "已向 %d 个终端下发自定义下行" % sent
        return False, "下行发送失败: %s" % ("；".join(errs) or "无可用通道")

    def poll_once(self):
        """主动取数一拍：逐站下发问帧 -> 等待各站应答 -> 合并结果。

        判定"新"的依据是该站应答缓存的时间戳比下发前更新（值没变也会回传，ts 一定刷新）。
        返回 True=本拍拿到新数据；False=超时/无通道，调用方应跳过本拍上报。
        读数一律来自轮询问帧的应答，因此没有 polls 就没有可下发的问帧。
        """
        if not self.polls:
            print("[warn] lora %s 未配置从站问帧（polls），无法轮询取数" % self.name)
            return False
        return bool(self._read_polls())

    def _wait_slave(self, slave, before):
        """等待指定从站的新应答（时间戳比下发前新即视为新帧，值没变也算）。"""
        deadline = time.time() + self.dl_timeout
        while time.time() < deadline:
            time.sleep(0.1)
            with self._lock:
                if (self._by_slave.get(slave) or {}).get("ts", 0) > before + 1e-6:
                    return True
        return False

    def _read_polls(self):
        """多从站透传 DTU 的一拍采集：逐站下发问帧 -> 等该站新应答 -> 按设备分流。

        同一个 devEUI 下的多台 485 传感器串行轮询（半双工 485 本来就只能一答一问），
        某台没答不影响其它台；全部无应答才返回空，采集线程会跳过本拍上报。
        """
        routed, got_any = {}, False
        for poll in self.polls:
            slave = poll["slave"]
            with self._lock:
                before = (self._by_slave.get(slave) or {}).get("ts", 0)
            self._pending_slave = slave
            if not self.send_downlink(hex_data=poll["hex"], fport=poll["fport"] or None):
                continue
            if not self._wait_slave(slave, before):
                # 同拍补发一次：LoRa 上下行本身丢包率高（现场实测单发命中率常只有
                # 30%~60%），补发一条成本极低，命中率可从 p 提升到 1-(1-p)^2，
                # 直接把读数延迟与「设备显示离线」的概率压下去
                with self._lock:
                    before = (self._by_slave.get(slave) or {}).get("ts", 0)
                if not self.send_downlink(hex_data=poll["hex"], fport=poll["fport"] or None):
                    continue
                if not self._wait_slave(slave, before):
                    # 把实际下发的问帧打出来：现场对帧时可直接拿它与 NS/串口助手收到的帧比对
                    # （从站号、寄存器、CRC 任一不符都会「发了但没人答」，只报从站号看不出问题）
                    print("[warn] lora %s 从站%d 下行 %s 后 %.1fs 内无新应答（已补发一次；终端离线 / 下行未达 / 该从站无设备？）"
                          % (self.name, slave, poll.get("hex") or "-", self.dl_timeout))
                    continue
            with self._lock:
                vals = dict((self._by_slave.get(slave) or {}).get("values") or {})
            if not vals:
                continue
            got_any = True
            routed.setdefault(poll["device"] or self.name, {}).update(vals)
        self._pending_slave = None
        self.routed = routed if got_any else {}
        merged = {}
        for sub in self.routed.values():
            merged.update(sub)
        return merged

    def connect(self):
        self.close()
        if not _PAHO_OK:
            raise IOError("未安装 paho-mqtt，LoRaWAN 设备无法订阅")
        # client_id 必须全局唯一：多节点/多设备共用同一 id 会互相踢下线
        cid = "nengtan-lora-%s-%d-%d" % (
            re.sub(r"[^A-Za-z0-9]", "", str(self.name))[:20] or "dev",
            os.getpid(), int(time.time() * 1000) % 100000)
        cli = _paho.Client(client_id=cid)
        if self.username:
            cli.username_pw_set(self.username, self.password or None)
        cli.on_message = self._on_message

        def _on_connect(c, u, f, rc, *a):
            if rc == 0:
                self._conn.set()
                c.subscribe(self._topic)
            else:
                print("[warn] lora %s 连接 broker %s:%s 失败 rc=%s" % (self.name, self.broker, self.port, rc))

        def _on_disconnect(c, u, *a):      # paho 2.x 各回调 API 版本参数个数不同，用 *a 兜底
            self._conn.clear()

        cli.on_connect = _on_connect
        cli.on_disconnect = _on_disconnect
        print("[info] lora %s 订阅 %s:%s 主题 %s" % (self.name, self.broker, self.port, self._topic))
        cli.connect_async(self.broker, self.port, 30)
        cli.loop_start()
        self._cli = cli

    def read_all(self):
        """本拍读数：逐站下发问帧、按站号收应答，再分流到各平台设备。

        读数一律来自轮询下发的应答；没有 polls 就没有问帧可发，返回空由采集线程
        跳过本拍上报（绝不把旧值当实时数据重复上报）。
        """
        if not self.polls:
            print("[warn] lora %s 未配置从站问帧（polls），跳过本拍上报" % self.name)
            return {}
        return self._read_polls()

    def close(self):
        if self._cli is not None:
            try:
                self._cli.loop_stop()
                self._cli.disconnect()
            except Exception:
                pass
            self._cli = None
        self._conn.clear()


# cellular 点位类型 -> (AT 命令, 提取正则)
_CELL_CMDS = {
    "csq":    ("AT+CSQ\r", r"\+CSQ:\s*(\d+)"),                    # 0-31 信号质量
    "signal": ("AT+CSQ\r", r"\+CSQ:\s*(\d+)"),                    # 同 csq
    "rsrp":   ('AT+QENG="servingcell"\r', r'"rsrp",(-?\d+)'),     # 移远 QENG 参考信号功率
    "rsrq":   ('AT+QENG="servingcell"\r', r'"rsrq",(-?\d+)'),
    "sinr":   ('AT+QENG="servingcell"\r', r'"sinr",(-?\d+)'),
    "iccid":  ("AT+ICCID\r", r"\+ICCID:\s*([0-9A-Fa-f]+)"),       # SIM 卡号（字符串）
    "imsi":   ("AT+CIMI\r", r"(\d{5,20})"),                       # 字符串
    "imei":   ("AT+CGSN\r", r"(\d{15,17})"),                      # 字符串
    "reg":    ("AT+CEREG?\r", r"\+CEREG:\s*\d,\s*(\d)"),          # 0 未注册 1 注册 2 搜索 3 拒绝 5 漫游
}


class AtSerial:
    """极简 AT 串口（8N1，不做 DTR/RTS 翻转，适配 4G/5G 模块 AT 口）。"""

    def __init__(self, port, baud=115200):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, fl & ~os.O_NONBLOCK)
        attr = termios.tcgetattr(self.fd)
        iflag = attr[0]
        iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                   termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        attr[0] = iflag
        attr[1] = 0
        lflag = attr[3]
        lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        attr[3] = lflag
        attr[4] = termios.CLOCAL | termios.CREAD | termios.CS8
        baud_map = {9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
                    57600: termios.B57600, 115200: termios.B115200, 230400: termios.B230400}
        attr[4] |= baud_map.get(int(baud), termios.B115200)
        attr[5] = baud_map.get(int(baud), termios.B115200)
        attr[6][termios.VMIN] = 0
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        time.sleep(0.05)

    def cmd(self, text, timeout=2.0):
        try:
            os.write(self.fd, text.encode())
        except OSError:
            return ""
        termios.tcdrain(self.fd)
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], max(0, deadline - time.time()))
            if not ready:
                break
            chunk = os.read(self.fd, 4096)
            if not chunk:
                break
            buf += chunk
            if b"OK" in buf or b"ERROR" in buf:
                break
        return buf.decode(errors="replace").replace("\r", "")

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class CellularReader:
    """5G/4G 模块自监控：把模块当一台设备管，AT 命令采状态 + 蜂窝接口计数差分算速率。"""

    def __init__(self, d):
        self.cfg = d.get("cellular") or {}
        self.points = d.get("points", [])
        self.port = self.cfg.get("serialPort", "/dev/ttyUSB2")
        self.baud = int(self.cfg.get("baudRate", 115200) or 115200)
        self.iface = self.cfg.get("iface", "wwan0")
        self.ser = None
        self._last_cnt = None  # (rx_bytes, tx_bytes, t)

    def connect(self):
        self.close()
        self.ser = AtSerial(self.port, self.baud)

    def _net_counters(self):
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(self.iface + ":"):
                        parts = line.replace(":", " ").split()
                        return int(parts[0]), int(parts[7])  # rx_bytes, tx_bytes
        except Exception:
            pass
        return None

    def _cmd(self, cmd):
        if self.ser is None:
            raise IOError("AT 串口未打开")
        return self.ser.cmd(cmd, timeout=2.0)

    def read_all(self):
        if self.ser is None:
            self.connect()
        res = {}
        cache = {}  # 同一 AT 命令只发一次
        for p in self.points:
            kind = (p.get("kind") or "signal").lower()
            prop = p.get("property")
            if kind in ("tx_rate", "txrate", "rx_rate", "rxrate"):
                continue  # 速率点位单独差分计算
            spec = _CELL_CMDS.get(kind)
            if spec is None:
                continue
            cmd, regex = spec
            if cmd not in cache:
                cache[cmd] = self._cmd(cmd)
            m = re.search(regex, cache[cmd])
            if m:
                raw = m.group(1)
                if kind in ("iccid", "imsi", "imei"):
                    res[prop] = raw  # 卡号类保持字符串（twins 字符串上报）
                else:
                    res[prop] = int(raw) if raw.lstrip("-").isdigit() else raw
        # 上下行速率：/proc/net/dev 计数差分
        cur = self._net_counters()
        if cur and self._last_cnt:
            rx0, tx0, t0 = self._last_cnt
            dt = time.time() - t0
            if dt > 0.5:
                rx_kbps = max(0.0, (cur[0] - rx0) * 8 / dt / 1000)
                tx_kbps = max(0.0, (cur[1] - tx0) * 8 / dt / 1000)
                for p in self.points:
                    kind = (p.get("kind") or "signal").lower()
                    if kind in ("tx_rate", "txrate"):
                        res[p.get("property")] = tx_kbps
                    elif kind in ("rx_rate", "rxrate"):
                        res[p.get("property")] = rx_kbps
        if cur:
            self._last_cnt = (cur[0], cur[1], time.time())
        return res

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None


def _make_reader(d):
    proto = (d.get("protocol") or "modbus-rtu").lower()
    if proto in ("modbus", "modbus-rtu", "rtu"):
        return ModbusRtuReader(d)
    if proto in ("modbus-tcp", "tcp"):
        return ModbusTcpReader(d)
    if proto in ("opcua", "opc-ua", "ua"):
        return OpcuaReader(d)
    if proto in ("lora", "lorawan"):
        return LoraReader(d)
    if proto in ("cellular", "5g", "4g", "lte"):
        return CellularReader(d)
    raise ValueError("未知协议: %s（支持 modbus-rtu / modbus-tcp / opcua / lora / cellular）" % proto)


# ---------------------------------------------------------------------------
# DMI 回调服务（edgecore -> mapper）
# ---------------------------------------------------------------------------
class MapperService(pb_grpc.DeviceMapperServiceServicer):
    def RegisterDevice(self, request, context):
        d = request.device
        print("[dmi] RegisterDevice: %s/%s protocol=%s" % (d.namespace, d.name, d.spec.protocol.protocolName))
        return pb.RegisterDeviceResponse(deviceName=d.name, deviceNamespace=d.namespace)

    def RemoveDevice(self, request, context):
        print("[dmi] RemoveDevice: %s/%s" % (request.deviceNamespace, request.deviceName))
        return pb.RemoveDeviceResponse()

    def UpdateDevice(self, request, context):
        d = request.device
        print("[dmi] UpdateDevice: %s/%s" % (d.namespace, d.name))
        return pb.UpdateDeviceResponse()

    def CreateDeviceModel(self, request, context):
        return pb.CreateDeviceModelResponse(deviceModelName=request.model.name,
                                            deviceModelNamespace=request.model.namespace)

    def RemoveDeviceModel(self, request, context):
        return pb.RemoveDeviceModelResponse()

    def UpdateDeviceModel(self, request, context):
        return pb.UpdateDeviceModelResponse()

    def GetDevice(self, request, context):
        return pb.GetDeviceResponse()


def serve_mapper_service():
    server = grpc.server(thread_pool=ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_DeviceMapperServiceServicer_to_server(MapperService(), server)
    try:
        os.unlink(MAPPER_SOCKET)
    except OSError:
        pass
    server.add_insecure_port("unix://" + MAPPER_SOCKET)
    server.start()
    print("[info] mapper 回调服务监听 %s" % MAPPER_SOCKET)
    return server


# ---------------------------------------------------------------------------
# 云边协同：SQLite 本地缓存 + 断点续传
# ---------------------------------------------------------------------------
_cache_conn = None
_cache_lock = threading.Lock()


def _cache_conn_open():
    global _cache_conn
    if _cache_conn is None:
        os.makedirs(os.path.dirname(CACHE_DB) or ".", exist_ok=True)
        _cache_conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
        _cache_conn.execute(
            "CREATE TABLE IF NOT EXISTS twin_cache ("
            "ts REAL, device TEXT, property TEXT, value REAL, "
            "PRIMARY KEY (ts, device, property))")
        _cache_conn.execute("CREATE INDEX IF NOT EXISTS idx_twin_ts ON twin_cache(ts)")
    return _cache_conn


def cache_count():
    try:
        with _cache_lock:
            return _cache_conn_open().execute("SELECT COUNT(*) FROM twin_cache").fetchone()[0]
    except Exception as e:
        print("[warn] 缓存计数失败: %s" % e)
        return 0


def cache_push(ts, device, prop, value):
    """云边断连时把读数写入本地 SQLite（数据不丢，恢复后补传）。"""
    try:
        with _cache_lock:
            c = _cache_conn_open()
            try:
                fv = float(value)
            except (TypeError, ValueError):
                return  # 字符串值（ICCID/IMSI 等）不入数值缓存，实时链路已上报
            with c:
                c.execute("INSERT OR REPLACE INTO twin_cache (ts, device, property, value) VALUES (?, ?, ?, ?)",
                          (float(ts), device, prop, fv))
                n = c.execute("SELECT COUNT(*) FROM twin_cache").fetchone()[0]
                if n > CACHE_MAX:  # 防无限膨胀：只保留最新 CACHE_MAX 条
                    c.execute(
                        "DELETE FROM twin_cache WHERE rowid IN "
                        "(SELECT rowid FROM twin_cache ORDER BY ts LIMIT ?)",
                        (n - CACHE_MAX,),
                    )
    except Exception as e:
        print("[warn] 本地缓存写入失败: %s" % e)


def cache_peek(limit):
    """取最旧 limit 条（不删除，补传成功才删，保证不丢）。"""
    try:
        with _cache_lock:
            return [(float(t), str(d), str(p), float(v)) for t, d, p, v in
                    _cache_conn_open().execute(
                        "SELECT ts, device, property, value FROM twin_cache ORDER BY ts LIMIT ?",
                        (limit,)).fetchall()]
    except Exception as e:
        print("[warn] 缓存读取失败: %s" % e)
        return []


def cache_remove(rows):
    if not rows:
        return
    try:
        with _cache_lock:
            c = _cache_conn_open()
            with c:
                c.executemany("DELETE FROM twin_cache WHERE ts = ? AND device = ? AND property = ?",
                              [(r[0], r[1], r[2]) for r in rows])
    except Exception as e:
        print("[warn] 缓存删除失败: %s" % e)


# ---------------------------------------------------------------------------
# 云边协同：MQTT 补传通道（可选）
# ---------------------------------------------------------------------------
_mqtt_cli = None


def _mqtt_client():
    global _mqtt_cli
    if not MQTT_ENABLED:
        return None
    if _mqtt_cli is None:
        try:
            cli = _paho.Client(client_id="box-mapper-%d" % os.getpid())
            try:
                # 断连期间限制待发队列，防内存膨胀（超出的数据已在本地缓存，恢复后补传）
                cli.max_queued_messages_set(2000)
            except Exception:
                pass
            user = MQTT_BROKER.get("username") or ""
            pwd = MQTT_BROKER.get("password") or ""
            if user:
                cli.username_pw_set(user, pwd)

            # 连上后订阅云端命令主题 cmd/{box}/#（平台下发部署模型/服务等指令）
            def _on_connect(c, u, f, rc, *a):
                if rc == 0:
                    try:
                        c.subscribe(MQTT_CMD_TOPIC.format(box=MQTT_BOX), qos=0)
                        print("[mqtt] 已订阅命令主题 %s" % MQTT_CMD_TOPIC.format(box=MQTT_BOX))
                    except Exception as e:
                        print("[warn] 订阅命令主题失败: %s" % e)
                else:
                    print("[warn] MQTT 连接失败 rc=%s，paho 将自动重试" % rc)

            cli.on_connect = _on_connect
            cli.on_message = _on_cmd_message
            # connect_async + loop_start：paho 后台线程自动重连（1s~120s 指数退避），
            # 云端 Broker 重启/网络抖动无需人工干预即可恢复
            cli.connect_async(MQTT_BROKER.get("host", "36.151.146.71"), int(MQTT_BROKER.get("port", 41883)), 30)
            cli.loop_start()
            _mqtt_cli = cli
        except Exception as e:
            print("[warn] MQTT 客户端初始化失败: %s" % e)
            return None
    return _mqtt_cli


def _mqtt_connected():
    """paho 后台线程当前是否已连上云端 Broker（未连接时返回 False，不阻塞）。"""
    cli = _mqtt_client()
    if cli is None:
        return False
    try:
        return bool(cli.is_connected())
    except Exception:
        return False


def mqtt_publish_realtime(device, values, ts):
    """实时读数双源：除 DMI twins 外，同时发布 data/# 到云端 Broker（独立直报、毫秒级）。

    与 DMI 通道互相独立：DMI 断连时 MQTT 仍可实时直报；Broker 重启由 paho 自动重连，
    无需人工干预。字符串/布尔值走 twins，不进 data/# 数值主题。
    """
    if not MQTT_ENABLED:
        return False
    cli = _mqtt_client()
    if cli is None:
        return False
    ok = 0
    name = device.get("name", "?")
    for prop, v in values.items():
        if v is None or isinstance(v, (str, bool)):
            continue
        topic = MQTT_TOPIC_TPL.format(box=MQTT_BOX, device=name, instance=name, property=prop)
        # hwId = 硬件唯一 ID（平台下发时写入设备定义）：改名只改 name，hwId 不变。
        # 云端时序库据此建子表 → 设备改名后历史不断链（主题里的 name 仅作显示）。
        payload_d = {"device": name, "box": MQTT_BOX, prop: float(v), "ts": float(ts)}
        hwid = str(device.get("hwId") or "").strip()
        if hwid:
            payload_d["hwId"] = hwid
        payload = json.dumps(payload_d)
        try:
            info = cli.publish(topic, payload, qos=0)
            info.wait_for_publish(0.3)
            ok += 1
        except Exception:
            break  # 发布异常即停止本轮；paho 自动重连后下一轮恢复
    return ok > 0


def mqtt_publish_replay(rows):
    """把缓存历史读数（带真实采集时间戳）发布到云端 Broker 的 data/# 主题。"""
    cli = _mqtt_client()
    if not cli:
        return False
    ok = 0
    for t, dev, prop, v in rows:
        topic = MQTT_TOPIC_TPL.format(box=MQTT_BOX, device=dev, instance=dev, property=prop)
        payload = json.dumps({"device": dev, "box": MQTT_BOX, prop: v, "ts": float(t)})
        try:
            info = cli.publish(topic, payload, qos=0)
            info.wait_for_publish(0.3)
            ok += 1
        except Exception:
            break
    return ok > 0


def _build_twins(device, values, ts_ms):
    twins = []
    for prop in sorted(values):
        v = values[prop]
        if v is None:
            continue
        if isinstance(v, bool):
            text = "true" if v else "false"
        elif isinstance(v, str):
            text = v  # 字符串值（ICCID/IMSI/IMEI 等）
        else:
            text = "%.4f" % float(v)
        twins.append(pb.Twin(
            propertyName=prop,
            observedDesired=pb.TwinProperty(value="", metadata={}),
            reported=pb.TwinProperty(value=text, metadata={"timestamp": str(int(ts_ms))}),
        ))
    return twins


def report_device(stub, device, values):
    """双源上报，任一通道成功即算成功：
    ① DMI ReportDeviceStatus -> 云端 K3s Device.status.twins（主链路，edgecore/CloudHub 实时同步）
    ② MQTT 实时发布 data/# -> 云端 Broker（独立直报，paho 自动重连）
    未送达通道对应的读数落本地缓存（主键 ts+device+property 去重），恢复后补传，数据不丢。"""
    ts = time.time()
    twins = _build_twins(device, values, ts * 1000)
    dmi_ok = False
    if stub is not None and twins:
        try:
            stub.ReportDeviceStatus(pb.ReportDeviceStatusRequest(
                deviceName=device.get("name"),
                deviceNamespace=device.get("namespace", "default"),
                reportedDevice=pb.DeviceStatus(
                    twins=twins,
                    reportToCloud=True,
                    reportCycle=int(float(device.get("interval", 1.0)) * 1000),
                ),
            ))
            dmi_ok = True
        except grpc.RpcError as e:
            print("[warn] [%s] ReportDeviceStatus 失败: %s" % (device.get("name"), e))
        except Exception as e:
            print("[warn] [%s] 上报异常: %s" % (device.get("name"), e))
    mqtt_ok = mqtt_publish_realtime(device, values, ts)
    if not mqtt_ok:
        # 仅缓存 MQTT 未送达的数据：MQTT 是带真实时间戳回填历史的通道，
        # 恢复后补传即还原断连期间完整历史；DMI 失败无需缓存（恢复后实时上报即同步最新值）
        for prop, v in values.items():
            if v is not None:
                cache_push(ts, device.get("name"), prop, v)
    return dmi_ok or mqtt_ok


def flush_cache(stub):
    """云边恢复后补传（双通道独立，任一通道通即各自回填）：
    ① MQTT：带真实时间戳回填全部历史 data/#（成功即删对应缓存）
    ② DMI：按设备补最新值到 twins（MQTT 未启用时兜底删缓存，避免无限重试）"""
    try:
        pending = cache_count()
        if pending <= 0:
            return
        rows = cache_peek(CACHE_FLUSH_BATCH)
        if not rows:
            return
        print("[info] 云边连接恢复，补传 %d/%d 条历史..." % (len(rows), pending))
        mqtt_ok = False
        if MQTT_ENABLED and _mqtt_connected():
            try:
                mqtt_ok = mqtt_publish_replay(rows)
                if mqtt_ok:
                    cache_remove(rows)
                    print("[info] MQTT 回填 %d 条历史，缓存剩余 %d 条" % (len(rows), cache_count()))
                    return  # 历史已带真实时间戳回填，最新值由实时上报持续覆盖
            except Exception as e:
                mqtt_ok = False
                print("[warn] MQTT 补传异常: %s" % e)
        elif MQTT_ENABLED:
            print("[info] MQTT 未连接，历史补传等待 paho 自动重连")
        dmi_ok = False
        if stub is not None:
            try:
                latest = {}
                for t, dev, prop, v in rows:
                    latest.setdefault(dev, {})[prop] = v
                for dev, props in latest.items():
                    device = {"name": dev, "namespace": "default", "interval": 1.0}
                    twins = _build_twins(device, props, rows[-1][0] * 1000)
                    if not twins:
                        continue
                    stub.ReportDeviceStatus(pb.ReportDeviceStatusRequest(
                        deviceName=dev,
                        deviceNamespace="default",
                        reportedDevice=pb.DeviceStatus(
                            twins=twins, reportToCloud=True, reportCycle=1000),
                    ))
                dmi_ok = True
            except grpc.RpcError as e:
                dmi_ok = False
                print("[warn] DMI 补传失败: %s" % e)
        if dmi_ok and not MQTT_ENABLED:
            cache_remove(rows)
            print("[info] DMI 补传完成（MQTT 未启用），缓存剩余 %d 条" % cache_count())
        elif dmi_ok:
            print("[info] DMI 已补最新值，历史待 MQTT 恢复回填（缓存 %d 条保留）" % cache_count())
    except Exception as e:
        print("[warn] 补传流程异常: %s" % e)


# ---------------------------------------------------------------------------
# 断连补传守护线程：与设备采集线程解耦。
# 即使所有采集线程因设备故障持续失败（reader 一直重连），只要 MQTT/DMI 恢复，
# 本线程周期调用 flush_cache 也能把断连期间的历史数据自动补传上云，数据不丢。
# ---------------------------------------------------------------------------
FLUSH_INTERVAL = int(os.environ.get("FLUSH_INTERVAL", 10))


def flusher_daemon(stop_event):
    print("[info] 补传守护线程启动（每 %ds 检查一次缓存）" % FLUSH_INTERVAL)
    while not stop_event.is_set():
        try:
            flush_cache(get_stub())
        except Exception as e:
            print("[warn] 补传守护异常: %s" % e)
        time.sleep(FLUSH_INTERVAL)


# ---------------------------------------------------------------------------
# 应用/模型部署（云端下发 cmd/{box}/# 命令，周期上报 state/{box}/services）
# 支持两类部署：
#   model   ：下载模型文件（可 tar.gz/zip 解压），仅存储，不自动启动
#   service ：下载可执行脚本/二进制，可配置启动命令并拉起后台进程（记录 pid）
# 部署清单保存在 APP_ROOT/manifest.json，盒子重启后仍可管理已部署应用。
# ---------------------------------------------------------------------------
APP_MANIFEST = os.path.join(APP_ROOT, "manifest.json")
APP_LOG_DIR = os.path.join(APP_ROOT, "logs")
_APP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _load_manifest():
    try:
        if os.path.exists(APP_MANIFEST):
            with open(APP_MANIFEST, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("apps"), dict):
                    return data
    except Exception as e:
        print("[warn] 读取应用清单失败: %s" % e)
    return {"apps": {}}


def _save_manifest(m):
    try:
        os.makedirs(os.path.dirname(APP_MANIFEST), exist_ok=True)
        tmp = APP_MANIFEST + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        os.replace(tmp, APP_MANIFEST)
        return True
    except Exception as e:
        print("[warn] 保存应用清单失败: %s" % e)
        return False


def _app_updated(m, name):
    m["apps"].setdefault(name, {})["updated_at"] = int(time.time())
    _save_manifest(m)


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _app_status(app):
    """读取清单中的应用状态并校正运行态（service 检查 pid 存活）。"""
    st = dict(app)
    if st.get("type") == "service" and st.get("pid"):
        st["running"] = _pid_alive(st.get("pid"))
        if not st["running"]:
            st["status"] = "stopped"
    return st


def _main_ip():
    """本机主接口 IPv4（默认路由源地址，供 ChirpStack 管理页 URL 用；失败返回空串）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2] or []:
            if not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return ""


def _chirpstack_status():
    """ChirpStack 栈（systemd nengtan-chirpstack + docker compose）运行状态。

    ChirpStack 由 deploy_chirpstack.sh 以独立 systemd 服务部署于本机
    （/opt/nengtan-chirpstack，UI :8080），不属于云端下发的 manifest 应用，
    故单独探测后并入 state/{box}/services 上报，平台盒子卡片据此显示其状态
    并提供管理页跳转。未安装时返回 None（不显示该服务行）。
    """
    if not os.path.isdir("/opt/nengtan-chirpstack"):
        return None
    running = False
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "nengtan-chirpstack"],
            capture_output=True, text=True, timeout=8,
        )
        running = out.stdout.strip() == "active"
    except Exception:
        running = False
    if not running:
        # systemd 兜底：按容器运行态判断（compose 项目 nengtan-chirpstack 的服务 chirpstack）
        try:
            out = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                capture_output=True, text=True, timeout=8,
            )
            running = any(
                ln.split()[0].startswith("nengtan-chirpstack-chirpstack") and len(ln.split()) > 1
                and ln.split()[1] == "Up"
                for ln in out.stdout.splitlines() if ln.strip()
            )
        except Exception:
            running = False
    ip = _main_ip()
    return {
        "name": "ChirpStack",
        "type": "LoRaWAN",
        "running": bool(running),
        "status": "running" if running else "stopped",
        "url": ("http://%s:8080" % ip) if ip else "",
        "command": "systemctl: nengtan-chirpstack",
    }


def _list_services():
    """全部已部署应用的状态列表（含本机预置的 ChirpStack，供周期上报与本地查询）。"""
    m = _load_manifest()
    out = []
    for name, app in m.get("apps", {}).items():
        st = _app_status(app)
        st["name"] = name
        out.append(st)
    cs = _chirpstack_status()
    if cs is not None:
        out.append(cs)
    return out


def _safe_app_name(name):
    return bool(name) and bool(_APP_NAME_RE.match(name or ""))


def _download(url, dest_dir):
    """下载 url 到 dest_dir，支持 tar.gz/tgz/zip 解压、单文件直接落盘。"""
    import urllib.request
    os.makedirs(dest_dir, exist_ok=True)
    url = str(url or "").strip()
    if not url:
        raise ValueError("url 为空")
    fname = url.split("?")[0].rstrip("/").split("/")[-1] or "payload"
    if not fname or fname in (".", ".."):
        fname = "payload"
    raw = os.path.join(dest_dir, "__download__")
    req = urllib.request.Request(url, headers={"User-Agent": "box-mapper/1.3"})
    with urllib.request.urlopen(req, timeout=60) as r, open(raw, "wb") as f:
        shutil.copyfileobj(r, f)
    if not os.path.exists(raw) or os.path.getsize(raw) == 0:
        raise IOError("下载失败或文件为空: %s" % url)
    low = fname.lower()
    if low.endswith(".tar.gz") or low.endswith(".tgz"):
        import tarfile
        with tarfile.open(raw, "r:gz") as tf:
            tf.extractall(dest_dir)
        os.remove(raw)
    elif low.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(raw) as zf:
            zf.extractall(dest_dir)
        os.remove(raw)
    else:
        final = os.path.join(dest_dir, fname)
        os.replace(raw, final)
    return dest_dir


def _start_service(name, app, command, args):
    """后台拉起 service（nohup 风格），写日志，返回 pid。"""
    workdir = os.path.join(APP_ROOT, name)
    os.makedirs(APP_LOG_DIR, exist_ok=True)
    logf = open(os.path.join(APP_LOG_DIR, "%s.log" % name), "ab", buffering=0)
    cmdline = [command] + list(args or [])
    try:
        proc = subprocess.Popen(
            cmdline, cwd=workdir, stdout=logf, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except FileNotFoundError:
        # 命令可能是相对路径脚本，尝试用 shell 解释
        proc = subprocess.Popen(
            " ".join(cmdline), cwd=workdir, stdout=logf, stderr=subprocess.STDOUT,
            shell=True, start_new_session=True,
        )
    app["pid"] = proc.pid
    app["status"] = "running"
    app["command"] = command
    app["args"] = list(args or [])
    return proc.pid


def _stop_service(name, app):
    pid = app.get("pid")
    if pid and _pid_alive(pid):
        try:
            os.kill(int(pid), 15)
            time.sleep(1)
            if _pid_alive(pid):
                os.kill(int(pid), 9)
        except OSError:
            pass
    app["pid"] = None
    app["status"] = "stopped"


def _deploy_app(cmd):
    """执行 deploy 指令，返回 (ok, message, detail)。"""
    name = str(cmd.get("name") or "").strip()
    if not _safe_app_name(name):
        return False, "应用名非法（仅字母数字 . _ -，1-64 字符）: %r" % name, None
    kind = str(cmd.get("type") or cmd.get("kind") or "service").lower()
    if kind not in ("model", "service"):
        return False, "部署类型仅支持 model/service: %r" % kind, None
    url = str(cmd.get("url") or "").strip()
    if not url:
        return False, "缺少下载地址 url（云端下发部署必须提供可下载的模型/服务包地址）", None
    app_dir = os.path.join(APP_ROOT, name)
    try:
        _download(url, app_dir)
    except Exception as e:
        return False, "下载/安装失败: %s" % e, None
    m = _load_manifest()
    app = m["apps"].setdefault(name, {})
    app.update({
        "name": name,
        "type": kind,
        "version": str(cmd.get("version") or "1.0.0"),
        "url": str(cmd.get("url") or ""),
        "path": app_dir,
    })
    if kind == "service":
        command = str(cmd.get("command") or "").strip()
        if command:
            try:
                pid = _start_service(name, app, command, cmd.get("args") or [])
                _app_updated(m, name)
                return True, "服务已启动 pid=%d" % pid, {"pid": pid, "status": "running"}
            except Exception as e:
                app["status"] = "stopped"
                _app_updated(m, name)
                return False, "启动失败: %s" % e, {"status": "stopped"}
        else:
            app["status"] = "stopped"
            _app_updated(m, name)
            return True, "应用已安装（未配置启动命令）", {"status": "stopped"}
    app["status"] = "downloaded"
    _app_updated(m, name)
    return True, "模型已部署", {"status": "downloaded"}


def _cmd_start_stop_remove(cmd):
    name = str(cmd.get("name") or "").strip()
    m = _load_manifest()
    app = m.get("apps", {}).get(name)
    if not app:
        return False, "应用不存在: %s" % name, None
    action = str(cmd.get("cmd") or "")
    try:
        if action == "start":
            if app.get("type") == "service":
                pid = _start_service(name, app, app.get("command"), app.get("args") or [])
                _app_updated(m, name)
                return True, "服务已启动 pid=%d" % pid, {"pid": pid, "status": "running"}
            app["status"] = "downloaded"
            _app_updated(m, name)
            return True, "模型无需启动", {"status": "downloaded"}
        if action == "stop":
            _stop_service(name, app)
            _app_updated(m, name)
            return True, "已停止", {"status": "stopped"}
        if action == "remove":
            _stop_service(name, app)
            m["apps"].pop(name, None)
            _save_manifest(m)
            shutil.rmtree(os.path.join(APP_ROOT, name), ignore_errors=True)
            return True, "已卸载", {"status": "removed"}
        if action == "restart":
            _stop_service(name, app)
            if app.get("type") == "service":
                pid = _start_service(name, app, app.get("command"), app.get("args") or [])
                _app_updated(m, name)
                return True, "服务已重启 pid=%d" % pid, {"pid": pid, "status": "running"}
            app["status"] = "downloaded"
            _app_updated(m, name)
            return True, "模型无需重启", {"status": "downloaded"}
    except Exception as e:
        return False, "操作失败: %s" % e, None
    return False, "未知命令: %s" % action, None


def _cmd_ack(cmd, ok, message, detail=None):
    """向平台回报命令执行结果（state/{box}/deploy）。"""
    cli = _mqtt_client()
    if not cli:
        print("[warn] MQTT 未就绪，命令回报丢弃: %s" % message)
        return
    payload = {
        "box": MQTT_BOX,
        "request_id": str(cmd.get("request_id") or cmd.get("rid") or ""),
        "cmd": str(cmd.get("cmd") or ""),
        "name": str(cmd.get("name") or ""),
        "ok": bool(ok),
        "message": str(message),
        "ts": time.time(),
    }
    if detail:
        payload["detail"] = detail
    try:
        cli.publish(MQTT_CMD_ACK_TOPIC.format(box=MQTT_BOX), json.dumps(payload), qos=0)
    except Exception as e:
        print("[warn] 命令回报发布失败: %s" % e)


def _find_device_cfg(name):
    # 一律读「运行期生效配置」：与采集线程同源，避免磁盘已改、内存未生效时的分叉
    for d in current_devices():
        if str(d.get("name")) == str(name):
            return d
    return None


def write_device_value(device_name, prop, value):
    """云端下发设定值 -> 写设备（保持寄存器 0x06 / 线圈 0x05）。

    config.json 设备项新增 writes 数组，例如（数控电源 0-24V，设定电压寄存器 0，0-2400→0-24.00V）：
      "writes": [
        {"property": "voltage_set", "kind": "holding", "registerAddr": 0,
         "scale": 100, "min": 0, "max": 2400},
        {"property": "output_on", "kind": "coil", "coilAddr": 0}
      ]
    scale 为"平台下发值 -> 寄存器原始值"的换算系数（12.00V × 100 = 1200）；
    min/max 为寄存器原始值的安全上下限，越界直接拒绝，避免误写烧设备。
    """
    d = _find_device_cfg(device_name)
    if d is None:
        return False, "设备不存在: %s" % device_name
    w = None
    for x in (d.get("writes") or []):
        if str(x.get("property")) == str(prop):
            w = x
            break
    if w is None:
        return False, "设备 %s 未配置可写点位 %s" % (device_name, prop)
    if str(d.get("protocol", "")).lower() != "modbus-rtu":
        return False, "仅 modbus-rtu 支持写入，当前协议: %s" % d.get("protocol")
    scfg = d.get("serial") or {}
    mcfg = d.get("modbus") or {}
    port = scfg.get("port")
    if not port:
        return False, "设备未配置串口"
    slave = int(mcfg.get("slaveId", 1))
    kind = str(w.get("kind") or "holding").lower()
    ser = None
    try:
        # 与采集线程共用同一条串口连接，避免抢收字节
        ser = _shared_serial(port, scfg)
        with _port_lock(port):
            if kind == "coil":
                addr = int(w.get("coilAddr", w.get("registerAddr", 0)))
                if isinstance(value, str):
                    on = value.strip().lower() in ("1", "true", "on", "yes", "open")
                else:
                    on = bool(value) and float(value) != 0
                _write_with_retry(lambda s: modbus_write_coil_rtu(s, slave, addr, on),
                                  ser, port, scfg)
                return True, "线圈%d=%s" % (addr, "ON" if on else "OFF")
            addr = int(w.get("registerAddr", 0))
            scale = float(w.get("scale", 1.0) or 1.0)
            try:
                raw = int(round(float(value) * scale))
            except (TypeError, ValueError):
                return False, "写入值非法: %r" % (value,)
            lo, hi = w.get("min"), w.get("max")
            if lo is not None and raw < int(lo):
                return False, "写入值 %d 低于下限 %s" % (raw, lo)
            if hi is not None and raw > int(hi):
                return False, "写入值 %d 超出上限 %s" % (raw, hi)
            echo = _write_with_retry(lambda s: modbus_write_holding_rtu(s, slave, addr, raw),
                                     ser, port, scfg)
            return True, "寄存器%d=%d（下发 %s × %s）" % (addr, echo[1], value, scale)
    except Exception as e:
        # 仅连接级故障才重建串口：普通丢帧重试后仍失败，不该把同串口其它设备的
        # 连接一起 close 掉（一条总线上多台设备时会造成"连锁掉线"）。
        if isinstance(e, OSError):
            _reset_serial(port)
        return False, "写入失败: %s" % e


# LoRa 活跃 reader 注册表：命令按需取数/自定义下行需要取实时连接（采集线程 connect 成功后注册）
_LORA_READER_REG = {}
_LORA_READER_LOCK = threading.Lock()


def _register_active_reader(name, reader):
    if isinstance(reader, LoraReader):
        with _LORA_READER_LOCK:
            _LORA_READER_REG[str(name)] = reader


def _unregister_active_reader(name):
    with _LORA_READER_LOCK:
        _LORA_READER_REG.pop(str(name), None)


# ---------------------------------------------------------------------------
# 设备命令执行（云端「命令执行」面板）：
#   * 读：一次性读任意寄存器（modbus-rtu/tcp）或 LoRa 主动取数一拍
#   * 写：property 模式走 writes 配置（见上）；addr 模式为一次性裸写寄存器（不落配置）
#   * 下行：LoRaWAN 向终端下发自定义下行（hex/text/object）
# 所有 IO 都走独立线程执行后再 _cmd_ack 回报，避免阻塞 MQTT 消息循环。
# ---------------------------------------------------------------------------
_REG_WIDTH = {"int16": 1, "uint16": 1, "short": 1, "ushort": 1, "word": 1,
              "int32": 2, "uint32": 2, "int": 2, "uint": 2, "dword": 2,
              "int64": 4, "uint64": 4, "long": 4, "ulong": 4,
              "float32": 2, "float": 2, "real": 2}


def read_device_regs(device_name, property_=None, addr=None, count=None,
                     dtype=None, fc=None, slave=None, scale=None, byte_order=None):
    """一次性读设备寄存器并解码（不依赖 writes 配置，用于新设备调试/写前确认）。

    两种寻址：
      * property_：读某采集点位（用配置里的 registerAddr/registerCount/type/fc/scale）
      * addr+fc+type+count：读任意寄存器（调试用）
    """
    d = _find_device_cfg(device_name)
    if d is None:
        return False, "设备不存在: %s" % device_name, None
    proto = (d.get("protocol") or "").lower()
    if proto not in ("modbus", "modbus-rtu", "rtu", "modbus-tcp", "tcp"):
        return False, "命令读仅支持 modbus 设备，当前协议: %s" % d.get("protocol"), None
    is_tcp = proto in ("modbus-tcp", "tcp")
    mcfg = d.get("modbus") or {}
    if not is_tcp and not (d.get("serial") or {}).get("port"):
        return False, "设备未配置串口", None
    try:
        slave_id = int(slave) if slave not in (None, "") else int(mcfg.get("slaveId", 1))
    except (TypeError, ValueError):
        return False, "slaveId 非法: %r" % (slave,), None

    point = None
    if property_:
        for p in (d.get("points") or []):
            if str(p.get("property")) == str(property_):
                point = p
                break
        if point is None:
            names = ", ".join(str(p.get("property")) for p in (d.get("points") or [])) or "（无点位）"
            return False, "设备 %s 未找到点位 %s（可用: %s）" % (device_name, property_, names), None
        addr = int(point.get("registerAddr", 0))
        count = int(point.get("registerCount", 1))
        dtype = str(point.get("type") or "uint16").lower()
        bo = point.get("byteOrder") or mcfg.get("byteOrder", "1234" if is_tcp else "2143")
    else:
        if addr is None:
            return False, "缺少 addr（寄存器地址）或 property（点位名）", None
        addr = int(addr)
        dtype = str(dtype or "uint16").lower()
        if count is None:
            count = _REG_WIDTH.get(dtype, 1)
        count = max(1, int(count))
        if count < _REG_WIDTH.get(dtype, 1):
            return False, "类型 %s 至少需 %d 个寄存器，当前 count=%d" % (
                dtype, _REG_WIDTH.get(dtype, 1), count), None
        bo = byte_order or mcfg.get("byteOrder", "1234" if is_tcp else "2143")
    try:
        fc3 = int(fc) if fc not in (None, "") else int(mcfg.get("fc", 3))
    except (TypeError, ValueError):
        fc3 = 3
    if fc3 not in (3, 4):
        return False, "fc 仅支持 3(保持寄存器)/4(输入寄存器)", None
    if is_tcp and fc3 == 4:
        return False, "modbus-tcp 暂仅支持功能码 3（读保持寄存器）", None

    try:
        if is_tcp:
            conn = ModbusTcpConn(
                (d.get("tcp") or {}).get("host", "127.0.0.1"),
                (d.get("tcp") or {}).get("port", 502),
                (d.get("tcp") or {}).get("timeout", 3.0))
            try:
                conn.connect()
                data = conn.read_holding(slave_id, addr, count)
            finally:
                conn.close()
        else:
            port = (d.get("serial") or {}).get("port")
            ser = _shared_serial(port, d.get("serial") or {})
            with _port_lock(port):
                data = modbus_read_regs_rtu(ser, slave_id, addr, count, fc3)
    except Exception as e:  # noqa: BLE001
        return False, "读寄存器失败: %s" % e, None

    try:
        v = decode_regs(data, dtype, bo)
    except Exception as e:  # noqa: BLE001
        return False, "寄存器解码失败(%s): %s" % (dtype, e), None
    raw_list = ["0x%04X" % struct.unpack(">H", data[i:i + 2])[0]
                for i in range(0, min(len(data), count * 2), 2)]
    # scale 优先取命令下发值；读点位且未单独给 scale 时用点位自带 scale（与采集读数一致）
    try:
        if scale not in (None, ""):
            v = v * float(scale)
        elif point is not None:
            v = v * float(point.get("scale", 1.0))
    except (TypeError, ValueError):
        pass
    detail = {"device": device_name, "addr": addr, "count": count, "type": dtype,
              "fc": fc3, "slaveId": slave_id, "byteOrder": bo,
              "raw": raw_list, "value": v}
    return True, "读寄存器%d 值=%s%s" % (
        addr, v, ("×%s" % (point.get("scale") if point else scale)) if (point and point.get("scale")) else ""), detail


def write_device_raw(device_name, addr=None, kind="holding", value=None,
                     lo=None, hi=None, slave=None):
    """一次性裸写寄存器（不落 writes 配置，供新设备上电设定如改 slaveID）。

    kind: holding(0x06 保持寄存器) / coil(0x05 线圈)。
    安全：holding 默认只允许 0~65535；可用 lo/hi 收紧（寄存器原始值）。
    """
    d = _find_device_cfg(device_name)
    if d is None:
        return False, "设备不存在: %s" % device_name
    if addr is None:
        return False, "缺少 addr（寄存器地址）"
    if str(d.get("protocol", "")).lower() != "modbus-rtu":
        return False, "裸写仅支持 modbus-rtu，当前协议: %s" % d.get("protocol")
    scfg = d.get("serial") or {}
    mcfg = d.get("modbus") or {}
    port = scfg.get("port")
    if not port:
        return False, "设备未配置串口"
    try:
        slave_id = int(slave) if slave not in (None, "") else int(mcfg.get("slaveId", 1))
    except (TypeError, ValueError):
        return False, "slaveId 非法: %r" % (slave,)
    addr = int(addr)
    kind = str(kind or "holding").lower()
    # 双保险：未显式传 lo/hi 时，用配置中同地址可写点位的范围兜底（平台下发的
    # 模型可写属性范围也会随 config 落到这里），避免裸写绕过限幅超限损伤设备。
    if lo is None and hi is None:
        for w in (d.get("writes") or []):
            if str(w.get("kind") or "holding").lower() != kind:
                continue
            wa = w.get("coilAddr") if kind == "coil" else w.get("registerAddr")
            try:
                same = wa is not None and int(wa) == addr
            except (TypeError, ValueError):
                same = False
            if same:
                lo, hi = w.get("min"), w.get("max")
                break
    ser = None
    try:
        ser = _shared_serial(port, scfg)
        with _port_lock(port):
            if kind == "coil":
                if isinstance(value, str):
                    on = value.strip().lower() in ("1", "true", "on", "yes", "open")
                else:
                    on = bool(value) and float(value) != 0
                _write_with_retry(lambda s: modbus_write_coil_rtu(s, slave_id, addr, on),
                                  ser, port, scfg)
                return True, "线圈%d=%s" % (addr, "ON" if on else "OFF")
            try:
                raw = int(round(float(value)))
            except (TypeError, ValueError):
                return False, "写入值非法: %r" % (value,)
            if lo is not None and raw < int(lo):
                return False, "写入值 %d 低于下限 %s" % (raw, lo)
            if hi is not None and raw > int(hi):
                return False, "写入值 %d 超出上限 %s" % (raw, hi)
            if raw < 0 or raw > 0xFFFF:
                return False, "写入值 %d 超出保持寄存器范围 0~65535（如为浮点请先 ×scale 转原始值）" % raw
            echo = _write_with_retry(
                lambda s: modbus_write_holding_rtu(s, slave_id, addr, raw), ser, port, scfg)
            return True, "寄存器%d=%d（从站%d）" % (echo[0], echo[1], slave_id)
    except Exception as e:  # noqa: BLE001
        if isinstance(e, OSError):
            _reset_serial(port)
        return False, "写入失败: %s" % e


def _active_reader(name):
    """取活跃 LoRa reader（按需主动取数/自定义下行时需要实时连接）。"""
    with _LORA_READER_LOCK:
        return _LORA_READER_REG.get(str(name))


def _read_lora_device(payload, cfg):
    device = str(payload.get("device") or "")
    r = _active_reader(device)
    if r is None:
        return False, "LoRa 设备 %s 未在采集运行（enabled=false 或采集线程未启动），无法按需取数" % device, None
    got = False
    note = ""
    # 取数只由「是否配了从站问帧（polls）」决定：读数一律来自轮询下发的应答，
    # 没配问帧就无从下发，也就取不到数。
    can_poll = bool(r.polls)
    if can_poll:
        got = r.poll_once()   # 下发问询 -> 等新上行
        note = "已下发下行取数；" if got else "已下发下行但 %.1fs 内未收到新上行（终端离线/下行未达？）；" % r.dl_timeout
    vals = r.snapshot_values()
    detail = {"device": device, "polled": bool(got), "values": vals,
              "downlink_enabled": bool(r.dl_enabled), "polls": len(r.polls)}
    if vals:
        return True, "LoRa 取到 %d 项值%s" % (len(vals), note), detail
    if got:
        return True, note + "未取到新值（终端可能未应答/点位过滤为空）", detail
    if not can_poll:
        return False, note + ("当前无值。该设备未配置从站问帧（lora.polls），无法取数："
                              "读数一律由下发问帧的应答带回，请在平台给该设备填从站号与"
                              "寄存器地址以生成问帧。"), detail
    return False, note + "可稍后再试或到终端侧排查下行链路", detail


def _lora_downlink(payload):
    device = str(payload.get("device") or "")
    r = _active_reader(device)
    if r is None:
        return False, "LoRa 设备 %s 未在采集运行，无法下发下行" % device, None
    try:
        ok, msg = r.send_raw_down(
            hex_data=payload.get("hex"), text=payload.get("text"), obj=payload.get("object"),
            fport=payload.get("fPort"), eui=payload.get("devEUI") or payload.get("eui"),
            confirmed=payload.get("confirmed"))
    except ValueError as e:
        return False, str(e), None
    except Exception as e:  # noqa: BLE001
        return False, "下行失败: %s" % e, None
    detail = {"device": device, "hex": payload.get("hex"), "text": payload.get("text"),
              "object": payload.get("object"), "fPort": payload.get("fPort")}
    return ok, msg, detail


def _run_device_io_cmd(payload):
    """设备 IO 命令异步执行线程体：执行后统一回报，不阻塞 MQTT 消息循环。"""
    cmd = str(payload.get("cmd") or "").lower()
    device = str(payload.get("device") or "")
    ok, message, detail = False, "未知命令: %s" % cmd, None
    try:
        if cmd in ("set", "write"):
            if payload.get("property") is not None and payload.get("addr") is None:
                ok, message = write_device_value(device, payload.get("property"), payload.get("value"))
                detail = {"device": device, "property": payload.get("property"),
                          "value": payload.get("value")}
            else:
                ok, message = write_device_raw(
                    device, addr=payload.get("addr"),
                    kind=payload.get("kind") or "holding",
                    value=payload.get("value"),
                    lo=payload.get("min") if "min" in payload else None,
                    hi=payload.get("max") if "max" in payload else None,
                    slave=payload.get("slaveId") if "slaveId" in payload else None)
                detail = {"device": device, "addr": payload.get("addr"),
                          "kind": payload.get("kind") or "holding",
                          "value": payload.get("value")}
        elif cmd in ("read", "get", "poll"):
            cfg = _find_device_cfg(device)
            if cfg is not None and (cfg.get("protocol") or "").lower() in ("lora", "lorawan"):
                ok, message, detail = _read_lora_device(payload, cfg)
            else:
                ok, message, detail = read_device_regs(
                    device, property_=payload.get("property"),
                    addr=payload.get("addr"), count=payload.get("count"),
                    dtype=payload.get("type") or payload.get("dtype"),
                    fc=payload.get("fc"), slave=payload.get("slaveId"),
                    scale=payload.get("scale"), byte_order=payload.get("byteOrder"))
        elif cmd in ("down", "downlink"):
            ok, message, detail = _lora_downlink(payload)
        else:
            ok, message, detail = False, "未知设备命令: %s" % cmd, None
    except Exception as e:  # noqa: BLE001
        ok, message, detail = False, "命令执行异常: %s" % e, None
    print("[info] 设备命令执行%s: cmd=%s device=%s -> %s"
          % ("成功" if ok else "失败", cmd, device, message))
    _cmd_ack(payload, ok, message, detail)


def _apply_config_cmd(payload):
    """平台/云端远程下发设备配置（cmd/{box}/config）：写入 config.json 并重启服务生效。

    payload:
      {"cmd":"config", "devices":[...], "remove": ["旧设备名"], "replace": false}
        - devices：mapper 设备配置数组（与 config.json 的 devices 同格式）
        - remove：要删掉的设备名（平台上已删除的设备，按 name 从配置里移除；
          先删后合，因此 remove 与 devices 同名时以 devices 为准 —— 改名场景安全）
        - lora_names：平台当前的 LoRa 设备名全集；盒子上凡是 protocol=lora 又不在这个
          名单里的条目（现场手工加的残留、改名前的旧名、回执缺失时平台看不到的条目）
          一并删除。只作用于 lora 条目，现场手工配的 modbus/opcua 设备不受影响。
        - replace：true=整体替换；false(默认)=按 name 合并（同名覆盖、新名追加）

    注意：平台上不存在的设备一律「删除」而不是留一条 enabled=false 的停采条目 ——
    停采条目在平台上表现为「有这台设备却没有数据」，既误导又不自愈。

    用途：用户在平台界面配好点位后点「下发到盒子」即可生效，
    无需现场 SSH 改文件（盒子运行期无 IP、无法远程登录）。
    写入前自动备份 config.json.bak.<时间戳>，写坏可回滚。
    """
    devices = payload.get("devices")
    if not isinstance(devices, list):
        devices = []
    # 删除语义：平台删掉的设备在盒子上真正删掉（不再保留 enabled=false 的停采条目）
    removed = [str(x).strip() for x in (payload.get("remove") or [])
               if str(x or "").strip()]
    if not devices and not removed:
        return False, "缺少 devices 数组（至少一台设备）或 remove 列表", None
    for d in devices:
        if not str(d.get("name") or "").strip():
            return False, "devices[].name 不能为空", None
    try:
        cfg = load_config()
    except Exception as e:  # noqa: BLE001
        return False, "读取现有配置失败: %s" % e, None

    gone: list = []
    if payload.get("replace"):
        merged = devices
    else:
        idx = {str(d.get("name")): d for d in (cfg.get("devices") or [])}
        gone = [n for n in removed if n in idx]
        for n in removed:
            idx.pop(n, None)
        for d in devices:
            idx[str(d.get("name"))] = d
        merged = list(idx.values())
        # 兜底清理：平台 LoRa 名单之外的 lora 条目一律删除（现场残留 / 改名旧名 /
        # 平台下发时拿不到盒子回执因而算不进 remove 的条目）
        scope = payload.get("lora_names")
        if isinstance(scope, list) and scope:
            keep = {str(x).strip() for x in scope if str(x or "").strip()}
            drop = {str(d.get("name")) for d in merged
                    if str(d.get("protocol")) == "lora" and str(d.get("name")) not in keep}
            if drop:
                merged = [d for d in merged if str(d.get("name")) not in drop]
                for n in sorted(drop):
                    if n not in gone:
                        gone.append(n)
    cfg["devices"] = merged

    backup = ""
    try:
        if os.path.exists(CONFIG_PATH):
            backup = "%s.bak.%s" % (CONFIG_PATH, time.strftime("%Y%m%d%H%M%S"))
            shutil.copy2(CONFIG_PATH, backup)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except Exception as e:  # noqa: BLE001
        return False, "写入配置失败: %s" % e, None

    # 写盘成功后立刻切换「运行期生效配置」：内存与磁盘同源，采集线程会在健康检查
    # 发现 version 变化后按新配置重建。这是「下发即生效」的保证 —— 不再依赖
    # systemctl 重启（历史故障：写盘成功但重启没生效，磁盘是新配置、内存还是旧
    # 配置，表现为平台显示有这台设备、盒子根本没在采集它）。
    ver = apply_runtime_config(cfg, source="cloud")

    # 兜底重启：重建 DMI 注册与连接，保持运行环境干净。重启只是兜底，
    # 配置生效不依赖它；即使重启没触发（手动运行/容器内运行），配置也已生效。
    def _restart():
        time.sleep(1.5)
        try:
            subprocess.Popen(["systemctl", "restart", "box-mapper"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            print("[warn] 重启 box-mapper 未触发（配置已在运行期生效）: %s" % e)

    threading.Thread(target=_restart, daemon=True).start()
    st = config_state()
    # 立即回报一次生效配置摘要（不等周期上报），平台据此判定「已下发 = 已生效」
    _publish_config_state()
    msg = "配置已生效：%d 台设备（版本 %d）" % (len(merged), ver)
    if gone:
        msg += "，已删除 %d 台：%s" % (len(gone), "、".join(gone))
    return True, msg, {
        "devices": [d.get("name") for d in merged],
        "removed": gone,
        "backup": backup,
        "fingerprint": st.get("fingerprint"),
        "version": ver,
        "pid": st.get("pid"),
        "enabled": [d.get("name") for d in merged if d.get("enabled") is not False],
        "disabled": [d.get("name") for d in merged if d.get("enabled") is False],
    }


def _on_cmd_message(client, userdata, msg):
    """订阅 cmd/{box}/# 收到平台下发的部署/启停/卸载/设定值/配置指令。"""
    try:
        payload = json.loads(msg.payload.decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            raise ValueError("指令必须为 JSON 对象")
    except Exception as e:
        print("[warn] 命令解析失败: %s" % e)
        return
    cmd = str(payload.get("cmd") or payload.get("action") or "").lower()
    # 容错：漏填 cmd 字段时，按内容推断。带 device+property+value 的即为设定值指令，
    # 避免"命令看着发出去了却没反应"（曾因平台侧漏带 cmd 被判为未知命令）。
    if not cmd and payload.get("device") and payload.get("property") is not None:
        cmd = "set"
    if not cmd and isinstance(payload.get("devices"), list):
        cmd = "config"
    print("[info] 收到云端命令 %r: %s" % (cmd, payload))
    if cmd in ("deploy", "install"):
        ok, message, detail = _deploy_app(payload)
    elif cmd in ("start", "stop", "remove", "uninstall", "restart"):
        if cmd == "uninstall":
            payload = dict(payload)
            payload["cmd"] = "remove"
        ok, message, detail = _cmd_start_stop_remove(payload)
    elif cmd in ("list", "services"):
        ok, message = True, "ok"
        detail = {"services": _list_services()}
    elif cmd in ("set", "write", "read", "get", "poll", "down", "downlink"):
        # 设备 IO 命令（写设定值、裸写/读寄存器、LoRa 下行与主动取数）。
        # 串口读最长约 1s、LoRa 下行等回报最长 dl_timeout，放独立线程执行后再回报，
        # 避免阻塞 MQTT 消息循环拖垮实时上报。
        threading.Thread(target=_run_device_io_cmd, args=(payload,), daemon=True).start()
        return
    elif cmd in ("config", "setconfig", "set_config", "devices"):
        # 远程下发设备配置（平台界面配置后一键生效）
        ok, message, detail = _apply_config_cmd(payload)
        print("[info] 配置下发%s: %s" % ("成功" if ok else "失败", message))
    elif cmd in ("config_get", "getconfig", "get_config"):
        try:
            # 返回「运行期生效配置」而非磁盘快照：平台读到的必须就是盒子此刻
            # 真正在采集的东西，两者不允许分叉。
            st = config_state()
            cur = current_config().get("devices") or []
            ok, message = True, "当前生效 %d 台设备（版本 %d）" % (len(cur), st.get("version"))
            detail = {"devices": cur, "fingerprint": st.get("fingerprint"),
                      "version": st.get("version"), "source": st.get("source")}
        except Exception as e:  # noqa: BLE001
            ok, message, detail = False, "读取配置失败: %s" % e, None
    else:
        ok, message = False, "未知命令: %s" % cmd
        detail = None
    _cmd_ack(payload, ok, message, detail)


def _publish_services():
    """周期上报运行服务列表到 state/{box}/services（平台盒子卡片展示）。"""
    cli = _mqtt_client()
    if not cli:
        return
    payload = {
        "box": MQTT_BOX,
        "services": _list_services(),
        "ts": time.time(),
    }
    try:
        cli.publish(MQTT_SERVICES_TOPIC.format(box=MQTT_BOX), json.dumps(payload), qos=0)
    except Exception as e:
        print("[warn] 服务状态上报失败: %s" % e)


def _publish_config_state():
    """上报「生效配置摘要」到 state/{box}/config（三端一致性校验的权威依据）。

    平台把它与「本地期望配置」「云端 CRD」三方比对：指纹一致=三端已对齐，
    不一致=存在漂移（能精确指出盒子现在到底在采集哪几台设备）。
    """
    cli = _mqtt_client()
    if not cli:
        return False
    try:
        cli.publish(MQTT_CONFIG_TOPIC.format(box=MQTT_BOX),
                    json.dumps(config_state()), qos=0)
        return True
    except Exception as e:  # noqa: BLE001
        print("[warn] 生效配置上报失败: %s" % e)
        return False


def services_reporter(stop_event):
    """周期上报当前运行的服务/模型列表与生效配置摘要（间隔 SERVICES_INTERVAL）。"""
    print("[info] 服务状态上报线程启动（每 %ds）" % SERVICES_INTERVAL)
    while not stop_event.is_set():
        try:
            if MQTT_ENABLED and _mqtt_connected():
                _publish_services()
                _publish_config_state()
        except Exception as e:
            print("[warn] 服务上报异常: %s" % e)
        time.sleep(SERVICES_INTERVAL)


# ---------------------------------------------------------------------------
# 设备采集线程
# ---------------------------------------------------------------------------
# 死值监测（stuck watch）：数值读数连续 count 拍纹丝不动 -> 注入 <prop>_stuck=1
# 告警属性并打醒目日志，恢复变化自动解除（注入 0）。防"假在线"掩盖变送器/传感器故障
# （例：变送器损坏恒定输出 0.01，无论称重多少寄存器纹丝不动）。设备配置示例：
#   "stuckWatch": {
#       "count": 30,             # 连续不变 N 拍触发（N x interval = 告警时长）
#       "deadband": 0.0,         # |Δ| <= deadband 视为不变；可按物理分辨率放宽
#       "properties": ["weight"] # 缺省 = 监测全部数值属性
#   }
# 仅在设备存在 stuckWatch 配置时启用，不影响其他设备；str/bool 状态属性不监测
# （ICCID/reg/在线状态等本就恒定）。告警属性随原通道上送：DMI twins + MQTT data/#，
# 云端 Device.status.twins / data/# 可直接看到，平台侧无需任何改动。
# ---------------------------------------------------------------------------
class StuckWatcher:
    """死值监测器（每设备一个实例，由 collector 驱动）。"""

    def __init__(self, device, interval=1.0):
        cfg = device.get("stuckWatch") or {}
        self.enabled = bool(device.get("stuckWatch")) and cfg.get("enabled", True) is not False
        self.count = max(2, int(cfg.get("count", 60) or 60))
        self.deadband = float(cfg.get("deadband", 0.0) or 0.0)
        watch = cfg.get("properties")
        self.props = [str(p) for p in watch] if watch else None  # None = 全部数值属性
        self.interval = max(0.1, float(interval or 1.0))
        self._last = {}   # prop -> 上一次有效值
        self._same = {}   # prop -> 连续不变拍数
        self._alarm = {}  # prop -> 当前告警态

    def _watched(self, prop, v):
        if v is None or isinstance(v, (str, bool)):
            return False
        if self.props is not None and prop not in self.props:
            return False
        return True

    def update(self, values):
        """比较本拍读数，就地合并告警属性到 values；返回告警状态翻转 [(prop, on), ...]。

        告警中每拍保持注入 <prop>_stuck=1（twins 持续刷新可见），解除时注入 0 清警；
        正常期不注入该属性，避免污染 twins。
        """
        flips = []
        for prop in list(values):
            v = values[prop]
            if not self._watched(prop, v):
                continue
            last = self._last.get(prop)
            if last is None or abs(float(v) - float(last)) > self.deadband:
                self._last[prop] = v
                self._same[prop] = 0
                on = False
            else:
                self._same[prop] = self._same.get(prop, 0) + 1
                on = self._same[prop] >= self.count
            prev = self._alarm.get(prop, False)
            self._alarm[prop] = on
            if on:
                values[prop + "_stuck"] = 1
            elif prev:
                values[prop + "_stuck"] = 0
            if on != prev:
                flips.append((prop, on))
        return flips


_stub_global = None
_stub_lock = threading.Lock()


def set_stub(stub):
    global _stub_global
    with _stub_lock:
        _stub_global = stub


def get_stub():
    with _stub_lock:
        return _stub_global


def collector(device, stop_event):
    """每设备独立线程：协议采集 -> 上报 -> 断连缓存/补传。"""
    name = device.get("name", "?")
    proto = device.get("protocol", "modbus-rtu")
    interval = float(device.get("interval", 1.0))
    points = device.get("points", [])
    print("[info] [%s] 采集线程启动: protocol=%s interval=%.1fs points=%d" % (
        name, proto, interval, len(points)))
    watcher = StuckWatcher(device, interval)
    if watcher.enabled:
        print("[info] [%s] 死值监测启用: 连续 %d 拍(~%.0fs)读数不变触发告警，监测=%s deadband=%s" % (
            name, watcher.count, watcher.count * watcher.interval,
            ",".join(watcher.props) if watcher.props else "全部数值属性", watcher.deadband))
    # 连续失败退避：设备不存在/掉线时若仍按原频率重试，每次都要空等到串口超时，
    # 会严重占用共享的 485 总线（同一串口上其它正常设备被拖慢甚至读数失败）。
    # 连续失败越多，重连间隔越长（5s→10s→30s→60s 封顶），成功后立即恢复正常频率。
    fail_streak = 0
    backoff_steps = (5, 5, 10, 30, 60)
    while not stop_event.is_set():
        reader = None
        try:
            reader = _make_reader(device)
            reader.connect()
            if isinstance(reader, LoraReader):
                _register_active_reader(name, reader)
            if fail_streak:
                print("[info] [%s] 采集恢复正常，重试频率回到 %.1fs" % (name, interval))
            fail_streak = 0
            print("[info] [%s] %s 连接成功" % (name, proto))
            while not stop_event.is_set():
                t0 = time.time()
                try:
                    values = reader.read_all()
                    if not values:
                        # 主动取数（LoRa 下行）未拿到本拍新值时返回空：跳过本拍上报，
                        # 既不重复上报旧值，也不写缓存，下一拍重新下发再试
                        # 按「补齐周期」休眠：周期严格等于 interval，拍用时长也不会把
                        # 周期越拖越长（对 LoRa 这类一拍要数秒的协议尤其重要）
                        time.sleep(max(0.1, interval - (time.time() - t0)))
                        continue
                    if watcher.enabled:
                        for prop, on in watcher.update(values):
                            if on:
                                print("[alarm] [%s] %s 已连续 ~%.0fs 读数无变化，疑似死值/变送器故障，请检查传感器与变送器！" % (
                                    name, prop, watcher.count * watcher.interval))
                            else:
                                print("[info] [%s] %s 读数恢复变化，死值告警解除" % (name, prop))
                    stub = get_stub()
                    # 多从站 DTU：一个 devEUI 下挂多台 485 传感器，按 polls[].device
                    # 分流上报到各自的平台设备主题（在平台就是一张张独立的设备卡片）
                    routed = getattr(reader, "routed", None)
                    if routed:
                        ok = False
                        for sub_name, sub_values in routed.items():
                            sub_dev = device if sub_name == name else dict(device, name=sub_name)
                            ok = report_device(stub, sub_dev, sub_values) or ok
                    else:
                        # stub 为 None（DMI 未就绪）时仍尝试上报：MQTT 实时直报通道独立可用，
                        # DMI 断连期间平台仍能经 data/# 拿到实时数据
                        ok = report_device(stub, device, values)
                    if ok:
                        flush_cache(stub)
                except Exception as e:
                    raise  # 采集层异常 -> 断开重连
                # 补齐周期：周期 = interval，拍用时计入其中
                time.sleep(max(0.1, interval - (time.time() - t0)))
        except Exception as e:
            wait = backoff_steps[min(fail_streak, len(backoff_steps) - 1)]
            fail_streak += 1
            print("[error] [%s] 采集异常: %s，%d 秒后重连（连续失败 %d 次）..." % (name, e, wait, fail_streak))
            stop_event.wait(wait)
            continue
        finally:
            if reader is not None:
                _unregister_active_reader(name)
                try:
                    reader.close()
                except Exception:
                    pass
        time.sleep(5)


# 全局持有回调 server 引用: 若被 GC, grpc 会 shutdown 并删除 unix socket 文件
_MAPPER_SERVER = None


def main():
    global _MAPPER_SERVER
    print("[info] 标准 KubeEdge DMI 多协议 mapper 启动: name=%s version=%s registerProtocol=%s" % (
        MAPPER_NAME, MAPPER_VERSION, MAPPER_PROTOCOL))
    print("[info] 设备数=%d 协议支持: modbus-rtu / modbus-tcp / opcua / lora / cellular%s" % (
        len(current_devices()), "" if _ASYNCUA_OK else "（asyncua 未安装，opcua 设备将跳过）"))
    _MAPPER_SERVER = serve_mapper_service()

    while True:
        try:
            if not os.path.exists(DMI_SOCKET):
                print("[warn] 等待 dmi.sock ...")
                time.sleep(3)
                continue
            channel = grpc.insecure_channel("unix://" + DMI_SOCKET)
            stub = pb_grpc.DeviceManagerServiceStub(channel)
            resp = stub.MapperRegister(pb.MapperRegisterRequest(
                withData=True,
                mapper=pb.MapperInfo(
                    name=MAPPER_NAME,
                    version=MAPPER_VERSION,
                    api_version=API_VERSION,
                    protocol=MAPPER_PROTOCOL,
                    address=MAPPER_SOCKET.encode(),
                    state="online",
                ),
            ), timeout=10)
            print("[info] MapperRegister 成功，返回 %d 个设备模型、%d 个设备" % (
                len(resp.modelList), len(resp.deviceList)))
            for m in resp.modelList:
                print("[dmi] 模型: %s/%s properties=%d" % (
                    m.namespace, m.name, len(m.spec.properties)))
            for d in resp.deviceList:
                cfg = {k: _unwrap_any(v) for k, v in d.spec.protocol.configData.data.items()}
                print("[dmi] 设备: %s/%s 协议=%s 配置=%s" % (
                    d.namespace, d.name, d.spec.protocol.protocolName, cfg))
            set_stub(stub)

            stop_event = threading.Event()
            devs = current_devices()
            run_version = config_version()
            threads = [threading.Thread(target=collector, args=(d, stop_event), daemon=True)
                       for d in devs]
            # 补传守护 + 服务状态上报：与采集线程并行，不依赖采集是否成功
            threads.append(threading.Thread(target=flusher_daemon, args=(stop_event,), daemon=True))
            if MQTT_ENABLED:
                threads.append(threading.Thread(target=services_reporter, args=(stop_event,), daemon=True))
            for t in threads:
                t.start()
            print("[info] 已启动 %d 个采集线程（生效配置版本 %d，设备: %s）+ 补传守护 + 服务上报" % (
                len(devs), run_version, ", ".join(str(d.get("name")) for d in devs)))

            # 健康检查：周期性重新 MapperRegister（幂等，刷新注册 + 校验 DMI 连通性）。
            # edgecore/CloudHub 重启、dmi.sock 重建后自动重注册恢复；盒子运行期无 IP、
            # 无法远程运维，必须全自动自愈（dmi.sock 缺失时等待其重建，不误判不退出）。
            while True:
                time.sleep(HEALTH_INTERVAL)
                if config_version() != run_version:
                    # 平台下发了新配置：立即按新配置重建采集线程（不依赖服务重启）。
                    # 「下发即生效」的最后一环：配置变了就必然重建，绝不留旧配置在跑。
                    print("[info] 检测到配置变更（版本 %d -> %d），按生效配置重建采集线程..." % (
                        run_version, config_version()))
                    stop_event.set()
                    break
                if not os.path.exists(DMI_SOCKET):
                    print("[warn] dmi.sock 不存在（edgecore 重启中？），等待重建...")
                    continue
                try:
                    stub.MapperRegister(pb.MapperRegisterRequest(
                        withData=True,
                        mapper=pb.MapperInfo(
                            name=MAPPER_NAME,
                            version=MAPPER_VERSION,
                            api_version=API_VERSION,
                            protocol=MAPPER_PROTOCOL,
                            address=MAPPER_SOCKET.encode(),
                            state="online",
                        ),
                    ), timeout=10)
                except grpc.RpcError as e:
                    print("[warn] DMI 健康检查失败（%s），停止采集线程并重新注册..." % e)
                    stop_event.set()
                    set_stub(None)
                    break
        except grpc.RpcError as e:
            set_stub(None)
            print("[warn] DMI 调用失败: %s，3 秒后重试" % e)
            time.sleep(3)
        except Exception as e:
            set_stub(None)
            print("[error] DMI 异常: %s，3 秒后重试" % e)
            time.sleep(3)


if __name__ == "__main__":
    main()
