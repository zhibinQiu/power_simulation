"""mqtt_source 包：MQTT 订阅客户端生命周期（唯一 client_id + 断线自动重连 1s→30s 退避）。

start() 由 main.py 启动时调用一次；update_config 经 _restart_subscriber 热重启。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict

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


def _restart_subscriber() -> None:
    """断开当前订阅客户端，按最新配置重启（Broker 配置热更新）。"""
    with _LOCK:
        client = _shared._CLIENT
        _shared._CLIENT = None
    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass
    start()


def _make_client():
    cid = f"{_shared._BROKER.get('client_id', 'carbon-sim-collector')}-{os.getpid()}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=True)
    except TypeError:
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        except TypeError:
            return mqtt.Client(client_id=cid)


def _on_connect(client, userdata, flags, reason_code, *args):
    if isinstance(reason_code, int):
        rc = reason_code
    else:
        rc = reason_code.value if hasattr(reason_code, "value") else reason_code
    with _LOCK:
        was_down = not _STATE["connected"]
        _STATE["connected"] = rc == 0
        _STATE["last_connect_rc"] = rc
        _STATE["last_error"] = "" if rc == 0 else f"连接失败 rc={rc}"
    if rc == 0:
        for t in _shared._TOPICS:
            client.subscribe(t, qos=int(_shared._BROKER.get("qos", 0)))
        # 额外订阅 $SYS/# 收集 Broker 统计（实时仪表盘数据源，参照 dashboard.py）
        client.subscribe("$SYS/#", qos=0)
        # 仅在「从断开/失败状态恢复」时提示成功，正常保持连接不打扰
        if was_down:
            _push_event("mqtt-up", "success", "MQTT 实时数据源已连接",
                        f"Broker {_shared._BROKER.get('host')}:{_shared._BROKER.get('port')} 连接成功，"
                        "实时数据持续更新。")
    else:
        _push_event("mqtt-down", "warn", "MQTT 数据源连接失败",
                    f"Broker 连接失败 rc={rc}，平台将自动重试。可在「能碳一体机管理 → 总览 → 配置 Broker」检查连接信息。")


def _on_disconnect(client, userdata, flags, reason_code, *args):
    with _LOCK:
        _STATE["connected"] = False
        _STATE["last_error"] = f"连接断开 rc={reason_code}"
    _push_event("mqtt-down", "warn", "MQTT 数据源连接断开",
                "与 Broker 的连接已断开，平台正在自动重连，恢复后数据自动同步。")


def _on_message(client, userdata, msg):
    _record_message(msg)


def start() -> None:
    """后台线程启动 MQTT 订阅（main.py 启动时调用一次）。"""
    if not _shared._PAHO_OK:
        _STATE["last_error"] = "未安装 paho-mqtt：pip install paho-mqtt"
        _push_event("mqtt-env", "error", "MQTT 数据源不可用",
                    "未安装 paho-mqtt，实时数据不可用。请在虚拟环境执行 pip install paho-mqtt 后重启平台。")
        return

    def _run():
        with _LOCK:
            _STATE["enabled"] = True
        client = _make_client()
        with _LOCK:
            _shared._CLIENT = client   # 供配置热更新（update_config）断开重连
        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        username = _shared._BROKER.get("username", "")
        password = _shared._BROKER.get("password", "")
        if username:
            client.username_pw_set(username, password or None)
        host = _shared._BROKER.get("host", "127.0.0.1")
        port = int(_shared._BROKER.get("port", 41883))
        while True:
            try:
                client.connect(host, port, keepalive=int(_shared._BROKER.get("keepalive", 60)))
                break
            except Exception as e:
                with _LOCK:
                    _STATE["last_error"] = f"连接失败：{e}"
                _push_event("mqtt-down", "warn", "MQTT 数据源连接失败",
                            f"无法连接 Broker {host}:{port}（{e}），平台将每 5 秒自动重试，"
                            "数据恢复后自动同步。")
                time.sleep(5)
        try:
            client.loop_forever()
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                _STATE["last_error"] = f"订阅异常：{e}"
            _push_event("mqtt-loop", "error", "MQTT 订阅异常",
                        f"消息循环异常退出：{e}。平台将自动重启订阅。")
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="mqtt-source").start()
