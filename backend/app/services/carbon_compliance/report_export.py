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
    compliance_year: int | str,
    accounting: dict[str, Any],
    market_tags: dict[str, Any],
    plans: list[dict[str, Any]],
) -> str:
    # 全年度（传入字符串「全年度」）时不带「年」字；具体年度显示「YYYY 年」
    year_label = compliance_year if str(compliance_year) == "全年度" else f"{compliance_year} 年"
    traded_buy = float(accounting.get("traded_buy_qty") or 0)
    traded_sell = float(accounting.get("traded_sell_qty") or 0)
    traded_line = ""
    if traded_buy or traded_sell:
        # 可用 CEA 已含流水：买入加、卖出减，这里把两笔拆开写清楚，避免「免费 CEA」被误读成纯免费额度
        traded_line = f"（免费 {float(accounting.get('allocated_free_cea', 0) or 0):.2f} + 买入 {traded_buy:.2f} − 卖出 {traded_sell:.2f}）"
    gap_net = float(accounting.get("compliance_gap", 0) or 0)
    ccer_offset = float(accounting.get("own_ccer_usable", 0) or 0)
    # 旧快照没有 gap_before_ccer，用「净缺口 + 已抵扣量」回推，避免显示成 0
    gap_raw = accounting.get("gap_before_ccer")
    gap_gross = float(gap_raw) if gap_raw is not None else gap_net + ccer_offset
    ccer_ratio = float(accounting.get("ccer_max_ratio") or 0.05)
    lines = [
        f"# {enterprise_name} {year_label}碳履约策略推荐",
        "",
        "## 核算快照",
        "",
        f"- 最终核查排放：{float(accounting.get('verified_emission', 0) or 0):.2f} 万吨 CO₂e",
        f"- 可用 CEA：{float(accounting.get('free_cea_quota', 0) or 0):.2f} 万吨{traded_line}",
        f"- 抵扣前缺口：{gap_gross:.2f} 万吨（核查排放 − 可用 CEA）",
        f"- CCER 抵销上限：{float(accounting.get('ccer_cap', 0) or 0):.2f} 万吨"
        f"（应清缴配额 = 核查排放 {float(accounting.get('verified_emission', 0) or 0):.2f} × {ccer_ratio * 100:.0f}%）",
        f"- 台账可抵扣 CCER：{float(accounting.get('own_ccer_eligible', 0) or 0):.2f} 万吨",
        f"- 本履约可动用 CCER：{ccer_offset:.2f} 万吨",
        f"- 履约缺口/富余（已扣 CCER）：{gap_net:.2f} 万吨",
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
        total_cost = float(p.get("total_cost") or 0)
        planned_cost = p.get("planned_cost")
        lines.append(f"- 总成本测算：{total_cost:.2f} 元")
        if planned_cost is not None and abs(float(planned_cost) - total_cost) > 0.5:
            # total_cost 只统计通过合规过滤的动作；被拦下的部分单独披露
            lines.append(f"- 拦截前计划成本：{float(planned_cost):.2f} 元")
        lines.append(f"- 净节约：{float(p.get('net_saving') or 0):.2f} 元")
        lines.append(f"- 操作窗口：{zh(TIME_WINDOW_LABELS, p.get('time_window'))}")
        comp = p.get("compliance") or {}
        for issue in comp.get("issues") or []:
            lines.append(
                f"- 合规提示（{issue.get('severity') or '-'}）：{issue.get('message') or ''}"
            )
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
