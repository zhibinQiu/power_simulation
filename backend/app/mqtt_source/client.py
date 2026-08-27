"""mqtt_source 包：MQTT 订阅客户端生命周期（唯一 client_id + 断线自动重连 1s→30s 退避）。

start() 由 main.py 启动时调用一次；update_config 经 _restart_subscriber 热重启。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict

from . import _shared
from ._shared import _LOCK, _STATE, mqtt
from .ingest import _record_message


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
        _STATE["connected"] = rc == 0
        _STATE["last_connect_rc"] = rc
        _STATE["last_error"] = "" if rc == 0 else f"连接失败 rc={rc}"
    print(f"[mqtt_source] connect rc={rc} broker={_shared._BROKER.get('host')}:{_shared._BROKER.get('port')}",
          flush=True)
    if rc == 0:
        for t in _shared._TOPICS:
            client.subscribe(t, qos=int(_shared._BROKER.get("qos", 0)))
            print(f"[mqtt_source] subscribe {t}", flush=True)
        # 额外订阅 $SYS/# 收集 Broker 统计（实时仪表盘数据源，参照 dashboard.py）
        client.subscribe("$SYS/#", qos=0)
        print("[mqtt_source] subscribe $SYS/#", flush=True)


def _on_disconnect(client, userdata, flags, reason_code, *args):
    with _LOCK:
        _STATE["connected"] = False
        _STATE["last_error"] = f"连接断开 rc={reason_code}"
    print(f"[mqtt_source] disconnect rc={reason_code}（将自动重连）", flush=True)


def _on_message(client, userdata, msg):
    _record_message(msg)


def start() -> None:
    """后台线程启动 MQTT 订阅（main.py 启动时调用一次）。"""
    if not _shared._PAHO_OK:
        _STATE["last_error"] = "未安装 paho-mqtt：pip install paho-mqtt"
        print(f"[mqtt_source] {_STATE['last_error']}", flush=True)
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
        while True:
            try:
                client.connect(_shared._BROKER.get("host", "127.0.0.1"),
                               int(_shared._BROKER.get("port", 41883)),
                               keepalive=int(_shared._BROKER.get("keepalive", 60)))
                break
            except Exception as e:
                with _LOCK:
                    _STATE["last_error"] = f"连接失败：{e}"
                print(f"[mqtt_source] retry connect -> {e}", flush=True)
                time.sleep(5)
        print(f"[mqtt_source] running topics={_shared._TOPICS}", flush=True)
        try:
            client.loop_forever()
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                _STATE["last_error"] = f"订阅异常：{e}"
            print(f"[mqtt_source] loop error -> {e}", flush=True)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="mqtt-source").start()
