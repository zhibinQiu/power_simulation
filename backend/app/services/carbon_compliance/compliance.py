"""合规校验：策略输出前强制拦截。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from app.services.carbon_compliance.units import fee_rate_for_channel, trade_cash_cny


@dataclass
class ComplianceIssue:
    code: str
    severity: str  # block | warn
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanAction:
    action: str  # buy_cea | sell_cea | use_ccer | buy_ccer
    qty: float  # 万吨
    unit_price: float = 0.0  # 元/吨
    window: str = ""
    note: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class ComplianceResult:
    ok: bool
    issues: list[ComplianceIssue]
    actions: list[PlanAction]
    total_cost: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
            "actions": [a.to_dict() for a in self.actions],
            "total_cost": self.total_cost,
            "notes": self.notes,
        }


def eligible_ccer_qty(
    holdings: list[dict],
    *,
    as_of: date | None = None,
) -> float:
    """过期与双重权益（linked_green_cert）剔除后的可抵扣量。

    规则：优先用 eligible_qty；若可抵扣为 0 但持有量>0 则回退持有量；
    且可抵扣不得超过持有量（避免台账「可抵扣」未随存量改数而虚高）。
    """
    today = as_of or date.today()
    total = 0.0
    for h in holdings:
        if h.get("linked_green_cert"):
            continue
        exp = h.get("expire_at")
        if exp:
            if isinstance(exp, str):
                exp_d = date.fromisoformat(exp[:10])
            else:
                exp_d = exp
            if exp_d < today:
                continue
        holding_qty = max(0.0, float(h.get("qty") or 0))
        raw_eligible = h.get("eligible_qty")
        if raw_eligible is None:
            qty = holding_qty
        else:
            qty = max(0.0, float(raw_eligible))
            if qty <= 0 and holding_qty > 0:
                qty = holding_qty
            elif holding_qty > 0:
                qty = min(qty, holding_qty)
        total += max(0.0, qty)
    return total


def filter_plan_actions(
    actions: list[PlanAction],
    *,
    ccer_cap: float,
    annual_budget_cap: float,
    single_trade_limit: float,
    large_split_threshold: float,
    listing_fee_rate: float = 0.0,
    block_fee_rate: float = 0.0,
    trade_fee_rate: float = 0.0,
    allow_dual_green_rights: bool = False,
) -> ComplianceResult:
    """合规过滤。手续费按动作渠道选用挂牌/大宗费率：手续费=成交总额×费率。"""
    issues: list[ComplianceIssue] = []
    notes: list[str] = []
    kept: list[PlanAction] = []
    ccer_used = 0.0
    spend = 0.0

    def _fee_rate(a: PlanAction) -> float:
        ch = (a.meta or {}).get("channel")
        if ch:
            return fee_rate_for_channel(
                str(ch),
                listing_fee_rate=listing_fee_rate,
                block_fee_rate=block_fee_rate,
            )
        if a.meta.get("fee_rate") is not None:
            return max(0.0, float(a.meta.get("fee_rate") or 0))
        return max(0.0, float(trade_fee_rate or 0))

    for raw in actions:
        a = PlanAction(
            action=raw.action,
            qty=float(raw.qty or 0),
            unit_price=float(raw.unit_price or 0),
            window=raw.window or "",
            note=raw.note or "",
            meta=dict(raw.meta or {}),
        )
        if a.qty <= 0:
            continue

        if a.action in ("use_ccer", "buy_ccer"):
            if ccer_used + a.qty > ccer_cap + 1e-9:
                allowed = max(0.0, ccer_cap - ccer_used)
                if allowed <= 0:
                    issues.append(
                        ComplianceIssue(
                            code="ccer_cap",
                            severity="block",
                            message=f"CCER 使用量超过合规上限 {ccer_cap:.2f} 万吨，已拦截",
                        )
                    )
                    continue
                notes.append(f"CCER 动作由 {a.qty:.2f} 调整为上限内 {allowed:.2f}")
                a.qty = allowed
            if a.meta.get("expired"):
                issues.append(
                    ComplianceIssue(
                        code="ccer_expired",
                        severity="block",
                        message="过期 CCER 禁止计入抵扣",
                    )
                )
                continue
            if a.meta.get("linked_green_cert") and not allow_dual_green_rights:
                issues.append(
                    ComplianceIssue(
                        code="dual_rights",
                        severity="block",
                        message="同一项目不可同时核发绿证与 CCER 双重权益",
                    )
                )
                continue
            ccer_used += a.qty

        rate = _fee_rate(a)
        a.meta["fee_rate"] = rate
        a.meta["fee_kind"] = (
            "block"
            if "offline" in str(a.meta.get("channel") or "")
            else ("listing" if a.meta.get("channel") else "none")
        )
        # 手续费=成交总额×费率；买入应付=总额+手续费；卖出实收=总额−手续费
        if a.action.startswith("sell"):
            cost = -trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="sell")
        else:
            cost = trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="buy")

        if a.action in ("buy_cea", "buy_ccer", "buy_green_power", "buy_green_cert"):
            if annual_budget_cap > 0 and spend + max(0.0, cost) > annual_budget_cap + 1e-6:
                issues.append(
                    ComplianceIssue(
                        code="budget_cap",
                        severity="block",
                        message=f"采购成本超出年度预算上限 {annual_budget_cap:.2f}",
                    )
                )
                continue
            limit = single_trade_limit
            if limit > 0 and a.qty > limit:
                notes.append(f"单笔 {a.qty:g} 万吨超过限额 {limit:g} 万吨，建议拆分")
                a.meta["split_suggested"] = True
                a.meta["split_size"] = limit
            if large_split_threshold > 0 and a.qty > large_split_threshold:
                a.meta["split_suggested"] = True
                a.meta["split_size"] = large_split_threshold
                notes.append(
                    f"大额交易 {a.qty:g} 万吨建议按 {large_split_threshold:g} 万吨拆分以降低流动性冲击"
                )

        spend += max(0.0, cost)
        kept.append(a)

    blocked = any(i.severity == "block" and i.code in ("budget_cap",) for i in issues)
    # 有拦截但若仍有有效动作则部分通过
    ok = len(kept) > 0 or not actions
    if blocked and not kept:
        ok = False
    total_cost = 0.0
    for a in kept:
        rate = float(a.meta.get("fee_rate") or 0)
        if a.action.startswith("sell"):
            c = -trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="sell")
        else:
            c = trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="buy")
        total_cost += c

    return ComplianceResult(
        ok=ok,
        issues=issues,
        actions=kept,
        total_cost=total_cost,
        notes=notes,
    )
