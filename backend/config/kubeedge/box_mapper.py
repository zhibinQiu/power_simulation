#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态 KubeEdge DMI Modbus mapper（纯 Python，仅依赖 grpcio + sqlite3，无第三方串口库）。

【配置源】云端 Device CRD —— edgecore 通过 CloudHub 把云端 Device 同步到本地
/var/lib/kubeedge/edgecore.db 的 meta_v2 表（value 列为完整对象 JSON，resourceversion 每次更新递增）。

【动态机制】
1. 启动时扫描 meta_v2 中全部 Device，按 spec.protocol.configData（串口/slaveID/点位表）动态建立采集任务
2. 每秒检测 meta_v2 的 resourceversion 变化 → 热更新采集任务
   （云端改名/改配置 → edgecore 自动同步 → mapper 自动跟随，全程无需人工干预/重启）

【回退兜底】若本地库无设备（云端尚未下发），回退读取 /opt/weight-bridge/config.json 的静态单设备配置。

【链路】称重仪表 --Modbus RTU(RS485/串口)--> 本 mapper --gRPC(dmi.sock)--> edgecore(deviceTwin/DMI)
        --CloudHub(10002)--> 云端 CloudCore --> K3s Device.status.twins
"""
import os
import sys
import json
import time
import hashlib
import struct
import fcntl
import termios
import select
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import grpc
import api_pb2 as pb
import api_pb2_grpc as pb_grpc

# ---------- 配置（仅 mapper 元信息 + 静态回退兜底） ----------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/opt/weight-bridge/config.json")
EDGECORE_DB = os.environ.get("EDGECORE_DB", "/var/lib/kubeedge/edgecore.db")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load_config()
DMI_SOCKET = os.environ.get("DMI_SOCKET", CFG.get("dmiSocket", "/etc/kubeedge/dmi.sock"))
MAPPER_SOCKET = os.environ.get("MAPPER_SOCKET", CFG.get("mapperSocket", "/tmp/nengtan-mapper.sock"))
MAPPER_NAME = CFG.get("mapperName", "nengtan-modbus-mapper")
MAPPER_VERSION = CFG.get("mapperVersion", "1.0.0")
API_VERSION = CFG.get("apiVersion", "v1beta1")
PROTOCOL = CFG.get("protocol", "nengtan-iot")
DEVICE_NAMESPACE = CFG.get("deviceNamespace", "default")
INTERVAL = float(CFG.get("interval", 1.0))

# 0x0200xxxx 是仪表"无传感器信号"等错误码，不视为真实重量
ERROR_MASK = 0xFFFF0000

# edgecore DMI 限流保护：在线状态(state=online)无需每秒上报，降频为 STATE_INTERVAL 秒一次；
# 触发 "too many request" 后 DMI 假死（需重启 edgecore 恢复），此时退避 BACKOFF_LIMITED 秒，避免雪崩。
STATE_INTERVAL = 30.0
BACKOFF_LIMITED = 60.0
BACKOFF_NORMAL = 5.0

# twins 上报周期：实测 DeviceTwin 处理 twins 消息约 1 条/秒，若 mapper 每秒上报 3 条 twins，
# 改名瞬间的消息风暴（删旧建新 + 积压）会把 DeviceTwin 队列打爆导致其卡死（云端 twins/state 全部消失）。
# 上报降到 REPORT_INTERVAL 秒一次（1 次 RPC = 3 twins ≈ 1 条/秒），速率匹配处理能力，改名风暴不再失控。
REPORT_INTERVAL = 3.0

# 设备集合变化（云端增删改设备）后的 DMI 安静期：
# 改名=云端删旧建新，若 mapper 此刻仍高频上报旧设备 twins，会与 DeviceTwin 的
# DeviceDeleted/DeviceCreated 事件处理形成并发竞争，导致 DeviceTwin 模块挂死
# （症状：日志只剩 edgestream 噪音，云端 state/twins 全部消失）。
# 检测到设备集合变化后暂停全部 DMI 上报 QUIET_SECONDS，让 DeviceTwin 无竞争地处理完事件。
QUIET_SECONDS = 10.0
_QUIET_UNTIL = 0.0


def _enter_quiet():
    global _QUIET_UNTIL
    _QUIET_UNTIL = time.time() + QUIET_SECONDS
ERROR_CODE = 0x02000000


# ---------- Modbus CRC16 ----------
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


# ---------- 串口底层（termios，无需 pyserial） ----------
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
        os.close(self.fd)


# ---------- 点位/设备模型 ----------
# (isSwap 字节内交换, isRegisterSwap 寄存器交换) -> byte_order
_BYTE_ORDER_MAP = {
    (False, False): "1234",
    (True, False): "2143",
    (False, True): "3412",
    (True, True): "4321",
}
_PARITY_MAP = {"none": "N", "even": "E", "odd": "O"}


class PropertySpec:
    """单个 Modbus 点位：从 CRD visitors 解析。"""
    __slots__ = ("name", "offset", "limit", "scale", "byte_order")

    def __init__(self, name, offset, limit, scale, byte_order):
        self.name = name
        self.offset = int(offset)
        self.limit = int(limit)
        self.scale = float(scale)
        self.byte_order = byte_order


class DeviceTask:
    """一台设备 = 一个串口 + 一个 Modbus 从站 + 一组点位。"""

    def __init__(self, namespace, name, port, baud, data, parity, stop_bits, slave_id,
                 interval, props, source="meta_v2"):
        self.namespace = namespace
        self.name = name
        self.port = port
        self.baud = baud
        self.data = data
        self.parity = parity
        self.stop_bits = stop_bits
        self.slave_id = slave_id
        self.interval = interval
        self.props = props
        self.source = source
        self.rv = None            # meta_v2 resourceversion（仅日志参考，不做变更判定）
        self.spec_hash = None     # Device spec 内容哈希（变更判定依据）
        self.stub = None
        self.running = False
        self.thread = None
        self._last_report_ts = 0.0   # 上次 ReportDeviceStatus(twins) 时间（按 REPORT_INTERVAL 节流）
        self._last_states_ts = 0.0   # 上次 ReportDeviceStates 时间（在线状态降频上报）

    def describe(self):
        return ("设备=%s/%s 串口=%s baud=%s slave=%s 点位=%s 周期=%ss [%s]" % (
            self.namespace, self.name, self.port, self.baud, self.slave_id,
            ",".join("%s@%d" % (p.name, p.offset) for p in self.props),
            self.interval, self.source))

    # ---- 生命周期 ----
    def start(self, stub):
        self.stub = stub
        if self.running:
            return
        self.running = True
        # 新任务/热更新后立即上报 state=online，避免 30s 节流延迟导致新设备云端 state 为空
        self._last_states_ts = 0.0
        self.thread = threading.Thread(target=self._loop, daemon=True, name="task-%s" % self.name)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
            self.thread = None

    # ---- 采集上报 ----
    def _loop(self):
        print("[info] 启动采集: %s" % self.describe())
        while self.running:
            ser = None
            backoff = BACKOFF_NORMAL
            try:
                ser = SimpleSerial(self.port, self.baud, self.data, self.parity, self.stop_bits)
                print("[info] 串口已打开: %s (%s)" % (self.port, self.name))
                while self.running:
                    try:
                        self._collect(ser)
                    except IOError as e:
                        print("[warn] %s 读取失败: %s" % (self.name, e))
                    time.sleep(self.interval)
            except Exception as e:
                print("[error] %s 串口异常: %s" % (self.name, e))
                backoff = BACKOFF_LIMITED if "too many request" in str(e) else BACKOFF_NORMAL
            finally:
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass
            if backoff >= BACKOFF_LIMITED:
                # edgecore DMI 限流假死，长退避等其恢复/被重启，避免雪崩
                print("[warn] %s DMI 限流(too many request)，%ds 后重试..." % (self.name, backoff))
            else:
                print("[info] %s %s 秒后重试串口..." % (self.name, backoff))
            time.sleep(backoff)

    def _collect(self, ser):
        now = time.time()
        if now < _QUIET_UNTIL:
            # 设备集合变化安静期：暂停 DMI 上报，避免与 DeviceTwin 增删事件并发竞争
            return
        if now - self._last_report_ts < REPORT_INTERVAL:
            return  # 未到 twins 上报周期（3s），避免消息速率超过 DeviceTwin 处理能力
        ts = str(int(now * 1000))
        twins = []
        for p in self.props:
            value = self._read_prop(ser, p)
            if value is None:
                continue  # 无信号错误码，跳过该属性
            twins.append(pb.Twin(
                propertyName=p.name,
                observedDesired=pb.TwinProperty(value="", metadata={}),
                reported=pb.TwinProperty(value="%.4f" % value, metadata={"timestamp": ts}),
            ))
        if not twins:
            print("[%s] %s 无信号，跳过上报" % (time.strftime("%H:%M:%S"), self.name))
            return
        vals = ", ".join("%s=%.4f" % (t.propertyName, float(t.reported.value)) for t in twins)
        print("[%s] %s %s" % (time.strftime("%H:%M:%S"), self.name, vals))
        req = pb.ReportDeviceStatusRequest(
            deviceName=self.name,
            deviceNamespace=self.namespace,
            reportedDevice=pb.DeviceStatus(
                twins=twins,
                reportToCloud=True,
                reportCycle=int(self.interval * 1000),
            ),
        )
        self.stub.ReportDeviceStatus(req)
        self._last_report_ts = now
        if now - self._last_states_ts >= STATE_INTERVAL:
            # state=online 为状态标记，无需每秒上报，降频避免触发 edgecore DMI 限流
            self.stub.ReportDeviceStates(pb.ReportDeviceStatesRequest(
                deviceName=self.name,
                deviceNamespace=self.namespace,
                state="online",
            ))
            self._last_states_ts = now

    def _read_prop(self, ser, p):
        req = struct.pack(">BBHH", self.slave_id, 0x03, p.offset, p.limit)
        req += struct.pack("<H", modbus_crc(req))
        ser.write(req)
        expected_len = 5 + p.limit * 2
        resp = ser.read(expected_len, timeout=1.0)
        if len(resp) < expected_len:
            extra = ser.read(expected_len - len(resp), timeout=0.5)
            if extra:
                resp += extra
        if len(resp) < expected_len:
            raise IOError("响应太短: %d/%d bytes" % (len(resp), expected_len))
        if resp[0] != self.slave_id or resp[1] != 0x03:
            raise IOError("响应头异常: %s" % resp[:4].hex())
        if modbus_crc(resp[:-2]) != struct.unpack("<H", resp[-2:])[0]:
            raise IOError("CRC 校验失败")
        data = resp[3:3 + resp[2]]
        if len(data) < 4:
            raise IOError("数据长度不足")
        b = data
        if p.byte_order == "2143":
            b1, b2, b3, b4 = b[1], b[0], b[3], b[2]
        elif p.byte_order == "1234":
            b1, b2, b3, b4 = b[0], b[1], b[2], b[3]
        elif p.byte_order == "4321":
            b1, b2, b3, b4 = b[3], b[2], b[1], b[0]
        elif p.byte_order == "3412":
            b1, b2, b3, b4 = b[2], b[3], b[0], b[1]
        else:
            raise ValueError("bad byte_order: %s" % p.byte_order)
        raw = (b1 << 24) | (b2 << 16) | (b3 << 8) | b4
        if raw >= 2 ** 31:
            raw -= 2 ** 32
        if (raw & ERROR_MASK) == ERROR_CODE:
            return None
        return raw * p.scale


def spec_hash_of(obj):
    """Device spec 内容指纹（status/twins 回写不影响，只有配置真的变化才变化）。"""
    spec = json.dumps(obj.get("spec", {}), ensure_ascii=False, sort_keys=True)
    return hashlib.md5(spec.encode("utf-8")).hexdigest()


# ---------- 从 Device CRD JSON 解析 ----------
def parse_device_crd(obj, rv):
    """obj: meta_v2 value 反序列化后的 Device 对象。返回 DeviceTask 或 None。"""
    spec = obj.get("spec") or {}
    protocol = spec.get("protocol") or {}
    cfg = protocol.get("configData") or {}
    com = cfg.get("com") or {}
    port = com.get("serialPort") or ""
    if not port:
        return None
    parity = _PARITY_MAP.get(str(com.get("parity", "none")).lower(), "N")
    slave_id = int(cfg.get("slaveID", 1))
    props = []
    for v in cfg.get("visitors") or []:
        name = v.get("propertyName")
        if not name:
            continue
        is_swap = bool(v.get("isSwap", False))
        is_reg_swap = bool(v.get("isRegisterSwap", False))
        bo = _BYTE_ORDER_MAP.get((is_swap, is_reg_swap), "1234")
        props.append(PropertySpec(
            name,
            int(v.get("offset", 0)),
            int(v.get("limit", 2)),
            float(v.get("scale", 1.0)),
            bo,
        ))
    if not props:
        return None
    cycles = [int(p.get("collectCycle") or 1000) for p in (spec.get("properties") or [])]
    interval = max(1.0, (min(cycles) if cycles else 1000) / 1000.0)
    task = DeviceTask(
        obj.get("metadata", {}).get("namespace") or DEVICE_NAMESPACE,
        obj.get("metadata", {}).get("name") or "",
        port,
        int(com.get("baudRate", 9600)),
        int(com.get("dataBits", 8)),
        parity,
        int(com.get("stopBits", 1)),
        slave_id,
        interval,
        props,
    )
    task.rv = rv
    task.spec_hash = spec_hash_of(obj)
    return task


def build_static_task():
    """本地库无设备时，回退 config.json 的静态单设备配置（向后兼容）。"""
    ser = CFG.get("serial") or {}
    modbus = CFG.get("modbus") or {}
    port = ser.get("port") or ""
    name = CFG.get("deviceName") or ""
    if not port or not name:
        return None
    task = DeviceTask(
        CFG.get("deviceNamespace", "default"), name, port,
        int(ser.get("baudrate", 9600)),
        int(ser.get("databits", 8)),
        ser.get("parity", "N"),
        int(ser.get("stopbits", 1)),
        int(modbus.get("slaveId", 1)),
        float(CFG.get("interval", 1.0)),
        [PropertySpec(
            CFG.get("property", "weight"),
            int(modbus.get("registerAddr", 0)),
            int(modbus.get("registerCount", 2)),
            float(modbus.get("scale", 1.0)),
            modbus.get("byteOrder", "2143"),
        )],
        source="config.json",
    )
    task.rv = 0
    task.spec_hash = "static"
    return task


# ---------- 动态同步（diff + 热更新） ----------
def load_devices_from_db():
    """读 edgecore.db meta_v2，返回 {name: (DeviceTask, rv, spec_hash)}。"""
    out = {}
    try:
        conn = sqlite3.connect(EDGECORE_DB, timeout=2)
        rows = conn.execute(
            "select key, value, resourceversion from meta_v2 "
            "where key like '%/devices/%' and key not like '%devicemodel%'"
        ).fetchall()
        conn.close()
    except Exception as e:
        print("[warn] 读取 edgecore.db 失败: %s" % e)
        return out
    for key, value, rv in rows:
        try:
            obj = json.loads(value)
            name = obj.get("metadata", {}).get("name")
            if not name:
                continue
            task = parse_device_crd(obj, rv)
            if task:
                out[name] = (task, rv, task.spec_hash)
        except Exception as e:
            print("[warn] 解析设备 %s 失败: %s" % (key, e))
    return out


def sync_devices(stub, tasks, lock):
    """diff 并热更新采集任务。

    变更判定依据 = Device spec 内容哈希（spec_hash），而不是 resourceversion。
    因为 edgecore 会把 mapper 上报的 twins 状态回写 meta_v2 使 rv 持续递增，
    但那不是配置变更；只有云端真正改 spec（改名/改参数）才会触发热更新。
    """
    devices = load_devices_from_db()
    if not devices:
        fb = build_static_task()
        if fb:
            devices[fb.name] = (fb, 0, fb.spec_hash)
    with lock:
        changed = False
        # 停止并移除已删除设备
        for name in list(tasks):
            if name not in devices:
                print("[info] 云端已删除设备 %s，停止采集" % name)
                tasks[name].stop()
                del tasks[name]
                changed = True
        # 新增/变更设备
        for name, (task, rv, sh) in devices.items():
            old = tasks.get(name)
            if old is not None and old.spec_hash == sh and old.source == task.source:
                continue
            if old is not None:
                print("[info] 设备 %s 配置变更(hash=%s->%s)，热更新" % (name, old.spec_hash, sh))
                old.stop()
            else:
                print("[info] 发现新设备 %s" % name)
            task.start(stub)
            tasks[name] = task
            changed = True
        if changed:
            _enter_quiet()
            print("[info] 设备集合变化，进入 %ss DMI 安静期，让 DeviceTwin 处理事件..." % QUIET_SECONDS)


# ---------- DMI 回调服务（edgecore -> mapper） ----------
class MapperService(pb_grpc.DeviceMapperServiceServicer):
    def RegisterDevice(self, request, context):
        d = request.device
        print("[dmi] RegisterDevice: %s/%s" % (d.namespace, d.name))
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


_MAPPER_SERVER = None


def main():
    global _MAPPER_SERVER
    print("[info] 动态 DMI mapper 启动: name=%s version=%s protocol=%s db=%s" % (
        MAPPER_NAME, MAPPER_VERSION, PROTOCOL, EDGECORE_DB))
    _MAPPER_SERVER = serve_mapper_service()
    tasks = {}
    lock = threading.Lock()
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
                    protocol=PROTOCOL,
                    address=MAPPER_SOCKET.encode(),
                    state="online",
                ),
            ), timeout=10)
            print("[info] MapperRegister 成功: 模型=%d 设备=%d" % (
                len(resp.modelList), len(resp.deviceList)))
            sync_devices(stub, tasks, lock)
            while True:
                time.sleep(1.0)
                try:
                    sync_devices(stub, tasks, lock)
                except grpc.RpcError as e:
                    print("[warn] DMI 失联: %s" % e)
                    break
        except grpc.RpcError as e:
            print("[warn] DMI 调用失败: %s，3 秒后重试" % e)
            time.sleep(3)
        except Exception as e:
            print("[error] DMI 异常: %s，3 秒后重试" % e)
            time.sleep(3)
        finally:
            with lock:
                for t in tasks.values():
                    t.stop()
                tasks.clear()


if __name__ == "__main__":
    main()
