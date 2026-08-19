"""实时遥测传输层：WebSocket 推送 + 监测设备历史时序（内存 ring buffer）。

把"长连接推送"与"设备历史采样"这一传输/状态关切从 main.py 的 REST 路由中拆出，
main.py 只需调用 register_realtime(app) 即可挂载，保持路由层精简。

职责：
- FeedManager：维护当前活跃 WebSocket 连接。
- DEVICE_HISTORY / DEVICE_META：每个监测设备最近读数的内存环形缓冲（约 10 分钟）。
- ws_feed：客户端连接后发送 {type:'model'} 设定当前流程，服务端每秒推送带噪声的实时遥测。
- seed_history：流程变更/启动时回填设备历史基线，保证前端首屏即有趋势数据。
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from .carbon_engine import cached_simulate
from .models import ProcessModel
from .presets import default_model


class FeedManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)


manager = FeedManager()

# --------------------- 监测设备历史时序（内存 ring buffer） ---------------------
# 每个设备维护一条最近读数序列（秒级采样），用于前端「历史数据 / 实时变化」图表。
# 设备读数 = 由活动数据算出的基准读数 × 时间噪声（模拟真实仪表抖动）。
DEVICE_HISTORY: Dict[str, List[Dict[str, float]]] = defaultdict(list)  # dev_id -> [{t, v}]
DEVICE_META: Dict[str, Dict[str, Any]] = {}                            # dev_id -> 设备元数据
HISTORY_MAX = 600                                                     # 约 10 分钟（1Hz）


def _noise(v: float, pct: float = 0.04) -> float:
    return max(0.0, v * (1 + random.uniform(-pct, pct)))


def _device_meta(unit_id: str, unit_name: str, unit_type: str, d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": d["id"], "unit_id": unit_id, "unit_name": unit_name, "unit_type": unit_type,
        "label": d.get("label"), "type": d.get("type"), "unit": d.get("unit"),
        "color": d.get("color"), "icon": d.get("icon"), "measured": d.get("measured"),
        "accuracy": d.get("accuracy"), "range": d.get("range"), "feeds": d.get("feeds"),
    }


def seed_history(model: "ProcessModel") -> None:
    """为当前流程的所有内置设备回填一段历史（启动时/流程变更时调用）。"""
    sim = cached_simulate(model)
    now = time.time()
    for u in sim.units:
        base_readings = {d["id"]: (d.get("reading") or 0.0) for d in (u.devices or [])}
        for d in (u.devices or []):
            did = d["id"]
            base = base_readings[did]
            pts = []
            for i in range(180, 0, -1):
                v = max(0.0, base * (1 + random.uniform(-0.05, 0.05)))
                pts.append({"t": now - i, "v": round(v, 3)})
            pts.append({"t": now, "v": round(base, 3)})
            DEVICE_HISTORY[did] = pts[-HISTORY_MAX:]
            DEVICE_META[did] = _device_meta(u.id, u.name, u.type, d)


def _record_devices(sim: "Any") -> List[Dict[str, Any]]:
    """每个遥测 tick：采样设备读数、追加历史、返回本 tick 的实时设备读数。"""
    out: List[Dict[str, Any]] = []
    now = time.time()
    for u in sim.units:
        for d in (u.devices or []):
            did = d["id"]
            base = d.get("reading") or 0.0
            v = max(0.0, base * (1 + random.uniform(-0.04, 0.04)))
            buf = DEVICE_HISTORY[did]
            buf.append({"t": now, "v": round(v, 3)})
            if len(buf) > HISTORY_MAX:
                DEVICE_HISTORY[did] = buf[-HISTORY_MAX:]
            DEVICE_META[did] = _device_meta(u.id, u.name, u.type, d)
            out.append({
                "id": did, "unit_id": u.id, "label": d.get("label"),
                "type": d.get("type"), "reading": round(v, 2), "unit": d.get("unit"),
            })
    return out


async def ws_feed(ws: WebSocket):
    """实时遥测 WebSocket：客户端设定流程后，每秒推送带噪声的遥测帧。"""
    await manager.connect(ws)
    model = default_model()
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                msg = _safe_json(raw)
                if msg.get("type") == "model" and msg.get("model"):
                    model = ProcessModel(**msg["model"])
                    seed_history(model)        # 流程变更 -> 重建设备历史基线
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
            sim = cached_simulate(model)
            device_readings = _record_devices(sim)
            payload = {
                "type": "telemetry",
                "total_co2": _noise(sim.totals.co2_total),
                "intensity": _noise(sim.totals.intensity),
                "steel_output": sim.totals.steel_output,
                "units": [
                    {"id": u.id, "name": u.name, "co2_total": _noise(u.co2_total),
                     "energy_total": _noise(u.energy_total),   # 3D 标签「先能后碳」需实时能耗
                     "heat": u.heat, "type": u.type}
                    for u in sim.units
                ],
                "devices": device_readings,
            }
            try:
                await ws.send_json(payload)
            except Exception:
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


def _safe_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def register_realtime(app) -> None:
    """把实时遥测相关路由挂载到 FastAPI 应用（在 main.py 中调用一次）。"""
    @app.websocket("/api/ws/feed")
    async def _ws_feed(ws: WebSocket):
        await ws_feed(ws)

    @app.get("/api/devices/history")
    def get_device_history():
        """返回所有内置监测设备的历史读数序列与元数据，供前端绘制趋势图。"""
        return {"history": dict(DEVICE_HISTORY), "meta": DEVICE_META}
