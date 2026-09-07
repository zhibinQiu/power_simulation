"""中间件内置 MQTT Broker（零依赖，MQTT 3.1.1 子集）。

存在的意义（架构约定）：外部数据接入统一「注册到中间件服务」，中间件对外提供
两个服务端口：
  1) 内置 Broker（默认 :41884）——平台直接订阅本中间件，不再经云端 41883 收外部数据；
  2) 管理 API（HTTP，默认 :42084）——平台在此注册/启停/删除数据源适配器。

本 Broker 只服务「中间件输出桥发布 + 平台订阅」这一封闭场景，因此实现 MQTT 3.1.1
的必要子集即可（无持久会话/无离线队列/无保留消息/无 QoS2）：
  CONNECT / CONNACK / SUBSCRIBE / SUBACK / UNSUBSCRIBE / UNSUBACK
  PUBLISH(QoS0,1) / PUBACK / PINGREQ / PINGRESP / DISCONNECT
主题匹配支持标准通配符 '+'（单层）与 '#'（末层）。

实现要点：
- 一个 accept 线程 + 每连接一个读线程；订阅表与发送由同一把锁保护；
- 客户端出口各带一个发送队列（单写线程），避免并发 send 交错导致报文撕裂；
- 允许匿名连接（中间件部署在受控网络/本机），可选 token 作为 MQTT 用户名校验。
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# 报文类型
_CONNECT = 1
_CONNACK = 2
_PUBLISH = 3
_PUBACK = 4
_SUBSCRIBE = 8
_SUBACK = 9
_UNSUBSCRIBE = 10
_UNSUBACK = 11
_PINGREQ = 12
_PINGRESP = 13
_DISCONNECT = 14

_CONNACK_ACCEPTED = 0
_CONNACK_BAD_PROTOCOL = 1
_CONNACK_REFUSED = 5


# ----------------------------- 报文编解码 -----------------------------

def _encode_length(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out.append(b)
        if n <= 0:
            break
    return bytes(out)


def _encode_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def topic_matches(filt: str, topic: str) -> bool:
    """标准 MQTT 主题过滤匹配（'+' 单层、'#' 尾巴多层）。"""
    if filt == topic:
        return True
    if not filt:
        return False
    f_parts = filt.split("/")
    t_parts = topic.split("/")
    for i, fp in enumerate(f_parts):
        if fp == "#":
            return i == len(f_parts) - 1
        if i >= len(t_parts):
            return False
        if fp == "+":
            continue
        if fp != t_parts[i]:
            return False
    return len(f_parts) == len(t_parts)


class _Conn:
    """一个客户端连接：读循环 + 单写出线程。"""

    def __init__(self, sock: "socket.socket", addr, broker: "MiniBroker"):
        self.sock = sock
        self.addr = addr
        self.broker = broker
        self.client_id = ""
        self.keepalive = 60
        self.alive = True
        self._q: "list[bytes]" = []
        self._cv = threading.Condition()
        self._writer = threading.Thread(target=self._write_loop, daemon=True,
                                        name=f"mw-broker-w-{addr}")
        self._writer.start()

    # ---- 发送 ----
    def send(self, data: bytes) -> None:
        if not self.alive:
            return
        with self._cv:
            # 队列过长（客户端不消费）直接丢弃，避免中间件内存被拖垮
            if len(self._q) > 2000:
                return
            self._q.append(data)
            self._cv.notify()

    def _write_loop(self) -> None:
        while True:
            with self._cv:
                while self.alive and not self._q:
                    self._cv.wait(0.5)
                if not self._q:
                    if not self.alive:
                        return
                    continue
                data = self._q.pop(0)
            try:
                self.sock.sendall(data)
            except Exception:
                self.close()
                return

    # ---- 读取 ----
    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def _read_packet(self) -> "Tuple[int, bytes] | None":
        b0 = self._recv_exact(1)[0]
        ptype = b0 >> 4
        # PUBLISH 的 QoS 位于固定头 bit1-2，需在此保存（body 中不含该信息）
        self._last_qos = (b0 & 0x06) >> 1
        mult = 1
        length = 0
        while True:
            b = self._recv_exact(1)[0]
            length += (b & 0x7F) * mult
            if not (b & 0x80):
                break
            mult *= 128
        body = self._recv_exact(length) if length else b""
        return ptype, body

    # ---- 主循环 ----
    def serve(self) -> None:
        try:
            while self.alive:
                pkt = self._read_packet()
                if pkt is None:
                    break
                self.broker._dispatch(self, pkt[0], pkt[1])
        except Exception:
            pass
        finally:
            self.close()

    def close(self) -> None:
        if not self.alive:
            return
        self.alive = False
        self.broker._on_conn_close(self)
        try:
            self.sock.close()
        except Exception:
            pass
        with self._cv:
            self._cv.notify_all()


class MiniBroker:
    """中间件内置 MQTT Broker。start() 后台线程监听，stop() 优雅关闭。"""

    def __init__(self, host: str = "0.0.0.0", port: int = 41884,
                 token: str = "", logger: Optional[Callable[[str, str], None]] = None):
        self.host = str(host or "0.0.0.0")
        self.port = int(port or 41884)
        self.token = str(token or "")
        self.log = logger or (lambda *a: None)
        self._sock: Any = None
        self._thread: Any = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._conns: List[_Conn] = []
        # 订阅表：conn -> [(filter, qos)]
        self._subs: Dict[_Conn, List[Tuple[str, int]]] = {}
        self.stats: Dict[str, Any] = {
            "running": False, "started_at": None,
            "clients": 0, "subscriptions": 0,
            "published": 0, "received": 0,
            "last_publish_at": None, "last_topic": None,
            "last_error": "",
        }

    # ----------------------------- 生命周期 -----------------------------
    def start(self) -> None:
        if self.stats["running"]:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self.host, self.port))
            self._sock.listen(64)
        except Exception as e:  # noqa: BLE001
            self.stats["last_error"] = f"内置 Broker 监听 {self.host}:{self.port} 失败：{e}"
            self.log("error", self.stats["last_error"])
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            return
        self._stop.clear()
        self.stats["running"] = True
        self.stats["started_at"] = time.time()
        self.stats["last_error"] = ""
        self._thread = threading.Thread(target=self._accept_loop, daemon=True,
                                        name="mw-broker-accept")
        self._thread.start()
        self.log("info", f"内置 MQTT Broker 已启动 {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        with self._lock:
            conns = list(self._conns)
        for c in conns:
            c.close()
        self.stats["running"] = False

    # ----------------------------- 状态 -----------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            clients = len(self._conns)
            subs = sum(len(v) for v in self._subs.values())
        st = dict(self.stats)
        st["clients"] = clients
        st["subscriptions"] = subs
        st["host"] = self.host
        st["port"] = self.port
        st["uptime"] = int(time.time() - self.stats["started_at"]) if self.stats["started_at"] else 0
        return st

    # ----------------------------- 内部：连接管理 -----------------------------
    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                sock, addr = self._sock.accept()
            except Exception:
                if self._stop.is_set():
                    break
                time.sleep(0.2)
                continue
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn = _Conn(sock, addr, self)
            with self._lock:
                self._conns.append(conn)
            threading.Thread(target=conn.serve, daemon=True,
                             name=f"mw-broker-r-{addr}").start()

    def _on_conn_close(self, conn: _Conn) -> None:
        with self._lock:
            if conn in self._conns:
                self._conns.remove(conn)
            self._subs.pop(conn, None)

    # ----------------------------- 报文分发 -----------------------------
    def _dispatch(self, conn: _Conn, ptype: int, body: bytes) -> None:
        if ptype == _CONNECT:
            self._handle_connect(conn, body)
        elif ptype == _PUBLISH:
            self._handle_publish(conn, body)
        elif ptype == _PUBACK:
            return
        elif ptype == _SUBSCRIBE:
            self._handle_subscribe(conn, body)
        elif ptype == _UNSUBSCRIBE:
            self._handle_unsubscribe(conn, body)
        elif ptype == _PINGREQ:
            conn.send(bytes([_PINGRESP << 4, 0]))
        elif ptype == _DISCONNECT:
            conn.close()

    def _handle_connect(self, conn: _Conn, body: bytes) -> None:
        try:
            idx = 0
            plen = struct.unpack_from("!H", body, idx)[0]
            idx += 2
            proto = body[idx:idx + plen].decode("utf-8", "replace")
            idx += plen
            level = body[idx]
            idx += 1
            flags = body[idx]
            idx += 1
            idx += 2  # keepalive
            cid_len = struct.unpack_from("!H", body, idx)[0]
            idx += 2
            client_id = body[idx:idx + cid_len].decode("utf-8", "replace")
            idx += cid_len
            username = ""
            if flags & 0x80:  # username flag
                ulen = struct.unpack_from("!H", body, idx)[0]
                idx += 2
                username = body[idx:idx + ulen].decode("utf-8", "replace")
            if proto != "MQTT" or level != 4:
                conn.send(bytes([_CONNACK << 4, 2, 0, _CONNACK_BAD_PROTOCOL]))
                conn.close()
                return
            if self.token and username != self.token:
                conn.send(bytes([_CONNACK << 4, 2, 0, _CONNACK_REFUSED]))
                conn.close()
                return
            conn.client_id = client_id or f"anon-{id(conn)}"
            conn.send(bytes([_CONNACK << 4, 2, 0, _CONNACK_ACCEPTED]))
            self.log("info", f"客户端已连接：{conn.client_id}（{conn.addr[0]}）")
        except Exception as e:  # noqa: BLE001
            self.log("error", f"CONNECT 解析失败：{e}")
            conn.close()

    def _handle_subscribe(self, conn: _Conn, body: bytes) -> None:
        try:
            pid = struct.unpack_from("!H", body, 0)[0]
            idx = 2
            codes = bytearray()
            with self._lock:
                subs = self._subs.setdefault(conn, [])
                while idx < len(body):
                    tlen = struct.unpack_from("!H", body, idx)[0]
                    idx += 2
                    filt = body[idx:idx + tlen].decode("utf-8", "replace")
                    idx += tlen
                    qos = body[idx] & 0x03
                    idx += 1
                    subs.append((filt, qos))
                    codes.append(min(qos, 1))
            head = bytes([_SUBACK << 4]) + _encode_length(2 + len(codes))
            conn.send(head + struct.pack("!H", pid) + bytes(codes))
        except Exception as e:  # noqa: BLE001
            self.log("error", f"SUBSCRIBE 处理失败：{e}")

    def _handle_unsubscribe(self, conn: _Conn, body: bytes) -> None:
        try:
            pid = struct.unpack_from("!H", body, 0)[0]
            idx = 2
            with self._lock:
                subs = self._subs.get(conn, [])
                while idx < len(body):
                    tlen = struct.unpack_from("!H", body, idx)[0]
                    idx += 2
                    filt = body[idx:idx + tlen].decode("utf-8", "replace")
                    idx += tlen
                    subs[:] = [s for s in subs if s[0] != filt]
            conn.send(bytes([_UNSUBACK << 4, 2]) + struct.pack("!H", pid))
        except Exception as e:  # noqa: BLE001
            self.log("error", f"UNSUBSCRIBE 处理失败：{e}")

    def _handle_publish(self, conn: _Conn, body: bytes) -> None:
        try:
            idx = 0
            tlen = struct.unpack_from("!H", body, idx)[0]
            idx += 2
            topic = body[idx:idx + tlen].decode("utf-8", "replace")
            idx += tlen
        except Exception as e:  # noqa: BLE001
            self.log("error", f"PUBLISH 解析失败：{e}")
            return
        qos = getattr(conn, "_last_qos", 0)
        pid = None
        if qos == 1:
            pid = struct.unpack_from("!H", body, idx)[0]
            idx += 2
        payload = body[idx:]
        if qos == 1 and pid is not None:
            conn.send(bytes([_PUBACK << 4, 2]) + struct.pack("!H", pid))
        with self._lock:
            self.stats["received"] += 1
        self.publish(topic, payload, qos=0)

    # ----------------------------- 发布 -----------------------------
    def publish(self, topic: str, payload: "bytes | str", qos: int = 0) -> int:
        """向所有匹配订阅者投递一条消息；返回投递到的客户端数。"""
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        with self._lock:
            targets: List[Tuple[_Conn, int]] = []
            for conn, subs in self._subs.items():
                for filt, sq in subs:
                    if topic_matches(filt, topic):
                        targets.append((conn, sq))
                        break
            self.stats["published"] += 1
            self.stats["last_publish_at"] = time.time()
            self.stats["last_topic"] = topic
        pkt_head = bytes([_PUBLISH << 4])
        body = _encode_str(topic) + payload
        pkt = pkt_head + _encode_length(len(body)) + body
        n = 0
        for conn, _sq in targets:
            conn.send(pkt)
            n += 1
        return n
