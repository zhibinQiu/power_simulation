"""策略运行结果导出为 Markdown。"""

from __future__ import annotations

from typing import Any

from app.services.carbon_compliance.labels import (
    ACTION_TAG_LABELS,
    PRICE_BAND_LABELS,
    TIME_WINDOW_LABELS,
    plan_action_zh,
    zh,
)


def strategy_run_to_markdown(
    *,
    enterprise_name: str,
    compliance_year: int,
    accounting: dict[str, Any],
    market_tags: dict[str, Any],
    plans: list[dict[str, Any]],
) -> str:
    lines = [
        f"# {enterprise_name} {compliance_year} 年碳履约策略推荐",
        "",
        "## 核算快照",
        "",
        f"- 最终核查排放：{float(accounting.get('verified_emission', 0) or 0):.2f} 万吨 CO₂e",
        f"- 免费 CEA：{float(accounting.get('free_cea_quota', 0) or 0):.2f} 万吨",
        f"- 履约缺口/富余：{float(accounting.get('compliance_gap', 0) or 0):.2f} 万吨",
        f"- CCER 合规上限：{float(accounting.get('ccer_cap', 0) or 0):.2f} 万吨",
        f"- 台账可抵扣 CCER：{float(accounting.get('own_ccer_eligible', 0) or 0):.2f} 万吨",
        f"- 本履约可动用 CCER：{float(accounting.get('own_ccer_usable', 0) or 0):.2f} 万吨",
        "",
        "## 市场周期",
        "",
        f"- 价格带：{zh(PRICE_BAND_LABELS, market_tags.get('price_band'))}",
        f"- 时间窗口：{zh(TIME_WINDOW_LABELS, market_tags.get('time_window'))}",
        f"- 建议动作：{zh(ACTION_TAG_LABELS, market_tags.get('action_tag'))}",
        f"- 说明：{market_tags.get('rationale') or ''}",
        "",
        "## 分层推荐方案",
        "",
    ]
    for p in plans:
        lines.append(f"### {p.get('title') or p.get('key')}")
        lines.append("")
        lines.append(p.get("description") or "")
        lines.append("")
        lines.append(f"- 总成本测算：{float(p.get('total_cost') or 0):.2f}")
        lines.append(f"- 净节约：{float(p.get('net_saving') or 0):.2f}")
        lines.append(f"- 操作窗口：{zh(TIME_WINDOW_LABELS, p.get('time_window'))}")
        comp = p.get("compliance") or {}
        if comp.get("notes"):
            lines.append(f"- 合规备注：{'; '.join(comp['notes'])}")
        lines.append("")
        lines.append("| 动作 | 数量(万吨) | 单价(元/吨) | 窗口 | 说明 |")
        lines.append("|------|------|------|------|------|")
        for a in p.get("actions") or []:
            lines.append(
                f"| {plan_action_zh(a.get('action'))} | {float(a.get('qty') or 0):.2f} | "
                f"{float(a.get('unit_price') or 0):.2f} | "
                f"{zh(TIME_WINDOW_LABELS, a.get('window'))} | "
                f"{(a.get('note') or '').replace('|', '/')} |"
            )
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("本报告由确定性规则引擎生成，不构成投资或合规承诺，请结合最新政策复核。")
    return "\n".join(lines)
