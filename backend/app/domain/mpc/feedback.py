"""实时反馈点位：把「当前温度 / 室温 / 水桶温度」接到 MQTT 真实上报。

为什么要走后端而不是前端直接读 WebSocket
------------------------------------
前端 `/api/ws/feed` 推的是**仿真流程里的设备实例**（id 来自场景 model.json），
而 `zhileng-temp / env-temp / shuitong-temp` 是云端设备名（盒子上报的原始设备），
两者只有在「设备关联」表里建立映射后才有交集。机房温控场景目前 model.json 是空的，
走前端通道拿不到这三个点。后端直接读 mqtt_source 的云端设备缓存，与场景无关。

读数口径
--------
只认 MQTT data/# 的实时上报（`CLOUD_DEVICES[*].primary`），不生成任何模拟值 ——
没有上报就是没有，返回 value=null，由页面显示「无上报」，绝不拿旧值/默认值冒充。
`age_s` 超过 `P.FB_STALE_S` 时 online=False（页面标陈旧，但仍返回数值供参考）。
"""
from __future__ import annotations

import time
from typing import Any, Dict

from . import params as P


def _pick_value(info: Dict[str, Any]):
    """从云端设备缓存里取主读数；主读数缺失时退回该设备的字段值。"""
    if not info:
        return None
    v = info.get("primary")
    if v is None:
        fields = info.get("values") or info.get("fields_data") or {}
        if isinstance(fields, dict):
            v = fields.get(P.FB_PROP)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_feedback() -> dict:
    """返回三个反馈点位的当前读数与新鲜度。

    {"ok": true, "stale_s": 60, "sources": {
        "t_now":  {"device": "zhileng-temp",  "value": 25.0, "age_s": 3.2,
                   "ts": "15:17:03", "online": true},
        "tenv":   {...}, "twater": {...}}}
    """
    try:
        from app import mqtt_source          # 延迟导入：MPC 的纯计算部分不依赖 MQTT
        snap = mqtt_source.snapshot_cloud_devices()
        available = True
    except Exception:                        # noqa: BLE001 —— MQTT 模块异常不能让页面崩
        snap, available = {}, False

    now = time.time()
    out: Dict[str, Any] = {}
    for field, device in P.FB_SOURCES.items():
        info = snap.get(device) or {}
        val = _pick_value(info)
        last = info.get("last_seen")
        try:
            last_f = float(last) if last is not None else None
        except (TypeError, ValueError):
            last_f = None
        age = None if last_f is None else round(now - last_f, 1)
        out[field] = {
            "device": device,
            "prop": P.FB_PROP,
            "value": None if val is None else round(val, 2),
            "age_s": age,
            "ts": None if last_f is None else time.strftime("%H:%M:%S", time.localtime(last_f)),
            "online": bool(val is not None and age is not None and age <= P.FB_STALE_S),
        }

    return {
        "ok": True,
        "available": available,
        "stale_s": P.FB_STALE_S,
        "snapshot_ts": time.strftime("%H:%M:%S"),
        "sources": out,
    }


__all__ = ["get_feedback"]
