"""内置 Skills：查询设备、仿真、碳市场、排放因子等本系统能力。

这些 Skill 使用 MCP Tool 的 JSON Schema 定义入参，既能被 LangGraph 智能体
直接调用，也会通过 MCP Server（mcp_server.py）以 MCP 协议对外暴露。
handler 均为同步函数，返回可 JSON 化的对象；SkillRegistry 统一转文本。

注意：所有数据源模块延迟导入（函数体内），避免顶层循环依赖。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import Skill

logger = logging.getLogger(__name__)


def _query_realtime_devices(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询所有设备的实时读数（来自云端 MQTT）与全厂汇总。"""
    from app import mqtt_source
    from app.carbon_engine import cached_simulate
    from app.presets import default_model

    sim = cached_simulate(default_model())
    devices: List[Dict[str, Any]] = []
    for u in sim.units:
        for d in (u.devices or []):
            did = d["id"]
            v = mqtt_source.resolve_reading(did)
            devices.append({
                "id": did,
                "unit": u.name,
                "unit_type": u.type,
                "name": d.get("name") or d.get("label") or did,
                "type": d.get("type", ""),
                "value": v,
                "unit_text": d.get("unit_text") or d.get("unit") or "",
            })
    return {
        "summary": {
            "total_co2_t": round(sim.totals.co2_total, 3),
            "intensity_t_co2_per_t_steel": round(sim.totals.intensity, 4),
            "energy_total": round(sim.totals.energy_total, 1),
            "energy_unit": getattr(sim.totals, "energy_unit", "GJ"),
        },
        "devices": devices,
    }


def _query_device_history(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询设备历史读数序列。args: {device_id?, limit?}。"""
    from app.realtime import DEVICE_HISTORY, DEVICE_META

    device_id = (args.get("device_id") or "").strip()
    limit = int(args.get("limit") or 20)
    if limit < 1:
        limit = 20
    if device_id:
        hist = DEVICE_HISTORY.get(device_id, [])
        meta = DEVICE_META.get(device_id, {})
        return {"device_id": device_id, "meta": meta,
                "history": hist[-limit:] if hist else []}
    out = {}
    for did, series in DEVICE_HISTORY.items():
        out[did] = {"meta": DEVICE_META.get(did, {}), "history": series[-limit:]}
    return {"devices": out}


def _run_simulation(args: Dict[str, Any]) -> Dict[str, Any]:
    """运行当前工艺流程模型仿真，返回各工序能耗/碳与全厂汇总。"""
    from app.carbon_engine import cached_simulate
    from app.presets import default_model

    sim = cached_simulate(default_model())
    units = []
    for u in sim.units:
        units.append({
            "id": u.id, "name": u.name, "type": u.type,
            "energy": round(u.energy_total, 1),
            "heat": round(u.heat, 1),
            "device_count": len(u.devices or []),
        })
    return {
        "summary": {
            "total_co2_t": round(sim.totals.co2_total, 3),
            "co2_direct_t": round(getattr(sim.totals, "co2_direct", 0.0), 3),
            "co2_indirect_t": round(getattr(sim.totals, "co2_indirect", 0.0), 3),
            "intensity_t_co2_per_t_steel": round(sim.totals.intensity, 4),
            "energy_total": round(sim.totals.energy_total, 1),
            "energy_unit": getattr(sim.totals, "energy_unit", "GJ"),
        },
        "units": units,
    }


def _get_carbon_market_quote(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询碳市场最新行情（CEA/CCER 最新价、涨跌幅、月聚合）。"""
    from app.carbon_market import fetch_quotes

    quotes = fetch_quotes()
    return {"quotes": quotes}


def _get_carbon_forecast(args: Dict[str, Any]) -> Dict[str, Any]:
    """碳价预测。args: {instrument?: cea|ccer, days?: 默认10, method?: linear|moving_average}。"""
    from app.carbon_market import forecast_series

    instrument = (args.get("instrument") or "cea").strip() or "cea"
    if instrument not in ("cea", "ccer"):
        instrument = "cea"
    try:
        days = int(args.get("days") or 10)
    except (TypeError, ValueError):
        days = 10
    days = max(1, min(days, 60))
    method = (args.get("method") or "linear").strip() or "linear"
    if method not in ("linear", "moving_average"):
        method = "linear"
    return forecast_series(instrument=instrument, days=days, method=method)


def _get_emission_factors(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询当前排放因子表（各燃料/电力的 CO2 排放因子）。"""
    from app.factors import default_factors

    return {"factors": default_factors()}


def _query_knowledge(args: Dict[str, Any]) -> Dict[str, Any]:
    """知识库全文检索。args: {query: str, limit?: int}。"""
    from app.services import knowledge_service as kb

    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "缺少检索关键词 query"}
    try:
        limit = max(1, min(int(args.get("limit") or 5), 10))
    except (TypeError, ValueError):
        limit = 5
    data = kb.search(query)
    results = []
    for r in (data.get("results") or [])[:limit]:
        doc = r.get("doc") or {}
        results.append({
            "doc_id": doc.get("id", ""),
            "title": doc.get("title", ""),
            "folder": doc.get("path", "/"),
            "snippet": (r.get("snippet") or "")[:200],
        })
    return {"ok": True, "query": query, "count": len(results), "results": results}


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

def register_builtin_skills(registry) -> None:
    """把全部内置 skills 注册到给定 SkillRegistry。"""
    skills = [
        Skill(
            name="query_realtime_devices",
            description=(
                "查询所有监测设备的实时读数（数据来自云端 MQTT 上报，非模拟）"
                "与全厂汇总：总 CO2 排放、吨钢强度、总能耗。无入参。"
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_query_realtime_devices,
            source="builtin",
            tags=["device", "realtime"],
        ),
        Skill(
            name="query_device_history",
            description=(
                "查询监测设备的历史读数序列（内存中最近若干采样点）。"
                "入参 device_id 可选，缺省返回所有设备。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "设备实例 id，如 ctw1，缺省查全部"},
                    "limit": {"type": "integer", "description": "每个设备最多返回的采样点数，默认 20"},
                },
            },
            handler=_query_device_history,
            source="builtin",
            tags=["device", "history"],
        ),
        Skill(
            name="run_simulation",
            description=(
                "运行当前钢铁工艺流程模型仿真，返回各工序能耗/热耗/设备数量"
                "与全厂汇总（总 CO2、直接/间接排放、吨钢强度、总能耗）。无入参。"
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_run_simulation,
            source="builtin",
            tags=["simulation"],
        ),
        Skill(
            name="get_carbon_market_quote",
            description=(
                "查询全国碳市场最新行情：CEA/CCER 最新成交价、涨跌幅、成交量"
                "与月度聚合统计。无入参，数据来自交易所官方接口。"
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_get_carbon_market_quote,
            source="builtin",
            tags=["carbon", "market"],
            timeout=20.0,   # 联网拉取交易所行情，超时保护
        ),
        Skill(
            name="get_carbon_forecast",
            description=(
                "基于历史收盘价对碳价做未来若干交易日的预测（外推），"
                "返回预测序列与置信区间。入参：instrument=cea|ccer，days=预测天数，"
                "method=linear|moving_average。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "instrument": {"type": "string", "enum": ["cea", "ccer"], "description": "品种，默认 cea"},
                    "days": {"type": "integer", "description": "预测交易天数，默认 10"},
                    "method": {"type": "string", "enum": ["linear", "moving_average"],
                               "description": "预测方法，默认 linear"},
                },
            },
            handler=_get_carbon_forecast,
            source="builtin",
            tags=["carbon", "forecast"],
            timeout=25.0,   # 依赖历史行情联网拉取，超时保护
        ),
        Skill(
            name="get_emission_factors",
            description=(
                "查询当前排放因子表：各燃料（焦炭/煤/天然气/生物质等）、外购电"
                "与其它含碳物料的 CO2 排放因子。无入参。"
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_get_emission_factors,
            source="builtin",
            tags=["carbon", "factors"],
        ),
        Skill(
            name="query_knowledge",
            description=(
                "在企业知识库中全文检索文档（工艺手册、标准规范、政策文件、"
                "技术资料等）。入参 query 为检索关键词，可选 limit 控制返回条数。"
                "当用户询问平台内置知识库内容或需引用文档资料作答时使用。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词（必填）"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 5，最大 10"},
                },
                "required": ["query"],
            },
            handler=_query_knowledge,
            source="builtin",
            tags=["knowledge"],
        ),
    ]
    for s in skills:
        registry.register(s)
