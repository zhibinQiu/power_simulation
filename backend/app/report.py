"""AI 分析报告生成：基于仿真结果（基线 / 策略 / 前后对比）生成结构化 Markdown 报告。

设计说明：
- 报告骨架与所有数值表格由本地代码生成（保证数字精确、可复现、无幻觉）；
- 「执行摘要结论 / 基线数据洞察 / 策略效果评估 / 优化建议」等分析段落由大语言模型撰写，
  大模型只负责基于给定数据的解读与建议，不参与数字计算；
- 无 LLM Key / 超时 / 输出异常时自动回退到确定性文案，保证离线可用。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .llm_strategy import chat_completion
from .models import SimResult

_ENGINE_LLM = "llm"
_ENGINE_TEMPLATE = "template"

CO2_UNIT = "tCO₂/h"          # 排放量
STEEL_UNIT = "t/h"           # 钢产量
INTENSITY_UNIT = "kgCO₂/t"   # 吨钢强度
ENERGY_UNIT = "GJ/h"         # 综合能耗
ENERGY_INTENSITY_UNIT = "kgce/t"  # 单位产品综合能耗


# ---------------------------------------------------------------------------
# 数值工具
# ---------------------------------------------------------------------------

def _fmt(v, digits=1) -> str:
    """格式化数值：空值显示 '-', 否则保留 digits 位小数并加千分位。"""
    if v is None:
        return "-"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _pct(part, whole) -> str:
    """百分比字符串（分母为 0 或空返回 '-'）。"""
    if not whole:
        return "-"
    try:
        return f"{float(part) / float(whole) * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


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
    L.append(f"# {title or '行业能碳仿真分析报告'}")
    meta = [f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if scenario:
        meta.append(f"**仿真情景**：{scenario}")
    meta.append("**数据来源**：行业能碳仿真平台仿真引擎")
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
        L.append("## 附录：全流程明细")
        rows = _unit_rows_ctx(b_ctx)
        L.append("| 工序 | 类型 | 直接排放（tCO₂/h） | 间接排放（tCO₂/h） | 合计（tCO₂/h） | 单位能耗（kgce/t） |")
        L.append("|---|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['name']} | {r['type']} | {_fmt(r['co2_direct'])} | {_fmt(r['co2_indirect'])} | {_fmt(r['co2_total'])} | {_fmt(r.get('energy_intensity'))} |")
        L.append("")
    L.append("---")
    L.append("> 本报告由数字孪生平台自动生成，分析段落由大语言模型基于仿真数据撰写，仅供参考。")
    return "\n".join(L)


def _unit_rows_ctx(b_ctx) -> List[Dict[str, Any]]:
    if not b_ctx:
        return []
    rows = list(b_ctx["units"])
    rows.sort(key=lambda u: u["co2_total"] or 0, reverse=True)
    return rows


# ---------------------------------------------------------------------------
# LLM 分析段落
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "你是钢铁行业节能减碳领域的资深数据分析专家，负责为「行业能碳仿真平台」的仿真结果撰写分析报告。"
    "你只根据给定的仿真数据撰写分析，绝不编造任何数字，也不要计算具体数值（数值全部由系统计算）。"
    "所有单位按上下文说明理解（CO2 为 tCO2/h、强度为 kgCO2/t、能耗为 GJ/h、单位能耗为 kgce/t）。"
    "输出简体中文，专业、精炼、结构清晰。"
)


# 分析深度 → 每段字数要求与单次 LLM 输出上限
_DEPTH_SPEC: Dict[str, Dict[str, Any]] = {
    "brief":    {"chars": "每段 80~150 字", "max_tokens": 600},
    "standard": {"chars": "每段 150~300 字", "max_tokens": 900},
    "deep":     {"chars": "每段 300~500 字", "max_tokens": 1600},
}


def _llm_section(ctx: Dict[str, Any], key: str, title: str, instruction: str,
                 spec: Dict[str, Any]) -> Optional[str]:
    """单段独立调用大模型；成功返回正文文本，失败返回 None。"""
    prompt = (
        "以下是数字孪生平台的一次仿真结果（JSON）：\n"
        f"```json\n{json.dumps(ctx, ensure_ascii=False, indent=1)}\n```\n\n"
        f"请撰写报告「{title}」这一段（{spec['chars']}，简体中文，Markdown 正文，可含短列表）。\n"
        f"{instruction}\n"
        "只输出该段正文内容，不要输出标题、序号或 JSON，也不要重复数据表格。"
    )
    messages = [
        {"role": "system", "content": _LLM_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = chat_completion(messages, timeout=90.0, max_tokens=spec["max_tokens"])
    except Exception:
        return None
    if not raw:
        return None
    text = raw.strip()
    # 去掉可能残留的 Markdown 围栏与标题行
    text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.M)
    text = re.sub(r"\s*```\s*$", "", text).strip()
    text = re.sub(r"^#+\s+.*\n", "", text).strip()
    return text or None


def _llm_analysis(ctx: Dict[str, Any], depth: str = "standard",
                  progress_cb: Optional[Callable[[int, str], None]] = None) -> Optional[Dict[str, str]]:
    """分段调用大模型生成 4 段分析文本，每完成一段回调进度。

    单段失败时用确定性文案补充该段；全部失败返回 None（由调用方整体回退）。
    """
    spec = _DEPTH_SPEC.get(depth, _DEPTH_SPEC["standard"])
    has_strategy = bool(ctx["strategy"])

    def _p(pct: int, stage: str) -> None:
        if progress_cb:
            progress_cb(pct, stage)

    strategy_inst = (
        ("评估策略「%s」的实施效果：核心指标变化、主要节能与减排来源工序、"
         "强度与能耗改善程度，并评估策略合理性。" % ctx["strategy_name"])
        if has_strategy else
        "本次未应用策略，请基于基线数据说明当前无策略对照、建议应用策略后对比，并简述可尝试的策略方向。"
    )
    sections = [
        ("summary", "执行摘要",
         "一句话概述整体能耗与排放水平与最关键发现，可给出综合能耗、总排放与强度水平结论。", 8, 25),
        ("baseline_insight", "基线数据分析洞察",
         "解读排放结构（直接/间接占比）、主要排放工序与贡献、强度与能耗效率、能流与碳流向特征，指出主要节能与减排机会点。", 28, 45),
        ("strategy_eval", "策略效果评估", strategy_inst, 48, 65),
        ("suggestions", "结论与优化建议",
         "给出 3~5 条具体、可落地的后续节能减碳建议（可结合工序类型、碳流向、能流与能耗结构等），"
         "使用短列表，并说明预期关注点。", 68, 82),
    ]
    fallback = _fallback_analysis(ctx)
    out: Dict[str, str] = {}
    for key, title, instruction, p0, p1 in sections:
        _p(p0, f"llm_{key}")
        try:
            text = _llm_section(ctx, key, title, instruction, spec)
        except Exception:
            text = None
        out[key] = text or fallback.get(key, "")
        _p(p1, f"llm_{key}")
    if not any(v for v in out.values()):
        return None
    return out


def _fallback_analysis(ctx: Dict[str, Any]) -> Dict[str, str]:
    """确定性兜底文案：无 LLM Key / 调用失败时使用。"""
    b_ctx = ctx["baseline"]
    s_ctx = ctx["strategy"]
    has_strategy = bool(s_ctx)
    b = b_ctx["totals"] if b_ctx else {}
    top = ""
    if b_ctx:
        rows = sorted(b_ctx["units"], key=lambda u: u["co2_total"] or 0, reverse=True)
        if rows:
            first = rows[0]
            top = (f"排放最大的工序为 **{first['name']}**（{_fmt(first['co2_total'])} tCO₂/h，"
                   f"占全厂 {_pct(first['co2_total'], b.get('co2_total'))}），是减排优先关注对象。")
    summary = (
        f"基线情景下全厂总排放为 **{_fmt(b.get('co2_total'))} tCO₂/h**，"
        f"吨钢碳排放强度 **{_fmt(b.get('intensity'))} kgCO₂/t**。{top}"
    )
    baseline_insight = (
        f"直接排放占全厂 {_pct(b.get('co2_direct'), b.get('co2_total'))}、间接排放占 "
        f"{_pct(b.get('co2_indirect'), b.get('co2_total'))}；碳利用率 "
        f"{b.get('carbon_utilization') * 100 if b.get('carbon_utilization') else 0:.2f}%。"
        f"{top}建议后续围绕主要排放工序推进余热回收、燃料替代与能效优化。"
    )
    if has_strategy:
        s = s_ctx["totals"]
        red = (b.get("co2_total", 0) - s.get("co2_total", 0))
        strategy_eval = (
            f"策略「{ctx['strategy_name']}」应用后全厂减排 **{_fmt(red)} tCO₂/h**"
            f"（减排率 {_pct(red, b.get('co2_total'))}），吨钢强度由 {_fmt(b.get('intensity'))} 降至 "
            f"{_fmt(s.get('intensity'))} kgCO₂/t。整体效果显著，建议结合工序级贡献进一步微调参数。"
        )
    else:
        strategy_eval = "本次未应用策略，暂无前后对照；建议输入策略文本并执行仿真后再导出对比报告。"
    suggestions = (
        "- 优先对排放占比最大的工序开展节能改造与工艺优化；\n"
        "- 提高煤气/余热回收利用率，降低综合能耗与单位产品能耗；\n"
        "- 结合碳捕集与利用技术提升碳利用率；\n"
        "- 定期运行策略仿真，量化各类减排措施的边际效果后择优实施。"
    )
    return {
        "summary": summary,
        "baseline_insight": baseline_insight,
        "strategy_eval": strategy_eval,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

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
    engine_used = _ENGINE_LLM
    if engine == _ENGINE_TEMPLATE:
        _p(40, "template")
        analysis = _fallback_analysis(ctx)
        engine_used = _ENGINE_TEMPLATE
    else:
        analysis = _llm_analysis(ctx, depth=depth, progress_cb=progress_cb)
        if analysis is None:
            engine_used = _ENGINE_TEMPLATE
            _p(40, "template")
            analysis = _fallback_analysis(ctx)
    _p(90, "render")
    md = _render_markdown(ctx, analysis, title=title, with_appendix=with_appendix)
    return {
        "ok": True,
        "markdown": md,
        "engine": engine_used,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
