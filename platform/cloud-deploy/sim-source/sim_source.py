#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""能碳平台 · 独立模拟数据源（外部系统仿真服务）

定位
----
本服务**独立于能碳平台项目**：不 import 平台/中间件任何代码、不依赖任何第三方库
（纯 Python 标准库），可单独拷贝到任意机器启动，用来模拟一个真实的外部业务系统：

    模拟数据源（本进程 = 外部系统）
        ├─ 自带一个极简 MQTT Broker（默认 127.0.0.1:41885，只给本机订阅）
        └─ 周期生成业务原生主题的数据：steel/<device>/telemetry、idc/<device>/telemetry
                    │  （外部系统自己的主题与 Broker，与平台规范无关）
                    ▼
    能碳数据中间件（mqtt 适配器订阅本 Broker）→ 转换/归属 → 云端 Broker(41883)
                    ▼
    平台按前缀识别外部源（ext-steel / ext-idc）

关键约定
--------
1. **平台自身不产生任何模拟数据**：模拟只存在于本独立进程，平台/中间件都不内置
   任何模拟生成器；停掉本服务 = 模拟数据消失，与真实外部系统行为一致。
2. 消息体为 JSON：`{"device": "<设备id>", "<测点>": <数值>, ...}`（常见外部系统形态），
   设备 id 由消息携带，因此一个主题可承载多设备、多测点。
3. 数值模型：基准 + 正弦波动 + 缓慢日漂移 + 有界噪声（曲线连续、可读、可复现）。

用法
----
    python3 sim_source.py --config config.json            # 启动（Broker + 数据生成）
    python3 sim_source.py --config config.json --check    # 自检：打印数据源清单后退出
    python3 sim_source.py --config config.json --port 41886   # 覆盖 Broker 端口

端口遵循项目全局规范：服务端口一律 40000+（默认 41885，被占用时 +1 递增避让）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import signal
import socket
import struct
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BROKER_PORT = 41885

# ============================ 极简 MQTT Broker（QoS0 子集） ============================
# 只实现外部订阅者（数据中间件）接入所需的最小子集：
#   CONNECT → CONNACK(0) | SUBSCRIBE → SUBACK(0) | PUBLISH(QoS0) 转发
#   PINGREQ → PINGRESP | DISCONNECT → 断开
# 不做鉴权/保留消息/遗嘱/QoS1-2（模拟外部系统无需），够用且零依赖。
_P_CONNECT, _P_CONNACK, _P_PUBLISH, _P_SUBSCRIBE, _P_SUBACK = 1, 2, 3, 8, 9
_P_PINGREQ, _P_PINGRESP, _P_DISCONNECT = 12, 13, 14


def _encode_len(length: int) -> bytes:
    """MQTT 剩余长度变长编码。"""
    out = bytearray()
    while True:
        b = length % 128
        length //= 128
        out.append(b | (0x80 if length > 0 else 0))
        if length <= 0:
            return bytes(out)


def _read_len(conn) -> Optional[int]:
    """读取 MQTT 剩余长度；连接关闭返回 None。"""
    multiplier, value = 1, 0
    for _ in range(4):
        data = conn.recv(1)
        if not data:
            return None
        value += (data[0] & 0x7F) * multiplier
        if not (data[0] & 0x80):
            return value
        multiplier *= 128
    return None


def topic_match(filt: str, topic: str) -> bool:
    """主题过滤匹配（支持单层 `+` 与多层 `#`，与 MQTT 规范一致）。"""
    if filt == topic:
        return True
    fs, ts = filt.split("/"), topic.split("/")
    for i, part in enumerate(fs):
        if part == "#":
            return i <= len(ts)
        if i >= len(ts):
            return False
        if part not in ("+", ts[i]):
            return False
    return len(fs) == len(ts)


class MiniBroker:
    """极简 MQTT Broker：本机订阅者接入 + 本地发布分发。"""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_BROKER_PORT,
                 logger=None):
        self.host = host
        self.port = port
        self.log = logger or (lambda *a: None)
        self._sock: Optional[socket.socket] = None
        self._subs: Dict[int, List[str]] = {}          # client_id -> 主题过滤器
        self._conns: Dict[int, socket.socket] = {}
        self._seq = 0
        self._lock = threading.Lock()
        self.running = False
        self.stats = {"clients": 0, "subscriptions": 0, "published": 0, "delivered": 0}

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(64)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True, name="sim-broker-accept").start()
        self.log("info", f"模拟源 Broker 已监听 {self.host}:{self.port}")

    def stop(self) -> None:
        self.running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        with self._lock:
            conns = list(self._conns.values())
            self._conns.clear()
            self._subs.clear()
        for c in conns:
            try:
                c.close()
            except OSError:
                pass
        self.log("info", "模拟源 Broker 已停止")

    # ---------- 发布（本地进程内调用，同时分发给已订阅的外部客户端）----------
    def publish(self, topic: str, payload: bytes) -> int:
        """发布一条消息；返回送达的订阅者数量。"""
        pkt = self._encode_publish(topic, payload)
        delivered = 0
        with self._lock:
            targets = [(cid, list(fs)) for cid, fs in self._subs.items()]
            conns = dict(self._conns)
            self.stats["published"] += 1
        for cid, filters in targets:
            if not any(topic_match(f, topic) for f in filters):
                continue
            conn = conns.get(cid)
            if conn is None:
                continue
            try:
                conn.sendall(pkt)
                delivered += 1
            except OSError:
                self._drop(cid)
        return delivered

    @staticmethod
    def _encode_publish(topic: str, payload: bytes) -> bytes:
        t = topic.encode("utf-8")
        body = struct.pack("!H", len(t)) + t + payload
        return bytes([_P_PUBLISH << 4]) + _encode_len(len(body)) + body

    # ---------- 服务端 ----------
    def _accept_loop(self) -> None:
        while self.running and self._sock is not None:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                return
            with self._lock:
                self._seq += 1
                cid = self._seq
                self._conns[cid] = conn
                self.stats["clients"] += 1
            threading.Thread(target=self._client_loop, args=(cid, conn),
                             daemon=True, name=f"sim-conn-{cid}").start()

    def _drop(self, cid: int) -> None:
        with self._lock:
            conn = self._conns.pop(cid, None)
            self._subs.pop(cid, None)
            self.stats["subscriptions"] = sum(len(v) for v in self._subs.values())
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass

    def _client_loop(self, cid: int, conn: socket.socket) -> None:
        try:
            while self.running:
                header = conn.recv(1)
                if not header:
                    break
                ptype = header[0] >> 4
                length = _read_len(conn)
                if length is None:
                    break
                body = b""
                while len(body) < length:
                    chunk = conn.recv(length - len(body))
                    if not chunk:
                        return
                    body += chunk
                if ptype == _P_CONNECT:
                    conn.sendall(bytes([_P_CONNACK << 4, 2, 0, 0]))
                elif ptype == _P_PINGREQ:
                    conn.sendall(bytes([_P_PINGRESP << 4, 0]))
                elif ptype == _P_DISCONNECT:
                    break
                elif ptype == _P_SUBSCRIBE:
                    self._handle_subscribe(cid, conn, body)
                elif ptype == _P_PUBLISH:  # 外部向本 Broker 发布（透传给订阅者）
                    if len(body) >= 2:
                        tlen = struct.unpack("!H", body[:2])[0]
                        topic = body[2:2 + tlen].decode("utf-8", "replace")
                        self.publish(topic, body[2 + tlen:])
                else:
                    continue  # 未支持的报文类型忽略（模拟源无需）
        except OSError:
            pass
        finally:
            self._drop(cid)

    def _handle_subscribe(self, cid: int, conn: socket.socket, body: bytes) -> None:
        if len(body) < 2:
            return
        pid = body[:2]
        filters: List[str] = []
        i = 2
        while i + 2 <= len(body):
            tlen = struct.unpack("!H", body[i:i + 2])[0]
            i += 2
            filters.append(body[i:i + tlen].decode("utf-8", "replace"))
            i += tlen + 1  # +1 跳过 QoS 字节
        with self._lock:
            # 同一连接可多次 SUBSCRIBE：过滤器累积（去重），与 MQTT 规范一致
            cur = self._subs.setdefault(cid, [])
            for f in filters:
                if f not in cur:
                    cur.append(f)
            self.stats["subscriptions"] = sum(len(v) for v in self._subs.values())
        conn.sendall(bytes([_P_SUBACK << 4, 2 + len(filters)]) + pid
                     + bytes([0] * len(filters)))
        self.log("info", f"订阅者#{cid} 订阅 {filters}")


# ============================ 模拟数据生成 ============================
def _num(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class Source:
    """一个模拟数据源（对应一个外部业务系统，如钢铁仿真 / 机房热控）。"""

    def __init__(self, cfg: Dict[str, Any], broker: MiniBroker, logger=None):
        self.cfg = cfg
        self.broker = broker
        self.log = logger or (lambda *a: None)
        self.box = str(cfg.get("box") or "").strip().lower()
        self.topic_prefix = str(cfg.get("topic_prefix") or self.box).strip("/")
        self.interval = max(0.5, _num(cfg.get("interval"), 2.0))
        self.devices: List[Dict[str, Any]] = [d for d in (cfg.get("devices") or [])
                                              if isinstance(d, dict)]
        self._stop = threading.Event()
        self._rnd = random.Random(int(time.time()) % 100000)
        self._phases: Dict[str, float] = {}
        self.stats = {"published": 0, "last_at": None, "last_topic": ""}

    # ---- 数值模型：基准 + 正弦 + 日漂移 + 有界噪声 ----
    def _phase(self, key: str) -> float:
        if key not in self._phases:
            import hashlib
            h = hashlib.md5(key.encode("utf-8")).hexdigest()
            self._phases[key] = (int(h[:8], 16) % 6283) / 1000.0
        return self._phases[key]

    def _value(self, device_id: str, prop: Dict[str, Any], now: float) -> float:
        name = str(prop.get("name") or "").strip()
        base = _num(prop.get("base"), 0.0)
        amp = _num(prop.get("amplitude"), 0.0)
        noise = abs(_num(prop.get("noise"), 0.0))
        period = max(1.0, _num(prop.get("period"), 60.0))
        phase = self._phase(f"{self.box}:{device_id}:{name}")
        wave = base + amp * math.sin(2.0 * math.pi * now / period + phase)
        drift = amp * 0.02 * math.sin(2.0 * math.pi * now / 86400.0)
        jitter = (self._rnd.random() * 2.0 - 1.0) * noise
        return round(wave + drift + jitter, 3)

    # ---- 生命周期 ----
    def start(self) -> None:
        self._stop.clear()
        threading.Thread(target=self._run, daemon=True,
                         name=f"sim-{self.box}").start()
        total = sum(len(d.get("properties") or []) for d in self.devices)
        self.log("info", f"[{self.box}] 模拟源启动：{len(self.devices)} 设备 / {total} 测点，"
                         f"周期 {self.interval}s（主题前缀 {self.topic_prefix}/）")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            for dev in self.devices:
                device_id = str(dev.get("id") or "").strip()
                if not device_id:
                    continue
                values: Dict[str, float] = {}
                for prop in (dev.get("properties") or []):
                    name = str(prop.get("name") or "").strip()
                    if not name:
                        continue
                    values[name] = self._value(device_id, prop, now)
                if not values:
                    continue
                payload = {"device": device_id, **values}
                topic = f"{self.topic_prefix}/{str(dev.get('topic') or device_id)}/telemetry"
                self.broker.publish(topic, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                self.stats["published"] += 1
                self.stats["last_at"] = now
                self.stats["last_topic"] = topic
            self._stop.wait(self.interval)

    def summary(self) -> Dict[str, Any]:
        return {
            "box": self.box,
            "topic_prefix": self.topic_prefix,
            "interval": self.interval,
            "devices": [{**{k: d.get(k) for k in ("id", "name", "topic")},
                         "properties": [p.get("name") for p in (d.get("properties") or [])]}
                        for d in self.devices],
        }


# ============================ 能碳一体机上行器（模拟） ============================
# 真实链路：外部数据系统 —网线/工业总线→ **能碳一体机**（采集）—上报→ 云端 Broker(41883)
#           → 云端数据中间件订阅转换 → 平台。
# 本类承担「能碳一体机」这一段：订阅本机私有 Broker（即外部数据系统的接入端口）上的
# 原生主题（steel/#、idc/#），把数据上行到云端 Broker 的上行空间（ext/<源>/#），
# 交由云端数据中间件转换为标准数据。零第三方依赖（自带的极简 MQTT 客户端）。
def _connect_packet(client_id: str, keepalive: int = 30) -> bytes:
    cid = client_id.encode("utf-8")
    body = (b"\x00\x04MQTT" + bytes([0x04, 0x02])
            + struct.pack("!H", keepalive) + struct.pack("!H", len(cid)) + cid)
    return bytes([_P_CONNECT << 4]) + _encode_len(len(body)) + body


def _subscribe_packet(topics: List[str], packet_id: int = 1) -> bytes:
    body = struct.pack("!H", packet_id)
    for t in topics:
        tb = t.encode("utf-8")
        body += struct.pack("!H", len(tb)) + tb + bytes([0])   # +QoS0
    return bytes([_P_SUBSCRIBE << 4 | 0x02]) + _encode_len(len(body)) + body


class BoxUplink:
    """模拟能碳一体机：采集外部数据系统 → 上报云端 Broker 上行空间 ext/<源>/#。"""

    def __init__(self, cfg: Dict[str, Any], logger=None):
        self.cfg = cfg or {}
        self.log = logger or (lambda *a: None)
        local = dict(cfg.get("local") or {})
        cloud = dict(cfg.get("cloud") or {})
        self.local_host = str(local.get("host") or "127.0.0.1")
        self.local_port = int(local.get("port") or DEFAULT_BROKER_PORT)
        self.topics = [str(t).strip() for t in (local.get("topics") or []) if str(t).strip()]
        self.cloud_host = str(cloud.get("host") or "")
        self.cloud_port = int(cloud.get("port") or 41883)
        self.prefix = str(cloud.get("prefix") or "").strip("/")
        self.keepalive = max(10, int(cfg.get("keepalive") or 30))
        self._sub: Any = None
        self._pub: Any = None
        self._stop = threading.Event()
        self._thread: Any = None
        self.stats = {"forwarded": 0, "errors": 0, "last_error": "",
                      "linked_source": False, "linked_cloud": False}

    # ---- 极简 MQTT 客户端 ----
    def _connect(self, host: str, port: int, client_id: str) -> socket.socket:
        s = socket.create_connection((host, port), timeout=5)
        s.settimeout(1.0)
        s.sendall(_connect_packet(client_id, self.keepalive))
        buf = b""
        while len(buf) < 4:                      # CONNACK: 20 02 00 00
            chunk = s.recv(4 - len(buf))
            if not chunk:
                raise OSError("连接被关闭（未收到 CONNACK）")
            buf += chunk
        if buf[0] != (_P_CONNACK << 4) or buf[3] != 0x00:
            raise OSError(f"CONNACK 返回码异常 rc={buf[3]}")
        return s

    def _ensure(self) -> None:
        if self._sub is None:
            self._sub = self._connect(self.local_host, self.local_port,
                                      "sim-box-uplink-sub")
            self._sub.sendall(_subscribe_packet(self.topics))
            self.stats["linked_source"] = True
            self.log("info", f"[一体机上行] 已接入外部数据系统 "
                             f"{self.local_host}:{self.local_port}，订阅 {self.topics}")
        if self._pub is None:
            self._pub = self._connect(self.cloud_host, self.cloud_port,
                                      "sim-box-uplink-pub")
            self.stats["linked_cloud"] = True
            self.log("info", f"[一体机上行] 已连接云端 Broker "
                             f"{self.cloud_host}:{self.cloud_port}"
                             f"（上行空间 {self.prefix or ''}/<源>/#）")

    def _reset(self) -> None:
        for sock in (self._sub, self._pub):
            if sock is None:
                continue
            try:
                sock.close()
            except OSError:
                pass
        self._sub = self._pub = None
        self.stats["linked_source"] = self.stats["linked_cloud"] = False

    def _forward(self, topic: str, payload: bytes) -> None:
        target = f"{self.prefix}/{topic}" if self.prefix else topic
        self._pub.sendall(MiniBroker._encode_publish(target, payload))
        self.stats["forwarded"] += 1
        self.stats["last_error"] = ""

    def _run(self) -> None:
        last_ping = 0.0
        while not self._stop.is_set():
            try:
                self._ensure()
                if time.time() - last_ping > self.keepalive / 2:
                    self._pub.sendall(bytes([_P_PINGREQ << 4, 0x00]))
                    last_ping = time.time()
                head = self._sub.recv(1)
                if not head:
                    raise OSError("外部数据系统连接已关闭")
                ptype = head[0] >> 4
                length = _read_len(self._sub) or 0
                body = b""
                while len(body) < length:
                    chunk = self._sub.recv(length - len(body))
                    if not chunk:
                        raise OSError("外部数据系统连接中断")
                    body += chunk
                if ptype == _P_PUBLISH and length >= 2:
                    tlen = struct.unpack("!H", body[:2])[0]
                    self._forward(body[2:2 + tlen].decode("utf-8", "replace"),
                                  body[2 + tlen:])
            except (socket.timeout, TimeoutError):
                continue
            except OSError as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e) or e.__class__.__name__
                self._reset()
                self._stop.wait(3.0)
            except Exception as e:  # noqa: BLE001
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                self._stop.wait(1.0)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="sim-box-uplink")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reset()

    def summary(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "from": f"{self.local_host}:{self.local_port} {self.topics}",
            "to": f"{self.cloud_host}:{self.cloud_port} "
                  f"{self.prefix or ''}/<源>/#",
        }


# ============================ 入口 ============================
def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _logger(verbose: bool):
    def log(level: str, msg: str) -> None:
        if level == "debug" and not verbose:
            return
        print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", file=sys.stderr, flush=True)
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description="能碳平台 · 独立模拟数据源（外部系统仿真）")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "config.json"),
                    help="数据源配置文件（默认 ./config.json）")
    ap.add_argument("--host", default="", help="覆盖 Broker 监听地址（默认取配置，缺省 127.0.0.1）")
    ap.add_argument("--port", type=int, default=0, help="覆盖 Broker 监听端口（默认 41885）")
    ap.add_argument("--check", action="store_true", help="自检：打印数据源清单后退出")
    ap.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    args = ap.parse_args()

    log = _logger(args.verbose)
    try:
        cfg = _load_config(args.config)
    except Exception as e:  # noqa: BLE001
        print(f"配置文件加载失败：{e}", file=sys.stderr)
        return 1

    bcfg = dict(cfg.get("broker") or {})
    host = args.host or str(bcfg.get("host") or "127.0.0.1")
    port = int(args.port or bcfg.get("port") or DEFAULT_BROKER_PORT)
    sources_cfg = [s for s in (cfg.get("sources") or []) if isinstance(s, dict)]

    print("=" * 70, file=sys.stderr, flush=True)
    print("能碳平台 · 独立模拟数据源（外部系统仿真）", file=sys.stderr, flush=True)
    print(f"配置文件    : {args.config}", file=sys.stderr, flush=True)
    print(f"自带 Broker : {host}:{port}", file=sys.stderr, flush=True)
    print(f"模拟数据源  : {len(sources_cfg)} 个", file=sys.stderr, flush=True)
    for s in sources_cfg:
        dev_cnt = len([d for d in (s.get("devices") or []) if isinstance(d, dict)])
        prop_cnt = sum(len(d.get("properties") or []) for d in (s.get("devices") or [])
                       if isinstance(d, dict))
        print(f"  - {s.get('box')}：{dev_cnt} 设备 / {prop_cnt} 测点，"
              f"周期 {s.get('interval')}s", file=sys.stderr, flush=True)

    # 一体机上行器（模拟）：从本机外部数据系统采集 → 上报云端 Broker 上行空间
    up_cfg = dict(cfg.get("uplink") or {})
    uplink = None
    if bool(up_cfg.get("enabled")):
        up_local = dict(up_cfg.get("local") or {})
        up_cloud = dict(up_cfg.get("cloud") or {})
        if not str(up_cloud.get("host") or "").strip():
            print("提示：uplink.cloud.host 为空，已禁用一体机上行（数据仅发到本机 Broker）",
                  file=sys.stderr, flush=True)
        else:
            if not [t for t in (up_local.get("topics") or []) if str(t).strip()]:
                up_cfg["local"] = {**up_local,
                                   "topics": [f"{s.get('topic_prefix') or s.get('box')}/#"
                                              for s in sources_cfg]}
            uplink = BoxUplink(up_cfg, log)
            print(f"一体机上行  : {uplink.summary()['from']} → {uplink.summary()['to']}",
                  file=sys.stderr, flush=True)

    if args.check:
        for s in sources_cfg:
            src = Source(s, MiniBroker(host, port, log), log)
            print(json.dumps(src.summary(), ensure_ascii=False, indent=2))
        if uplink is not None:
            print(json.dumps({"uplink（模拟能碳一体机转发）": uplink.summary()},
                             ensure_ascii=False, indent=2))
        print("=" * 70, file=sys.stderr, flush=True)
        return 0

    broker = MiniBroker(host, port, log)
    try:
        broker.start()
    except OSError as e:
        print(f"Broker 启动失败（端口 {port} 被占用？）：{e}", file=sys.stderr)
        return 1

    sources = [Source(s, broker, log) for s in sources_cfg]
    for s in sources:
        s.start()
    if uplink is not None:
        uplink.start()

    print("模拟数据源已就绪（Ctrl+C 停止）", file=sys.stderr, flush=True)
    stop = threading.Event()

    def _sig(signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    last = 0.0
    while not stop.is_set():
        if time.time() - last >= 60:
            b = broker.stats
            detail = "，".join(f"{s.box}:{s.stats['published']}" for s in sources)
            up = ""
            if uplink is not None:
                u = uplink.stats
                up = (f" | 上行(一体机) forwarded={u['forwarded']} errors={u['errors']}"
                      f" {u['last_error'] or ''}").strip()
            print(f"[sim] broker clients={b['clients']} subs={b['subscriptions']} "
                  f"published={b['published']} delivered={b['delivered']} | {detail}{up}",
                  file=sys.stderr, flush=True)
            last = time.time()
        stop.wait(1.0)

    for s in sources:
        s.stop()
    if uplink is not None:
        uplink.stop()
    broker.stop()
    log("info", "模拟数据源已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
