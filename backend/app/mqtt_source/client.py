"""mqtt_source 包：多 Broker 订阅客户端生命周期（每端点独立 client + 重连退避）。

平台订阅两类数据入口（用户诉求：外部数据注册到中间件，平台订阅取数）：
  - cloud      ：云端 Broker（一体机盒子/agent 推送），订阅配置主题 + $SYS/#；
                 中间件 external 形态下，外部数据源/模拟数据也直发本 Broker 的
                 data/ext-*/... 主题（消息归属按前缀自动区分，见 ingest）。
  - middleware ：中间件独立数据端口（仅 local 形态，middleware.json subscribe=true）：
                 外部数据源（含独立模拟源），只订阅 data/#；external 形态 subscribe=false
                 时本端点停用。

两端共享同一条摄取管道（ingest._record_message，用 source 参数区分口径），因此
设备识别、读数解析、关联驱动仿真完全复用，无重复代码。

start() 由 main.py 启动时调用一次，为每个端点各起一个线程；
update_config（云端 Broker 配置）经 _restart_subscriber 只重启 cloud 端点；
中间件配置变更经 restart_middleware() 只重启 middleware 端点。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict

from . import _shared
from ._shared import _LOCK, _STATE, mqtt
from .ingest import _record_message

# 事件推送节流：同类事件在 min_gap 秒内只提醒一次，避免断线自动重试期间每 5 秒刷屏打扰
_last_push_ts: Dict[str, float] = {}


def _push_event(key: str, level: str, title: str, body: str, min_gap: float = 60.0) -> None:
    """把警告/错误/恢复事件推送到前端弹窗（经 realtime.manager 广播，不再打印到命令行）。"""
    from .. import realtime  # 延迟导入，避免与 realtime.py 顶层 import mqtt_source 形成循环
    now = time.time()
    if now - _last_push_ts.get(key, 0.0) < min_gap:
        return
    _last_push_ts[key] = now
    realtime.manager.notify(level, title, body)


# ---------------------------------------------------------------------------
# 端点连接（每个端点一个 paho client + 一个线程）
# ---------------------------------------------------------------------------

class _Endpoint:
    """一个订阅端点的连接管理（connect → loop_forever，断线自动重连）。"""

    def __init__(self, key: str):
        self.key = key
        self.client: Any = None
        self._thread: Any = None
        self._rev = 0              # 配置版本号：重启时自增，旧线程据此退出

    # ---- 配置 ----
    @property
    def cfg(self) -> Dict[str, Any]:
        return _shared._ENDPOINTS.get(self.key) or {}

    @property
    def broker(self) -> Dict[str, Any]:
        return dict(self.cfg.get("broker") or {})

    @property
    def topics(self) -> list:
        return list(self.cfg.get("topics") or [])

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    def label(self) -> str:
        return str(self.cfg.get("label") or self.key)

    # ---- client 构造 ----
    def _make_client(self):
        b = self.broker
        cid = f"{b.get('client_id', 'carbon-sim-collector')}-{self.key}-{os.getpid()}-{self._rev}"
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=True)
        except TypeError:
            try:
                return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
            except TypeError:
                return mqtt.Client(client_id=cid)

    # ---- 回调 ----
    def _on_connect(self, client, userdata, flags, reason_code, *args):
        rc = reason_code if isinstance(reason_code, int) else \
            (getattr(reason_code, "value", reason_code))
        with _LOCK:
            st = _shared._EP_STATE.setdefault(self.key, {})
            was_down = not st.get("connected")
            st["connected"] = rc == 0
            st["last_connect_rc"] = rc
            st["last_error"] = "" if rc == 0 else f"连接失败 rc={rc}"
            if self.key == "cloud":     # 主状态保持云端口径（前端/旧接口兼容）
                _STATE["connected"] = rc == 0
                _STATE["last_connect_rc"] = rc
                _STATE["last_error"] = st["last_error"]
        if rc == 0:
            for t in self.topics:
                client.subscribe(t, qos=int(self.broker.get("qos", 0)))
            if self.cfg.get("sys"):
                # 额外订阅 $SYS/# 收集 Broker 统计（实时仪表盘数据源，仅云端 Broker）
                client.subscribe("$SYS/#", qos=0)
            if was_down:
                _push_event(f"mqtt-up-{self.key}", "success", f"{self.label()}：已连接",
                            f"{self.broker.get('host')}:{self.broker.get('port')} 连接成功，"
                            "实时数据持续更新。")
        else:
            self._notify_down(f"连接失败 rc={rc}")

    def _on_disconnect(self, client, userdata, flags, reason_code, *args):
        with _LOCK:
            st = _shared._EP_STATE.setdefault(self.key, {})
            st["connected"] = False
            st["last_error"] = f"连接断开 rc={reason_code}"
            if self.key == "cloud":
                _STATE["connected"] = False
                _STATE["last_error"] = st["last_error"]
        self._notify_down(f"连接断开 rc={reason_code}")

    def _on_message(self, client, userdata, msg):
        with _LOCK:
            st = _shared._EP_STATE.setdefault(self.key, {})
            st["message_count"] = int(st.get("message_count") or 0) + 1
            st["last_message_at"] = time.time()
        _record_message(msg, source=self.key)

    def _notify_down(self, reason: str) -> None:
        host, port = self.broker.get("host"), self.broker.get("port")
        if self.key == "cloud":
            tip = "可在「能碳一体机与数据源 → 系统连接图 → 云端配置」检查连接信息。"
        else:
            tip = "可在「能碳一体机与数据源 → 数据源接入 → 中间件服务」检查地址与端口。"
        _push_event(f"mqtt-down-{self.key}", "warn", f"{self.label()}：连接异常",
                    f"{host}:{port} {reason}，平台将自动重连。{tip}")

    # ---- 线程 ----
    def _run(self, rev: int) -> None:
        b = self.broker
        host, port = b.get("host", "127.0.0.1"), int(b.get("port", 41883))
        client = self._make_client()
        self.client = client
        if self.key == "cloud":
            _shared._CLIENT = client       # 兼容旧引用（配置热更新/发布）
        _shared._EP_CLIENTS[self.key] = client
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        if b.get("username"):
            client.username_pw_set(b.get("username"), b.get("password") or None)
        while rev == self._rev:
            try:
                client.connect(host, port, keepalive=int(b.get("keepalive", 60)))
                break
            except Exception as e:  # noqa: BLE001
                with _LOCK:
                    st = _shared._EP_STATE.setdefault(self.key, {})
                    st["last_error"] = f"连接失败：{e}"
                self._notify_down(f"无法连接（{e}）")
                for _ in range(10):
                    if rev != self._rev:
                        return
                    time.sleep(0.5)
        try:
            client.loop_forever()
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                st = _shared._EP_STATE.setdefault(self.key, {})
                st["last_error"] = f"订阅异常：{e}"
            _push_event(f"mqtt-loop-{self.key}", "error", f"{self.label()}：订阅异常",
                        f"消息循环异常退出：{e}。平台将自动重启订阅。")
        finally:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def start(self) -> None:
        if not _shared._PAHO_OK:
            with _LOCK:
                st = _shared._EP_STATE.setdefault(self.key, {})
                st["last_error"] = "未安装 paho-mqtt：pip install paho-mqtt"
            return
        if not self.enabled:
            self.stop()
            with _LOCK:
                st = _shared._EP_STATE.setdefault(self.key, {})
                st["connected"] = False
                st["enabled"] = False
                st["last_error"] = "已停用（未订阅）"
            return
        self._rev += 1
        with _LOCK:
            st = _shared._EP_STATE.setdefault(self.key, {})
            st["enabled"] = True
        self._thread = threading.Thread(target=self._run, args=(self._rev,), daemon=True,
                                        name=f"mqtt-source-{self.key}")
        self._thread.start()

    def stop(self) -> None:
        self._rev += 1
        client = self.client
        self.client = None
        _shared._EP_CLIENTS.pop(self.key, None)
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        if self.key == "cloud" and _shared._CLIENT is client:
            _shared._CLIENT = None


_endpoints: Dict[str, _Endpoint] = {}


def _endpoint(key: str) -> _Endpoint:
    ep = _endpoints.get(key)
    if ep is None:
        ep = _Endpoint(key)
        _endpoints[key] = ep
    return ep


# ---------------------------------------------------------------------------
# 对外：启动 / 重启
# ---------------------------------------------------------------------------

def start() -> None:
    """后台线程启动全部订阅端点（main.py 启动时调用一次）。"""
    if not _shared._PAHO_OK:
        _STATE["enabled"] = False
        _STATE["last_error"] = "未安装 paho-mqtt：pip install paho-mqtt"
        _push_event("mqtt-env", "error", "MQTT 实时数据源不可用",
                    "未安装 paho-mqtt，实时数据不可用。请在虚拟环境执行 pip install paho-mqtt 后重启平台。")
        return
    _shared.sync_endpoints()
    with _LOCK:
        _STATE["enabled"] = True
    for key in ("cloud", "middleware"):
        _endpoint(key).start()


def _restart_subscriber() -> None:
    """断开云端订阅端点，按最新配置重启（云端 Broker 配置热更新）。"""
    _shared.sync_endpoints()
    _endpoint("cloud").start()


def restart_middleware() -> None:
    """断开中间件订阅端点，按最新中间件配置重启（中间件地址/Broker 端口热更新）。"""
    _shared.sync_endpoints()
    _endpoint("middleware").start()


def restart_all() -> None:
    """全部端点按最新配置重启（云端 Broker 与中间件配置同时变更时使用）。"""
    _shared.sync_endpoints()
    for key in ("cloud", "middleware"):
        _endpoint(key).start()


# ---------------------------------------------------------------------------
# 兼容导出：旧版模块级回调签名（测试/外部代码直接调用，默认按云端端点处理）
# ---------------------------------------------------------------------------

def _make_client():
    return _endpoint("cloud")._make_client()


def _on_connect(client, userdata, flags, reason_code, *args):
    _endpoint("cloud")._on_connect(client, userdata, flags, reason_code, *args)


def _on_disconnect(client, userdata, flags, reason_code, *args):
    _endpoint("cloud")._on_disconnect(client, userdata, flags, reason_code, *args)


def _on_message(client, userdata, msg):
    _endpoint("cloud")._on_message(client, userdata, msg)
