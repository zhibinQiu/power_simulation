"""内置 Skills：查询设备、仿真、碳市场、排放因子等本系统能力。

这些 Skill 使用 MCP Tool 的 JSON Schema 定义入参，既能被 LangGraph 智能体
直接调用，也会通过 MCP Server（mcp_server.py）以 MCP 协议对外暴露。
handler 均为同步函数，返回可 JSON 化的对象；SkillRegistry 统一转文本。

注意：所有数据源模块延迟导入（函数体内），避免顶层循环依赖。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import Skill

logger = logging.getLogger(__name__)

# 量程文本解析（如 "0–6000 t/h"、"0–5e6 m³/h"）
_RANGE_NUM = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
# 中文疑问/助词，用于把整句提问切成分词检索词
_STOP_CHARS = set("的了吗呢啊吧怎样如何怎么哪些多少怎么把被让给于和与及或是这那个些有没")


def _split_search_terms(query: str) -> List[str]:
    """把中文整句切成 ≥2 字检索词：先按标点拆，再按停用字切分，最后补 4~6 字滑动窗口。"""
    terms: List[str] = []
    parts = [p for p in re.split(r"[\s,，。、;；:：!！?？]+", query or "") if p]
    for part in parts:
        cur = ""
        for ch in part:
            if ch in _STOP_CHARS:
                if len(cur) >= 2:
                    terms.append(cur)
                cur = ""
            else:
                cur += ch
        if len(cur) >= 2:
            terms.append(cur)
    # 滑动窗口兜底：如「高炉节能减碳」拆不出子串时，补 4/5/6 字窗口提高命中
    seen = set(terms)
    for part in parts:
        clean = "".join(ch for ch in part if ch not in _STOP_CHARS)
        for width in (4, 5, 6):
            for i in range(0, max(0, len(clean) - width + 1)):
                w = clean[i:i + width]
                if w not in seen:
                    seen.add(w)
                    terms.append(w)
    return terms


def _range_bounds(range_str: Optional[str]) -> Optional[Tuple[float, float]]:
    """从量程文本提取 (下界, 上界)；无法解析返回 None。"""
    nums = [float(x) for x in _RANGE_NUM.findall(range_str or "")]
    if not nums:
        return None
    return min(nums), max(nums)


def _device_status(value: Optional[float], range_str: Optional[str]) -> str:
    """设备健康判定：no_data（无上报）/ abnormal（超量程）/ ok。"""
    if value is None:
        return "no_data"
    bounds = _range_bounds(range_str)
    if bounds:
        lo, hi = bounds
        if value < lo or value > hi * 1.05:   # 上界留 5% 容差
            return "abnormal"
    return "ok"


def _query_realtime_devices(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询所有设备的实时读数（来自云端 MQTT）与全厂汇总，并给出每台设备健康状态。"""
    from app import mqtt_source
    from app.carbon_engine import cached_simulate
    from app.presets import default_model

    sim = cached_simulate(default_model())
    devices: List[Dict[str, Any]] = []
    counts = {"ok": 0, "abnormal": 0, "no_data": 0}
    for u in sim.units:
        for d in (u.devices or []):
            did = d["id"]
            v = mqtt_source.resolve_reading(did)
            status = _device_status(v, d.get("range") or "")
            counts[status] += 1
            devices.append({
                "id": did,
                "unit": u.name,
                "name": d.get("name") or d.get("label") or did,
                "type": d.get("type", ""),
                "value": v,
                "unit_text": d.get("unit_text") or d.get("unit") or "",
                "status": status,
            })
    return {
        "summary": {
            "total_co2_t": round(sim.totals.co2_total, 3),
            "intensity_t_co2_per_t_steel": round(sim.totals.intensity, 4),
            "energy_total": round(sim.totals.energy_total, 1),
            "energy_unit": getattr(sim.totals, "energy_unit", "GJ"),
            "device_status": {
                "total": len(devices), "ok": counts["ok"],
                "abnormal": counts["abnormal"], "no_data": counts["no_data"],
                "note": "ok=读数正常；abnormal=超量程；no_data=未上报（未关联云端/MQTT断连）",
            },
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
    """运行当前工艺流程模型仿真，返回各工序能耗/碳/占比与全厂汇总。"""
    from app.carbon_engine import cached_simulate
    from app.presets import default_model

    sim = cached_simulate(default_model())
    total_co2 = float(sim.totals.co2_total) or 1.0
    units = []
    for u in sim.units:
        share = (u.co2_total / total_co2 * 100.0) if u.co2_total else 0.0
        units.append({
            "id": u.id, "name": u.name, "type": u.type,
            "energy": round(u.energy_total, 1),
            "heat": round(u.heat, 1),
            "co2_direct_t": round(u.co2_direct, 3),
            "co2_indirect_t": round(u.co2_indirect, 3),
            "co2_total_t": round(u.co2_total, 3),
            "co2_share_pct": round(share, 1),
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
            "process_shares": [
                {"name": u["name"], "type": u["type"],
                 "co2_total_t": u["co2_total_t"], "share_pct": u["co2_share_pct"]}
                for u in units
            ],
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
    """知识库全文检索（整串未命中时自动拆词回退检索）。args: {query: str, limit?: int}。"""
    from app.services import knowledge_service as kb

    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "缺少检索关键词 query"}
    try:
        limit = max(1, min(int(args.get("limit") or 5), 10))
    except (TypeError, ValueError):
        limit = 5
    data = kb.search(query)
    hits = list(data.get("results") or [])
    if not hits:
        # 整串未命中：拆成 ≥2 字的词分别检索后去重合并
        terms = _split_search_terms(query)
        seen: Dict[str, Dict[str, Any]] = {}
        for t in terms:
            for r in kb.search(t).get("results") or []:
                doc = r.get("doc") or {}
                seen.setdefault(doc.get("id", ""), r)
        hits = list(seen.values())
    results = []
    for r in hits[:limit]:
        doc = r.get("doc") or {}
        results.append({
            "doc_id": doc.get("id", ""),
            "title": doc.get("title", ""),
            "folder": doc.get("path", "/"),
            "snippet": (r.get("snippet") or "")[:200],
        })
    return {"ok": True, "query": query, "count": len(results), "results": results}


def _summarize_plant_emissions(args: Dict[str, Any]) -> Dict[str, Any]:
    """估算今年以来全厂累计 CO2 排放、能源消耗与钢产量（仿真速率 × 运行时长）。"""
    from app.carbon_engine import cached_simulate
    from app.presets import default_model

    sim = cached_simulate(default_model())
    totals = sim.totals

    # 运行时长：优先入参；缺省 = 今年已过天数 × 24h × 平均负荷率（估算口径）
    hours = args.get("hours")
    hours_note = "估算运行时长 = 今年已过天数 × 24h × 平均负荷率"
    load_factor = 0.85
    try:
        load_factor = float(args.get("load_factor") or 0.85)
        load_factor = max(0.0, min(1.0, load_factor))
    except (TypeError, ValueError):
        pass
    if hours is None:
        days_passed = datetime.now().timetuple().tm_yday
        hours = days_passed * 24.0 * load_factor
    else:
        try:
            hours = max(0.0, float(hours))
        except (TypeError, ValueError):
            hours = 0.0
        hours_note = "入参运行时长（小时）"

    co2_rate = float(totals.co2_total)          # t/h
    energy_rate = float(totals.energy_total)    # GJ/h
    steel_rate = float(totals.steel_output)     # t/h
    co2_ytd = co2_rate * hours
    energy_ytd_gj = energy_rate * hours
    energy_ytd_tce = energy_ytd_gj * 34.12 / 1000.0   # 1 GJ = 34.12 kgce
    steel_ytd = steel_rate * hours

    return {
        "ok": True,
        "method": "plant_emissions_ytd",
        "as_of": datetime.now().date().isoformat(),
        "hours": round(hours, 1),
        "hours_note": hours_note,
        "load_factor": load_factor,
        "rates_per_hour": {
            "co2_t": round(co2_rate, 3),
            "energy_gj": round(energy_rate, 1),
            "steel_t": round(steel_rate, 1),
        },
        "ytd": {
            "co2_total_t": round(co2_ytd, 0),
            "energy_total_gj": round(energy_ytd_gj, 0),
            "energy_total_tce": round(energy_ytd_tce, 0),
            "steel_total_t": round(steel_ytd, 0),
        },
        "intensity_t_co2_per_t_steel": round(float(totals.intensity), 2),
        "calculation_note": {
            "summary": "按当前仿真瞬时速率 × 估算运行时长，推算今年以来全厂累计排放与能耗。",
            "steps": [
                f"瞬时速率：CO2 {co2_rate:.2f} t/h、能耗 {energy_rate:.1f} GJ/h、钢产量 {steel_rate:.1f} t/h",
                f"运行时长 = {hours:.0f} 小时（{hours_note}）",
                f"累计 CO2 = {co2_rate:.2f} × {hours:.0f} = {co2_ytd:.0f} 吨",
                f"累计能耗 = {energy_rate:.1f} × {hours:.0f} = {energy_ytd_gj:.0f} GJ（≈{energy_ytd_tce:.0f} tce）",
            ],
            "assumptions": [
                "估算值 = 仿真瞬时速率 × 运行时长，实际累计以计量表计/台账数据为准",
                "负荷率影响默认运行时长：可传 hours 覆盖，或传 load_factor 调整",
            ],
        },
    }


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
            name="summarize_plant_emissions",
            description=(
                "【统计·全厂累计排放能耗】估算今年以来工厂累计 CO2 排放、能源消耗"
                "（GJ/吨标准煤）与钢产量，并给出吨钢碳排放强度。"
                "基于当前工艺仿真的瞬时速率（t/h、GJ/h）× 估算运行时长；"
                "默认运行时长 = 今年已过天数 × 24h × 平均负荷率（0.85），"
                "可用 hours 覆盖、用 load_factor 调整负荷率。"
                "结果为估算值，实际累计以计量表计/台账为准。"
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "hours": {"type": "number", "description": "累计运行时长（小时），可选，缺省按今年已过天数估算"},
                    "load_factor": {"type": "number", "description": "平均负荷率（0~1），默认 0.85"},
                },
            },
            handler=_summarize_plant_emissions,
            source="builtin",
            tags=["carbon", "energy", "statistics"],
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
