"""mqtt_source 包：盒子侧状态缓存（state/# 主题解析与查询）。

BOX_SERVICES / BOX_APP_EVENTS 为原地修改的 dict，直接绑定 _shared 引用即可。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from ._shared import BOX_APP_EVENTS, BOX_SERVICES, _LOCK
from .publish import publish


def _record_box_state(topic: str, data: Dict[str, Any]) -> None:
    """解析盒子 state/# 上报：state/{box}/services（运行服务列表）与 state/{box}/deploy（命令结果）。"""
    box = str(data.get("box") or "").strip()
    if not box:
        parts = [p for p in topic.split("/") if p]
        box = parts[1] if len(parts) > 1 else "未分组"
    now = time.time()
    with _LOCK:
        if topic.endswith("/services"):
            services = data.get("services")
            if isinstance(services, list):
                # 归一化：确保每项有 name 字段，缺省补空串（前端容错）
                norm = []
                for s in services:
                    if isinstance(s, dict):
                        item = dict(s)
                        item.setdefault("name", "")
                        norm.append(item)
                    elif isinstance(s, str):
                        norm.append({"name": s})
                BOX_SERVICES[box] = {"services": norm, "last_seen": now}
        elif topic.endswith("/deploy"):
            ev = {
                "request_id": str(data.get("request_id") or ""),
                "cmd": str(data.get("cmd") or ""),
                "name": str(data.get("name") or ""),
                "ok": bool(data.get("ok")),
                "message": str(data.get("message") or ""),
                "detail": data.get("detail"),
                "ts": now,
            }
            BOX_APP_EVENTS.setdefault(box, []).append(ev)
            if len(BOX_APP_EVENTS[box]) > 20:
                del BOX_APP_EVENTS[box][:-20]


def box_services(box: str) -> List[Dict[str, Any]]:
    """查询盒子当前运行的服务/模型列表（无上报返回空列表）。"""
    with _LOCK:
        info = BOX_SERVICES.get(box or "")
        return list((info or {}).get("services") or [])


def box_app_events(box: str) -> List[Dict[str, Any]]:
    """查询盒子最近的应用部署/启停命令结果。"""
    with _LOCK:
        return list(BOX_APP_EVENTS.get(box or "") or [])


def publish_box_cmd(box: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """向盒子下发应用部署/启停指令（MQTT 命令主题 cmd/{box}/deploy）。

    盒子运行期无直达 IP，云端→盒子方向只能经云端 Broker 的 cmd/# 命令主题：
    盒子 mapper 订阅 cmd/{box}/#，收到后执行部署并回报 state/{box}/deploy。
    """
    topic = "cmd/%s/deploy" % (box or "").strip()
    body = dict(payload or {})
    body.setdefault("box", (box or "").strip())
    res = publish(topic, body)
    if res.get("ok"):
        res["topic"] = topic
    return res
