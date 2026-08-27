"""AI 分析报告生成：基于仿真结果（基线 / 策略 / 前后对比）生成结构化 Markdown 报告。

设计说明：
- 报告骨架与所有数值表格由本地代码生成（保证数字精确、可复现、无幻觉）；
- 「执行摘要结论 / 基线数据洞察 / 策略效果评估 / 优化建议」等分析段落由「报告分析引擎」生成；
- 分析引擎为策略模式（domain/reporting/engines.py）：LLM 撰写优先，无 Key / 超时 / 异常
  时自动回退到确定性模板文案，保证离线可用。新增引擎只需在工厂注册一行，本文件无需改动。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .domain.reporting import create_report_engine
from .domain.reporting.engines import _fmt, _pct  # noqa: F401 —— 渲染与模板共用格式化工具
from .models import SimResult

CO2_UNIT = "tCO₂/h"          # 排放量
STEEL_UNIT = "t/h"           # 钢产量
INTENSITY_UNIT = "kgCO₂/t"   # 吨钢强度
ENERGY_UNIT = "GJ/h"         # 综合能耗
ENERGY_INTENSITY_UNIT = "kgce/t"  # 单位产品综合能耗


# ---------------------------------------------------------------------------
# 数值工具（_fmt/_pct 定义于 domain/reporting/engines.py，模板与渲染共用）
# ---------------------------------------------------------------------------

def _snap(v, digits=2) -> Optional[float]:
    """把数值保留 digits 位小数后返回（供 LLM 上下文与对比计算）。"""
    if v is None:
        return None
    try:
        return round(float(v), digits)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 仿真结果摘要
# ---------------------------------------------------------------------------

def _sim_ctx(sim: Optional[SimResult]) -> Optional[Dict[str, Any]]:
    """提取仿真结果的紧凑上下文（供 LLM 分析段落与模板共用）。"""
    if not sim:
        return None
    t = sim.totals
    units = []
    for u in sim.units:
        units.append({
            "id": u.id,
            "type": u.type,
            "name": u.name,
            "co2_total": _snap(u.co2_total),
            "co2_direct": _snap(u.co2_direct),
            "co2_indirect": _snap(u.co2_indirect),
            "carbon_in": _snap(u.carbon_in),
            "carbon_to_co2": _snap(u.carbon_to_co2),
            "carbon_to_steel": _snap(u.carbon_to_steel),
            "carbon_to_slag": _snap(u.carbon_to_slag),
            "carbon_captured": _snap(u.carbon_captured),
            "steel_output": _snap(u.steel_output),
            "energy_total": _snap(u.energy_total),
            "energy_intensity": _snap(u.energy_intensity, 1),
            "heat": _snap(u.heat),
            "elec": _snap(u.elec),
            "fuel_energy": _snap(u.fuel_energy),
            "breakdown": [
                {
                    "item": it.item,
                    "qty": _snap(it.qty, 3),
                    "qty_unit": it.qty_unit,
                    "basis": it.basis,
                    "formula": it.formula,
                    "co2": _snap(it.co2, 3),
                    "scope": it.scope,
                }
                for it in u.breakdown
            ],
            "notes": list(u.notes or []),
        })
    return {
        "totals": {
            "co2_total": _snap(t.co2_total),
            "co2_direct": _snap(t.co2_direct),
            "co2_indirect": _snap(t.co2_indirect),
            "carbon_in": _snap(t.carbon_in),
            "carbon_to_co2": _snap(t.carbon_to_co2),
            "carbon_to_steel": _snap(t.carbon_to_steel),
            "carbon_to_slag": _snap(t.carbon_to_slag),
            "carbon_captured": _snap(t.carbon_captured),
            "carbon_utilization": _snap(t.carbon_utilization, 4),
            "steel_output": _snap(t.steel_output),
            "intensity": _snap(t.intensity, 1),
            "energy_total": _snap(t.energy_total),
            "energy_intensity": _snap(t.energy_intensity, 1),
            "elec": _snap(t.elec, 1),
            "fuel_energy": _snap(t.fuel_energy, 1),
        },
        "units": units,
    }


def _build_ctx(baseline: SimResult, strategy: Optional[SimResult],
               strategy_name: str = "", strategy_text: str = "",
               ops: Optional[List[Any]] = None,
               understood: Optional[List[str]] = None,
               scenario: str = "") -> Dict[str, Any]:
    """组装统一上下文，模板渲染与 LLM 调用共用同一份数据。"""
    op_list = []
    for o in (ops or []):
        if hasattr(o, "model_dump"):
            op_list.append(o.model_dump())
        elif isinstance(o, dict):
            op_list.append(dict(o))
    return {
        "scenario": scenario,
        "baseline": _sim_ctx(baseline),
        "strategy": _sim_ctx(strategy),
        "strategy_name": strategy_name or "（未命名策略）",
        "strategy_text": strategy_text,
        "ops": op_list,
        "understood": list(understood or []),
    }


# ---------------------------------------------------------------------------
# 对比计算
# ---------------------------------------------------------------------------

def _delta_fields(b_ctx, s_ctx) -> List[Dict[str, Any]]:
    """核心指标对比表行（基线 / 策略 / 变化量 / 变化率）。"""
    if not b_ctx or not s_ctx:
        return []
    bt, st = b_ctx["totals"], s_ctx["totals"]
    rows = []
    spec = [
        ("co2_total", "总排放量", CO2_UNIT, 1),
        ("co2_direct", "直接排放（范围一）", CO2_UNIT, 1),
        ("co2_indirect", "间接排放（范围二）", CO2_UNIT, 1),
        ("intensity", "吨钢碳排放强度", INTENSITY_UNIT, 1),
        ("energy_total", "综合能耗", ENERGY_UNIT, 1),
        ("energy_intensity", "单位产品综合能耗", ENERGY_INTENSITY_UNIT, 1),
        ("carbon_utilization", "碳利用率", "%", 4),
        ("steel_output", "钢产量", STEEL_UNIT, 1),
    ]
    for key, label, unit, digits in spec:
        b, s = bt.get(key), st.get(key)
        if b is None or s is None:
            continue
        diff = s - b
        if key == "carbon_utilization":
            rate = _pct(s - b, b) if b else "-"
            diff_s = f"{diff * 100:+.2f} pp" if diff >= 0 else f"{diff * 100:.2f} pp"
            base_s = f"{b * 100:.2f}%"
            strat_s = f"{s * 100:.2f}%"
        else:
            rate = f"{diff / b * 100:+.1f}%" if b else "-"
            diff_s = f"+{_fmt(diff, digits)}" if diff >= 0 else _fmt(diff, digits)
            base_s, strat_s = _fmt(b, digits), _fmt(s, digits)
        rows.append({
            "key": key, "label": label, "unit": unit,
            "base": b, "strat": s,
            "base_s": base_s, "strat_s": strat_s,
            "diff_s": diff_s, "rate_s": rate,
        })
    return rows


def _unit_delta_rows(b_ctx, s_ctx) -> List[Dict[str, Any]]:
    """工序级减排贡献表：各工序 CO2 变化量降序（减排幅度最大的排最前）。"""
    if not b_ctx or not s_ctx:
        return []
    b_units = {u["id"]: u for u in b_ctx["units"]}
    s_units = {u["id"]: u for u in s_ctx["units"]}
    rows = []
    for uid, bu in b_units.items():
        su = s_units.get(uid)
        if not su:
            continue
        diff = (su["co2_total"] or 0) - (bu["co2_total"] or 0)
        rows.append({
            "name": bu["name"], "type": bu["type"],
            "base": bu["co2_total"] or 0, "strat": su["co2_total"] or 0,
            "diff": diff,
            "rate": f"{diff / bu['co2_total'] * 100:+.1f}%" if bu["co2_total"] else "-",
        })
    rows.sort(key=lambda r: r["diff"])
    return rows


# ---------------------------------------------------------------------------
# Markdown 渲染（骨架 + 数值表由本地代码生成）
# ---------------------------------------------------------------------------

def _render_markdown(ctx: Dict[str, Any], analysis: Dict[str, str],
                     title: str = "", with_appendix: bool = True) -> str:
    b_ctx = ctx["baseline"]
    s_ctx = ctx["strategy"]
    has_strategy = bool(s_ctx)
    scenario = ctx["scenario"]
    b = b_ctx["totals"] if b_ctx else {}
    L: List[str] = []

    # 标题与元信息
    L.append(f"# {title or '工业能碳智控分析报告'}")
    meta = [f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if scenario:
        meta.append(f"**仿真情景**：{scenario}")
    meta.append("**数据来源**：工业能碳智控平台仿真引擎")
    for m in meta:
        L.append(f"> {m}")
    L.append("")

    # 1 执行摘要
    L.append("## 一、执行摘要")
    L.append(analysis.get("summary", ""))
    L.append("")
    if b:
        L.append("| 指标 | 数值 | 单位 |")
        L.append("|---|---|---|")
        L.append(f"| 总排放量 | {_fmt(b.get('co2_total'))} | {CO2_UNIT} |")
        L.append(f"| 其中：直接排放（范围一） | {_fmt(b.get('co2_direct'))} | {CO2_UNIT} |")
        L.append(f"| 其中：间接排放（范围二） | {_fmt(b.get('co2_indirect'))} | {CO2_UNIT} |")
        L.append(f"| 吨钢碳排放强度 | {_fmt(b.get('intensity'))} | {INTENSITY_UNIT} |")
        L.append(f"| 综合能耗 | {_fmt(b.get('energy_total'))} | {ENERGY_UNIT} |")
        L.append(f"| 单位产品综合能耗 | {_fmt(b.get('energy_intensity'))} | {ENERGY_INTENSITY_UNIT} |")
        L.append(f"| 碳利用率 | {b.get('carbon_utilization') * 100 if b.get('carbon_utilization') else 0:.2f}% | - |")
        L.append(f"| 钢产量 | {_fmt(b.get('steel_output'))} | {STEEL_UNIT} |")
        if has_strategy:
            red = _snap(b.get('co2_total', 0) - s_ctx["totals"].get('co2_total', 0), 1)
            red_pct = f"{red / b['co2_total'] * 100:.1f}%" if b.get('co2_total') else "-"
            L.append(f"| 应用策略后预计减排 | {red} | {CO2_UNIT}（减排率 {red_pct}） |")
            e_red = _snap(b.get('energy_total', 0) - s_ctx["totals"].get('energy_total', 0), 1)
            e_pct = f"{e_red / b['energy_total'] * 100:.1f}%" if b.get('energy_total') else "-"
            L.append(f"| 应用策略后预计节能 | {e_red} | {ENERGY_UNIT}（节能率 {e_pct}） |")
        L.append("")

    # 2 基线数据分析
    L.append("## 二、基线数据分析")
    if b:
        L.append(f"基线情景下全厂每小时排放 CO₂ **{_fmt(b.get('co2_total'))} t**，其中直接排放（范围一）"
                 f"**{_fmt(b.get('co2_direct'))} t**（占比 {_pct(b.get('co2_direct'), b.get('co2_total'))}）、"
                 f"间接排放（范围二）**{_fmt(b.get('co2_indirect'))} t**（占比 {_pct(b.get('co2_indirect'), b.get('co2_total'))}）。")
        L.append("")
        L.append("### 2.1 工序排放贡献分布")
        rows = _unit_rows_ctx(b_ctx)
        L.append("| 排名 | 工序 | 类型 | 排放量（tCO₂/h） | 占比 |")
        L.append("|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            L.append(f"| {i} | {r['name']} | {r['type']} | {_fmt(r['co2_total'])} | {_pct(r['co2_total'], b.get('co2_total'))} |")
        L.append("")
        L.append("### 2.2 强度与效率指标")
        L.append(f"- 吨钢碳排放强度：**{_fmt(b.get('intensity'))} kgCO₂/t**；")
        L.append(f"- 单位产品综合能耗：**{_fmt(b.get('energy_intensity'))} kgce/t**；")
        L.append(f"- 碳利用率（固碳占输入碳比例）：**{b.get('carbon_utilization') * 100 if b.get('carbon_utilization') else 0:.2f}%**。")
        L.append("")
        L.append("### 2.3 碳流向分析")
        carbon_in = b.get("carbon_in")
        if carbon_in:
            to_co2 = b.get("carbon_to_co2")
            to_steel = b.get("carbon_to_steel")
            to_slag = b.get("carbon_to_slag")
            captured = b.get("carbon_captured")
            L.append(f"全流程碳输入 **{_fmt(carbon_in, 1)} tC/h**，去向分布：")
            L.append(f"- 氧化成 CO₂ 排放：**{_fmt(to_co2, 1)} tC/h**（占比 {_pct(to_co2, carbon_in)}）；")
            L.append(f"- 进入钢水固碳：**{_fmt(to_steel, 1)} tC/h**（占比 {_pct(to_steel, carbon_in)}）；")
            L.append(f"- 进入炉渣固碳：**{_fmt(to_slag, 1)} tC/h**（占比 {_pct(to_slag, carbon_in)}）；")
            L.append(f"- 被捕集（含利用）：**{_fmt(captured, 1)} tC/h**（占比 {_pct(captured, carbon_in)}）。")
            L.append("")
        L.append("### 2.4 能耗结构与能流分析")
        es_rows = _energy_structure_rows(b_ctx)
        if es_rows:
            L.append(f"基线情景下全厂综合能耗 **{_fmt(b.get('energy_total'))} GJ/h**"
                     f"（其中外购电 **{_fmt(b.get('elec'))} MWh/h**、燃料能耗 **{_fmt(b.get('fuel_energy'))} GJ/h**），结构如下：")
            L.append("")
            L.append("| 能耗构成 | 数值（GJ/h） | 占比 |")
            L.append("|---|---|---|")
            for r in es_rows:
                L.append(f"| {r['label']} | {_fmt(r['value'], 1)} | {r['pct']} |")
            L.append("")
        eu_rows = _unit_energy_rows(b_ctx)
        if eu_rows:
            L.append("各工序能耗分布（按综合能耗降序）：")
            L.append("")
            L.append("| 工序 | 类型 | 产量（t/h） | 电耗（MWh/h） | 燃料能耗（GJ/h） | 综合能耗（GJ/h） | 单位能耗（kgce/t） |")
            L.append("|---|---|---|---|---|---|---|")
            for u in eu_rows:
                L.append(f"| {u['name']} | {u['type']} | {_fmt(u.get('steel_output'))} | "
                         f"{_fmt(u.get('elec'), 2)} | {_fmt(u.get('fuel_energy'))} | "
                         f"{_fmt(u.get('energy_total'))} | {_fmt(u.get('energy_intensity'))} |")
            L.append("")
    L.append(analysis.get("baseline_insight", ""))
    L.append("")

    # 3 使用的策略
    L.append("## 三、使用的策略")
    L.append(f"本次仿真采用的策略为「**{ctx['strategy_name']}**」。")
    if ctx["strategy_text"]:
        L.append("")
        L.append(f"> 策略原文：{ctx['strategy_text']}")
    ops = ctx["ops"]
    understood = ctx["understood"]
    if understood:
        L.append("")
        L.append("**策略意图解析**：")
        for u in understood:
            L.append(f"- {u}")
    if ops:
        L.append("")
        L.append("**策略操作清单**：")
        L.append("| # | 操作 | 对象 | 参数 | 说明 |")
        L.append("|---|---|---|---|---|")
        for i, op in enumerate(ops, 1):
            action = op.get("action") or "-"
            target = op.get("target") or op.get("unit_id") or op.get("unit") or "-"
            param = str(op.get("param", "")) if op.get("param") is not None else "-"
            note = op.get("note") or ""
            if not note and op.get("value") is not None:
                note = f"{param} = {op['value']}（{op.get('mode', 'absolute')}）"
            L.append(f"| {i} | {action} | {target} | {param} | {note or '-'} |")
        L.append("")
    if not has_strategy:
        L.append("")
        L.append("> 说明：本次仅输出基线仿真结果，未应用任何节能减碳策略。可在左侧「策略」资源中输入策略文本并执行仿真，"
                 "再导出包含前后对比的完整报告。")
        L.append("")

    # 4 策略前后对比分析
    L.append("## 四、策略前后对比分析")
    if has_strategy:
        rows = _delta_fields(b_ctx, s_ctx)
        L.append("### 4.1 核心指标对比")
        L.append("| 指标 | 基线 | 应用策略后 | 变化量 | 变化率 |")
        L.append("|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['label']} | {r['base_s']} | {r['strat_s']} | {r['diff_s']} | {r['rate_s']} |")
        L.append("")
        s_totals = s_ctx["totals"]
        b_totals = b_ctx["totals"]
        red = (b_totals.get("co2_total", 0) - s_totals.get("co2_total", 0))
        L.append(f"策略应用后全厂总排放由 **{_fmt(b_totals.get('co2_total'))}** 降至 **{_fmt(s_totals.get('co2_total'))}** {CO2_UNIT}，"
                 f"共减排 **{_fmt(red)}** {CO2_UNIT}（减排率 **{_pct(red, b_totals.get('co2_total'))}**）。")
        L.append("")
        ud = _unit_delta_rows(b_ctx, s_ctx)
        if ud:
            L.append("### 4.2 工序级减排贡献（按减排量排序）")
            L.append("| 工序 | 类型 | 基线（tCO₂/h） | 策略后（tCO₂/h） | 变化量（tCO₂/h） | 变化率 |")
            L.append("|---|---|---|---|---|---|")
            for r in ud:
                diff_s = f"+{_fmt(r['diff'])}" if r["diff"] >= 0 else _fmt(r["diff"])
                L.append(f"| {r['name']} | {r['type']} | {_fmt(r['base'])} | {_fmt(r['strat'])} | {diff_s} | {r['rate']} |")
            L.append("")
        L.append(analysis.get("strategy_eval", ""))
        L.append("")
    else:
        L.append("当前仅存在基线仿真结果，未应用策略，无法进行前后对比。")
        L.append("")

    # 5 结论与建议
    L.append("## 五、分析结论与建议")
    L.append(analysis.get("suggestions", ""))
    L.append("")

    # 6 附录
    if with_appendix:
        L.append("## 附录一：全流程排放与能耗明细")
        rows = _appendix_rows(b_ctx)
        L.append("（按合计排放量降序排列）")
        L.append("")
        L.append(_APPENDIX_HEADER)
        L.append(_APPENDIX_SEP)
        for r in rows:
            L.append(_appendix_line(r))
        L.append("")
        if has_strategy and s_ctx:
            L.append("### 附录一之二：策略应用后全流程明细")
            s_rows = _appendix_rows(s_ctx)
            L.append(_APPENDIX_HEADER)
            L.append(_APPENDIX_SEP)
            for r in s_rows:
                L.append(_appendix_line(r))
            L.append("")
        ledger_md = _ledger_md(b_ctx)
        if ledger_md:
            L.append("## 附录二：工序碳排放核算台账")
            L.append("各工序逐项核算明细（含排放因子与计算公式），可追溯、可复现：")
            L.append("")
            L.append(ledger_md)
        if has_strategy and s_ctx:
            s_ledger_md = _ledger_md(s_ctx)
            if s_ledger_md:
                L.append("## 附录二之二：策略应用后工序核算台账")
                L.append(s_ledger_md)
    L.append("---")
    L.append("> 本报告由数字孪生平台自动生成，分析段落由大语言模型基于仿真数据撰写，仅供参考。")
    return "\n".join(L)


def _unit_rows_ctx(b_ctx) -> List[Dict[str, Any]]:
    if not b_ctx:
        return []
    rows = list(b_ctx["units"])
    rows.sort(key=lambda u: u["co2_total"] or 0, reverse=True)
    return rows


def _energy_structure_rows(b_ctx) -> List[Dict[str, Any]]:
    """全厂能耗结构：外购电力（1 MWh = 3.6 GJ 折标）与燃料能耗占比。"""
    if not b_ctx:
        return []
    t = b_ctx["totals"]
    elec_gj = (t.get("elec") or 0) * 3.6
    fuel = t.get("fuel_energy") or 0
    total = t.get("energy_total") or 0
    rows = [
        {"label": "外购电力（按 1 MWh = 3.6 GJ 折标）", "value": elec_gj, "unit": "GJ/h",
         "pct": _pct(elec_gj, total)},
        {"label": "燃料能耗（固体/液体/气体燃料）", "value": fuel, "unit": "GJ/h",
         "pct": _pct(fuel, total)},
    ]
    rows.sort(key=lambda r: r["value"] or 0, reverse=True)
    return rows


def _unit_energy_rows(b_ctx) -> List[Dict[str, Any]]:
    """各工序能耗分布（按综合能耗降序），含电耗 / 燃料能耗 / 单位能耗。"""
    if not b_ctx:
        return []
    rows = list(b_ctx["units"])
    rows.sort(key=lambda u: u["energy_total"] or 0, reverse=True)
    return rows


def _carbon_route(u: Dict[str, Any]) -> str:
    """工序碳去向摘要：固钢 / 渣 / 捕集（均为 0 时显示 '-'）。"""
    parts = []
    if u.get("carbon_to_steel"):
        parts.append(f"固钢{_fmt(u['carbon_to_steel'], 1)}")
    if u.get("carbon_to_slag"):
        parts.append(f"渣{_fmt(u['carbon_to_slag'], 1)}")
    if u.get("carbon_captured"):
        parts.append(f"捕集{_fmt(u['carbon_captured'], 1)}")
    return "、".join(parts) if parts else "-"


_APPENDIX_HEADER = (
    "| 工序 | 类型 | 产量（t/h） | 直接排放（tCO₂/h） | 间接排放（tCO₂/h） | 合计（tCO₂/h） | "
    "电耗（MWh/h） | 燃料（GJ/h） | 综合能耗（GJ/h） | 单位能耗（kgce/t） | 碳去向（tC/h） |"
)
_APPENDIX_SEP = "|---|---|---|---|---|---|---|---|---|---|---|"


def _appendix_rows(b_ctx) -> List[Dict[str, Any]]:
    """全流程明细行（按合计排放降序）。"""
    if not b_ctx:
        return []
    rows = list(b_ctx["units"])
    rows.sort(key=lambda u: u["co2_total"] or 0, reverse=True)
    return rows


def _appendix_line(r: Dict[str, Any]) -> str:
    return (f"| {r['name']} | {r['type']} | {_fmt(r.get('steel_output'))} | "
            f"{_fmt(r.get('co2_direct'))} | {_fmt(r.get('co2_indirect'))} | {_fmt(r.get('co2_total'))} | "
            f"{_fmt(r.get('elec'), 2)} | {_fmt(r.get('fuel_energy'))} | "
            f"{_fmt(r.get('energy_total'))} | {_fmt(r.get('energy_intensity'))} | "
            f"{_carbon_route(r)} |")


def _ledger_md(ctx_units: Optional[Dict[str, Any]]) -> str:
    """渲染「工序核算台账」章节：每个工序的排放核算明细与工艺说明。"""
    if not ctx_units:
        return ""
    L: List[str] = []
    for u in ctx_units["units"]:
        bd = u.get("breakdown") or []
        if not bd:
            continue
        L.append(f"### {u['name']}（{u['type']}）")
        L.append(f"该工序每小时排放 CO₂ **{_fmt(u.get('co2_total'))} t**"
                 f"（直接 {_fmt(u.get('co2_direct'))} t / 间接 {_fmt(u.get('co2_indirect'))} t），核算明细如下：")
        L.append("")
        L.append("| 核算项 | 用量 | 单位 | 核算依据 | CO₂ 当量（tCO₂/h） | 范围 |")
        L.append("|---|---|---|---|---|---|")
        for it in bd:
            qty_s = _fmt(it.get("qty"), 3) if it.get("qty") else "-"
            unit_s = it.get("qty_unit") or "-"
            co2_s = _fmt(it.get("co2"), 1)
            if it.get("co2") and it.get("co2") < 0:
                co2_s = f"{co2_s}（减排）"
            scope_s = "范围一（直接）" if it.get("scope") == "direct" else "范围二（间接）"
            basis = it.get("basis") or "-"
            if it.get("formula"):
                basis = f"{basis}；{it['formula']}"
            L.append(f"| {it.get('item') or '-'} | {qty_s} | {unit_s} | {basis} | {co2_s} | {scope_s} |")
        notes = u.get("notes") or []
        if notes:
            L.append("")
            L.append(f"> 备注：{'；'.join(notes)}")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 报告正文后处理：剔除提示词/思考链泄漏，统一 Markdown 排版
# ---------------------------------------------------------------------------

# 提示词/思考链泄漏特征：这些是仅供模型阅读的指令或草稿措辞，绝不应出现在交付报告正文中
_LEAK_PATTERNS: tuple = (
    r"我们需要回答", r"我们需要撰写", r"我们需要解读", r"我们需要输出",
    r"我们需要思考", r"我们需要合理", r"我们需",
    r"请撰写报告", r"撰写报告「", r"请输出完整\s*Markdown",
    r"输出完整\s*Markdown报告", r"输出纯\s*Markdown",
    r"用户要求", r"用户说", r"用户禁止", r"根据用户", r"用户提供的事实底稿",
    r"系统提示", r"系统已计算",
    r"硬约束",
    r"事实底稿", r"底稿第",
    r"只输出该段", r"不要输出标题", r"不要重复数据", r"可含短列表",
    r"每段\s*\d+\s*[-~—]\s*\d+\s*字", r"字数要求",
    r"请严格依据", r"请原样使用",
)


def _is_leak_para(para: str) -> bool:
    """判断一段是否为提示词/思考链泄漏（应剔除）。"""
    p = para.strip()
    if not p:
        return False
    if re.search("|".join(_LEAK_PATTERNS), p):
        return True
    # 思考链自指特征：第一人称任务语言 / 草稿标记 / 自我提问
    if re.match(r"^(我们需要|我们需|可能内容|草稿[:：]|先起草|开始起草)", p):
        return True
    if p.count("？") + p.count("?") >= 2:
        return True
    return False


def _polish_report_text(text: str) -> str:
    """清洗提示词/思考链泄漏段落，并统一 Markdown 排版（分段、压缩空行、标题前空行、去行尾空格）。"""
    paras = re.split(r"\n\s*\n", (text or ""))
    kept = [p for p in paras if not _is_leak_para(p)]
    body = "\n\n".join(kept).strip()
    # 排版统一：压缩多余空行、去除行尾空格、标题前保证空行
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"(?<!^)\n(#{1,4}\s)", r"\n\n\1", body)
    return body


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

# 说明：LLM 分析段落（_llm_section / _llm_analysis / _fallback_analysis）
# 已迁移至 domain/reporting/engines.py 并以策略模式（LlmReportEngine /
# TemplateReportEngine / AutoReportEngine）组织，见 generate_report 下方调用。

def generate_report(baseline: SimResult, strategy: Optional[SimResult] = None,
                    strategy_name: str = "", strategy_text: str = "",
                    ops: Optional[List[Dict[str, Any]]] = None,
                    understood: Optional[List[str]] = None,
                    scenario: str = "", title: str = "",
                    engine: str = "auto", depth: str = "standard",
                    with_appendix: bool = True,
                    progress_cb: Optional[Callable[[int, str], None]] = None) -> Dict[str, Any]:
    """生成完整分析报告。

    参数：
    - title: 自定义报告标题（空则使用默认标题）
    - engine: 'auto'（有 LLM 则用 LLM，失败回退模板）| 'llm'（强制 LLM，失败回退模板）| 'template'（确定性模板）
    - depth: 'brief' | 'standard' | 'deep'，控制每段分析字数
    - with_appendix: 是否包含「附录：全流程明细」表格
    - progress_cb(pct, stage): 进度回调（0~100 与阶段标识），用于前端实时展示

    返回 {ok, markdown, engine, generated_at}：
    - engine == 'llm'      分析段落由大模型生成；
    - engine == 'template' 无 LLM 可用，使用确定性模板文案。
    """
    def _p(pct: int, stage: str) -> None:
        if progress_cb:
            progress_cb(pct, stage)

    _p(2, "ctx")
    ctx = _build_ctx(baseline, strategy, strategy_name, strategy_text, ops, understood, scenario)
    # 报告分析引擎（策略模式）：'template' / 'llm' / 'auto'（LLM 优先、失败自动回退模板）
    engine_obj = create_report_engine(engine)
    _p(8, "analyze")
    analysis = engine_obj.build_analysis(ctx, depth=depth, progress_cb=progress_cb)
    if analysis is None:
        # 'llm' 强制模式下 LLM 不可用时的最终兜底
        engine_used = "template"
        _p(40, "template")
        analysis = create_report_engine("template").build_analysis(ctx, depth=depth)
    else:
        engine_used = getattr(engine_obj, "used_engine", engine_obj.name)
    _p(90, "render")
    md = _render_markdown(ctx, analysis, title=title, with_appendix=with_appendix)
    md = _polish_report_text(md)
    return {
        "ok": True,
        "markdown": md,
        "engine": engine_used,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
