"""履约与市场风险预警。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.services.carbon_compliance.carry_forward import CarryForwardResult


def _parse_deadline(year: int, md: str) -> date:
    try:
        month_s, day_s = md.split("-")
        return date(year, int(month_s), int(day_s))
    except Exception:
        return date(year, 12, 31)


def build_alerts(
    *,
    compliance_year: int,
    clearance_deadline_md: str,
    warn_days: list[int],
    compliance_gap: float,
    ccer_used: float,
    ccer_cap: float,
    price_band: str,
    as_of: date | None = None,
    carry_forward: CarryForwardResult | None = None,
) -> list[dict[str, Any]]:
    today = as_of or date.today()
    deadline = _parse_deadline(compliance_year, clearance_deadline_md or "12-31")
    days_left = (deadline - today).days

    alerts: list[dict[str, Any]] = []
    sorted_warn = sorted([int(d) for d in (warn_days or [90, 30, 15])], reverse=True)
    if compliance_gap > 0:
        for d in sorted_warn:
            if 0 <= days_left <= d:
                level = "critical" if d <= 15 else ("warning" if d <= 30 else "info")
                alerts.append(
                    {
                        "level": level,
                        "alert_type": "clearance_countdown",
                        "message": (
                            f"距清缴截止（{deadline.isoformat()}）剩 {days_left} 天，"
                            f"履约缺口约 {compliance_gap:.2f} 万吨，请尽快补足资产"
                        ),
                        "due_at": datetime(
                            deadline.year, deadline.month, deadline.day, tzinfo=timezone.utc
                        ),
                    }
                )
                break

    if carry_forward and carry_forward.excess > 1e-9 and carry_forward.deadline:
        carry_days = (carry_forward.deadline - today).days
        if carry_days <= 90:
            level = "critical" if carry_days <= 15 else ("warning" if carry_days <= 45 else "info")
            alerts.append(
                {
                    "level": level,
                    "alert_type": "carry_forward_excess",
                    "message": (
                        f"超额配额约 {carry_forward.excess:.2f} 万吨不可长期囤积；"
                        f"最大可结转 {carry_forward.max_carry:.2f} 万吨"
                        f"（基础+净卖出×{carry_forward.net_sell_multiplier:g}），"
                        f"请在结转日 {carry_forward.deadline.isoformat()} 前卖出变现"
                        f"或提前卖出约 {carry_forward.sell_to_expand_cap:.2f} 万吨以扩大可结转存量，"
                        f"否则超额到期失效"
                        + (
                            f"（距结转日 {carry_days} 天）"
                            if carry_days >= 0
                            else "（已过结转日）"
                        )
                    ),
                    "due_at": datetime(
                        carry_forward.deadline.year,
                        carry_forward.deadline.month,
                        carry_forward.deadline.day,
                        tzinfo=timezone.utc,
                    ),
                }
            )

    if price_band == "high":
        alerts.append(
            {
                "level": "warning",
                "alert_type": "price_spike",
                "message": "CEA 价格处于历史高位区间，关注采购成本与卖出窗口",
                "due_at": None,
            }
        )
    elif price_band == "low":
        alerts.append(
            {
                "level": "info",
                "alert_type": "price_low",
                "message": "CEA 价格处于历史低位区间，缺口企业可考虑分批采购",
                "due_at": None,
            }
        )

    if ccer_used > ccer_cap + 1e-6:
        alerts.append(
            {
                "level": "critical",
                "alert_type": "ccer_over_cap",
                "message": f"CCER 计划用量 {ccer_used:.2f} 超过合规上限 {ccer_cap:.2f}",
                "due_at": None,
            }
        )

    return alerts
