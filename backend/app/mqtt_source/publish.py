"""mqtt_source 包：Broker 统计 / 测试发布 / 连接状态查询。

publish 使用独立短连接客户端（唯一 client_id），不影响主订阅线程。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict

from . import _shared
from ._shared import (BROKER_STATS, CLOUD_DEVICES, MESSAGE_LOG, READINGS,
                      _LOCK, _STATE, mqtt)


def broker_stats() -> Dict[str, Any]:
    """Broker 实时统计（来自 $SYS/broker/#，实时仪表盘数据源）。"""
    with _LOCK:
        return dict(BROKER_STATS)


def publish(topic: str, payload: Any) -> Dict[str, Any]:
    """向云端 Broker 发一条测试消息（参照 dashboard.py 的 /api/publish）。

    使用独立短连接客户端发布，不影响主订阅线程。
    等待连接就绪后再发布，并校验 publish 返回值，避免「假成功」（消息未发出却返回 ok）。
    """
    if not _shared._PAHO_OK:
        return {"ok": False, "error": "未安装 paho-mqtt：pip install paho-mqtt"}
    pc = None
    try:
        # 独立唯一 client_id：与订阅线程区分，避免相同 client_id 将订阅线程踢下线（MQTT 协议约定）
        _cid = f"{_shared._BROKER.get('client_id', 'carbon-sim-collector')}-pub-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        try:
            pc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=_cid, clean_session=True)
        except TypeError:
            pc = mqtt.Client(client_id=_cid, clean_session=True)
        username = _shared._BROKER.get("username", "")
        password = _shared._BROKER.get("password", "")
        if username:
            pc.username_pw_set(username, password or None)

        connected = threading.Event()
        published = threading.Event()
        pub_rc = {"rc": -1}

        def _on_connect(client, userdata, flags, *args):
            connected.set()

        def _on_publish(client, userdata, mid, *args):
            pub_rc["rc"] = 0
            published.set()

        pc.on_connect = _on_connect
        pc.on_publish = _on_publish

        pc.connect(_shared._BROKER.get("host", "127.0.0.1"),
                   int(_shared._BROKER.get("port", 41883)), 60)
        pc.loop_start()
        if not connected.wait(timeout=5):
            return {"ok": False, "error": "连接云端 Broker 超时（5s）"}
        info = pc.publish(topic,
                          payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                          qos=int(_shared._BROKER.get("qos", 0)))
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return {"ok": False, "error": f"发布失败 rc={info.rc}"}
        published.wait(timeout=5)  # 等 on_publish 确认真正发出（qos0 发送后立即回调）
        return {"ok": True, "topic": topic}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        if pc is not None:
            try:
                pc.loop_stop()
                pc.disconnect()
            except Exception:  # noqa: BLE001
                pass


def get_status() -> Dict[str, Any]:
    with _LOCK:
        st = dict(_STATE)
        st["readings_count"] = len(READINGS)
        st["recent_messages"] = list(MESSAGE_LOG[-20:])
        st["topics"] = list(_shared._TOPICS)
        st["broker_host"] = _shared._BROKER.get("host")
        st["broker_port"] = _shared._BROKER.get("port")
        st["mapping"] = dict(_shared._MAPPING)
        st["broker_stats"] = dict(BROKER_STATS)
        st["cloud_devices"] = [
            {
                "id": c,
                "box": d.get("box"),
                "topic": d.get("topic"),
                "last_seen": d.get("last_seen"),
                "primary": d.get("primary"),
                "fields": list(d.get("fields") or {}),
            }
            for c, d in sorted(CLOUD_DEVICES.items(),
                               key=lambda kv: kv[1].get("last_seen") or 0, reverse=True)
        ]
        st["links"] = [{"cloud_id": c, "local_id": l} for c, l in _shared._LINKS.items()]
        st["ignored_devices"] = sorted(_shared._IGNORED_DEVICES)
    return st
