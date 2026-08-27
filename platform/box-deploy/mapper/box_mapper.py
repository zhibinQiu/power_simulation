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
      - lora         ：LoRaWAN（订阅盒子本地 mosquitto 的 ChirpStack 应用上行，payloadKey 映射）
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

# 云端部署的应用/模型安装根目录（子目录 = 应用名）
APP_ROOT = os.environ.get("APP_ROOT", CFG.get("apps", {}).get("dir", "/opt/box-apps"))
# 服务状态上报间隔（秒）
SERVICES_INTERVAL = int(os.environ.get("SERVICES_INTERVAL", 30))

# DMI 健康检查间隔：edgecore/CloudHub 重启、dmi.sock 重建后自动重新注册
# （盒子运行期无 IP、无法远程运维，必须全自动自愈，不依赖人工干预）
HEALTH_INTERVAL = int(os.environ.get("HEALTH_INTERVAL", 30))


def _load_devices(cfg):
    """兼容新旧格式：有 devices 数组用新格式，否则把旧单设备配置包装成单设备列表。"""
    devs = cfg.get("devices")
    if devs and isinstance(devs, list):
        return devs
    modbus = cfg.get("modbus") or {}
    serial = cfg.get("serial")
    tcp = cfg.get("tcp")
    protocol = cfg.get("protocol", "modbus")
    if tcp and tcp.get("host"):
        protocol = "modbus-tcp"
    elif protocol == "modbus":
        protocol = "modbus-rtu" if serial else "modbus-tcp"
    return [{
        "name": cfg.get("deviceName") or "default-device",
        "namespace": cfg.get("deviceNamespace", "default"),
        "protocol": protocol,
        "interval": cfg.get("interval", 1.0),
        "serial": serial,
        "tcp": tcp,
        "opcua": cfg.get("opcua"),
        "modbus": modbus,
        "points": [{
            "property": cfg.get("property", "value"),
            "registerAddr": modbus.get("registerAddr", 0) if isinstance(modbus, dict) else 0,
            "registerCount": modbus.get("registerCount", 2) if isinstance(modbus, dict) else 2,
            "type": "float32",
            "scale": modbus.get("scale", 1.0) if isinstance(modbus, dict) else 1.0,
            "byteOrder": modbus.get("byteOrder", "2143") if isinstance(modbus, dict) else "2143",
        }],
    }]


DEVICES = _load_devices(CFG)


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
    """寄存器字节流 -> 数值。data 为按寄存器顺序拼接的原始字节（每寄存器 2 字节大端）。"""
    dtype = (dtype or "float32").lower()
    bo = (byte_order or "2143").upper()
    if dtype in ("float32", "float", "real"):
        b = data[0:4]
        if len(b) < 4:
            return None
        if bo == "2143":
            b = b[1:2] + b[0:1] + b[3:4] + b[2:3]
        elif bo == "3412":
            b = b[2:4] + b[0:2]
        elif bo == "4321":
            b = b[::-1]
        return struct.unpack(">f", b)[0]
    if dtype in ("int16", "short"):
        return struct.unpack(">h", data[0:2])[0]
    if dtype in ("uint16", "ushort", "word"):
        return struct.unpack(">H", data[0:2])[0]
    if dtype in ("int32", "int"):
        return struct.unpack(">i", data[0:4])[0]
    if dtype in ("uint32", "uint", "dword"):
        return struct.unpack(">I", data[0:4])[0]
    if dtype in ("int64", "long"):
        return struct.unpack(">q", data[0:8])[0]
    if dtype in ("uint64", "ulong"):
        return struct.unpack(">Q", data[0:8])[0]
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


def modbus_read_holding_rtu(ser: SimpleSerial, slave: int, addr: int, count: int) -> bytes:
    """Modbus RTU 读保持寄存器（功能码 0x03），返回寄存器原始字节。"""
    req = struct.pack(">BBHH", slave, 0x03, addr, count)
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
    if resp[0] != slave or resp[1] != 0x03:
        raise IOError("响应头异常: %s" % resp[:4].hex())
    payload = resp[:-2]
    if modbus_crc(payload) != struct.unpack("<H", resp[-2:])[0]:
        raise IOError("CRC 校验失败")
    data = resp[3:3 + resp[2]]
    if len(data) < count * 2:
        raise IOError("数据长度不足")
    return data


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
        self.ser = None
        self._lock = _port_lock(self.port)

    def connect(self):
        self.close()
        self.ser = SimpleSerial(
            self.port,
            int(self.serial_cfg.get("baudrate", 9600)),
            int(self.serial_cfg.get("databits", 8)),
            self.serial_cfg.get("parity", "N"),
            int(self.serial_cfg.get("stopbits", 1)),
        )

    def read_all(self):
        if self.ser is None:
            self.connect()
        res = {}
        with self._lock:
            for p in self.points:
                data = modbus_read_holding_rtu(
                    self.ser, self.slave,
                    int(p.get("registerAddr", 0)),
                    int(p.get("registerCount", 2)),
                )
                bo = p.get("byteOrder") or self.modbus_cfg.get("byteOrder", "2143")
                v = decode_regs(data, p.get("type", "float32"), bo)
                res[p.get("property")] = None if v is None else _scale_point(v, p)
        return res

    def close(self):
        if self.ser is not None:
            self.ser.close()
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


class LoraReader:
    """LoRaWAN 网关桥接（被动推送模型）。

    盒子侧 LoRa 网关（SX1302 + ChirpStack）把传感器上行推送到本地 mosquitto
    （application/{appID}/device/{devEUI}/event/up），本 Reader 订阅该主题，
    从报文 JSON 的 object/data 中按点位 payloadKey 提取最新值缓存，read_all 返回缓存。
    """

    def __init__(self, d):
        self.cfg = d.get("lora") or {}
        self.points = d.get("points", [])
        self.broker = self.cfg.get("broker", "127.0.0.1")
        self.port = int(self.cfg.get("port", 1883) or 1883)
        self.application_id = str(self.cfg.get("applicationID", "+") or "+")
        self.dev_eui = str(self.cfg.get("devEUI", "+") or "+").lower()
        self._topic = "application/%s/device/%s/event/up" % (self.application_id, self.dev_eui)
        self._latest = {}      # devEUI -> {property: value}
        self._lock = threading.Lock()
        self._cli = None

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode(errors="replace"))
        except Exception:
            return
        obj = data.get("object")
        if not isinstance(obj, dict):
            obj = data.get("data")
        if not isinstance(obj, dict):
            obj = {}
        dev_eui = str(data.get("devEUI") or "").lower()
        values = {}
        for p in self.points:
            key = p.get("payloadKey")
            if not key:
                continue
            v = obj
            for part in str(key).split("."):  # 支持 a.b.c 嵌套路径
                if isinstance(v, dict) and part in v:
                    v = v[part]
                else:
                    v = None
                    break
            if v is not None:
                values[p.get("property")] = v
        if values:
            with self._lock:
                self._latest[dev_eui] = values

    def connect(self):
        self.close()
        if not _PAHO_OK:
            raise IOError("未安装 paho-mqtt，LoRaWAN 设备无法订阅")
        cli = _paho.Client(client_id="nengtan-lora-%d" % os.getpid())
        cli.on_message = self._on_message

        def _on_connect(c, u, f, rc, *a):
            if rc == 0:
                c.subscribe(self._topic)

        cli.on_connect = _on_connect
        cli.connect_async(self.broker, self.port, 30)
        cli.loop_start()
        self._cli = cli

    def read_all(self):
        with self._lock:
            if self.dev_eui != "+":
                vals = self._latest.get(self.dev_eui, {})
            else:  # 未指定 devEUI：合并订阅到的所有节点最新值
                vals = {}
                for v in self._latest.values():
                    vals.update(v)
        return dict(vals)

    def close(self):
        if self._cli is not None:
            try:
                self._cli.loop_stop()
                self._cli.disconnect()
            except Exception:
                pass
            self._cli = None


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
            cli.connect_async(MQTT_BROKER.get("host", "172.19.134.45"), int(MQTT_BROKER.get("port", 41883)), 30)
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
        payload = json.dumps({"device": name, "box": MQTT_BOX, prop: float(v), "ts": float(ts)})
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


def _list_services():
    """全部已部署应用的状态列表（供周期上报与本地查询）。"""
    m = _load_manifest()
    out = []
    for name, app in m.get("apps", {}).items():
        st = _app_status(app)
        st["name"] = name
        out.append(st)
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


def _on_cmd_message(client, userdata, msg):
    """订阅 cmd/{box}/# 收到平台下发的部署/启停/卸载指令。"""
    try:
        payload = json.loads(msg.payload.decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            raise ValueError("指令必须为 JSON 对象")
    except Exception as e:
        print("[warn] 命令解析失败: %s" % e)
        return
    cmd = str(payload.get("cmd") or payload.get("action") or "").lower()
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


def services_reporter(stop_event):
    """周期上报当前运行的服务/模型列表（间隔 SERVICES_INTERVAL）。"""
    print("[info] 服务状态上报线程启动（每 %ds）" % SERVICES_INTERVAL)
    while not stop_event.is_set():
        try:
            if MQTT_ENABLED and _mqtt_connected():
                _publish_services()
        except Exception as e:
            print("[warn] 服务上报异常: %s" % e)
        time.sleep(SERVICES_INTERVAL)


# ---------------------------------------------------------------------------
# 设备采集线程
# ---------------------------------------------------------------------------
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
    while not stop_event.is_set():
        reader = None
        try:
            reader = _make_reader(device)
            reader.connect()
            print("[info] [%s] %s 连接成功" % (name, proto))
            while not stop_event.is_set():
                try:
                    values = reader.read_all()
                    stub = get_stub()
                    # stub 为 None（DMI 未就绪）时仍尝试上报：MQTT 实时直报通道独立可用，
                    # DMI 断连期间平台仍能经 data/# 拿到实时数据
                    ok = report_device(stub, device, values)
                    if ok:
                        flush_cache(stub)
                except Exception as e:
                    raise  # 采集层异常 -> 断开重连
                time.sleep(interval)
        except Exception as e:
            print("[error] [%s] 采集异常: %s，5 秒后重连..." % (name, e))
        finally:
            if reader is not None:
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
        len(DEVICES), "" if _ASYNCUA_OK else "（asyncua 未安装，opcua 设备将跳过）"))
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
            threads = [threading.Thread(target=collector, args=(d, stop_event), daemon=True)
                       for d in DEVICES]
            # 补传守护 + 服务状态上报：与采集线程并行，不依赖采集是否成功
            threads.append(threading.Thread(target=flusher_daemon, args=(stop_event,), daemon=True))
            if MQTT_ENABLED:
                threads.append(threading.Thread(target=services_reporter, args=(stop_event,), daemon=True))
            for t in threads:
                t.start()
            print("[info] 已启动 %d 个采集线程 + 补传守护 + 服务上报" % len(threads))

            # 健康检查：周期性重新 MapperRegister（幂等，刷新注册 + 校验 DMI 连通性）。
            # edgecore/CloudHub 重启、dmi.sock 重建后自动重注册恢复；盒子运行期无 IP、
            # 无法远程运维，必须全自动自愈（dmi.sock 缺失时等待其重建，不误判不退出）。
            while True:
                time.sleep(HEALTH_INTERVAL)
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
