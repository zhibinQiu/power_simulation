"""策略推荐引擎：CEA + CCER 履约动作 → 三套分层方案。

绿电/绿证为国家强制/披露路径，不纳入本引擎推荐。
公开侧无实时挂单，价格以日均/预测价为锚，采购优先建议线下撮合。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.carbon_compliance.accounting import AccountingResult
from app.services.carbon_compliance.carry_forward import CarryForwardResult
from app.services.carbon_compliance.compliance import PlanAction, filter_plan_actions
from app.services.carbon_compliance.defaults import deep_merge, default_settings
from app.services.carbon_compliance.market_cycle import MarketCycleResult
from app.services.carbon_compliance.units import (
    cash_cny,
    fee_rate_for_channel,
    resolve_fee_rates,
    trade_cash_cny,
)


PLAN_SPECS = (
    ("min_cost", "最低成本履约方案", "仅 CEA+CCER 满足清缴刚需，优先线下撮合降本"),
    ("optimized", "成本优化综合方案", "CEA+CCER + 择时窗口，线下优先、线上挂牌兜底"),
    ("full_compliance", "稳健履约方案", "CEA+CCER 全覆盖，含囤存/出售等画像允许动作"),
)


@dataclass
class StrategyContext:
    risk_profile: str
    annual_budget_cap: float
    single_trade_limit: float
    settings: dict
    accounting: AccountingResult
    market: MarketCycleResult
    cea_price: float
    ccer_price: float
    sellable_cea: float
    # 预测/锚定的「当日」参考价（非实时挂单）
    cea_price_predicted: float | None = None
    ccer_price_predicted: float | None = None
    carry_forward: CarryForwardResult | None = None


def _profile(settings: dict, risk: str) -> dict:
    profiles = settings.get("strategy_profiles") or {}
    base = (default_settings()["strategy_profiles"]).get(risk) or {}
    return deep_merge(base, profiles.get(risk) or {})


def _channel_cfg(settings: dict) -> dict:
    base = (default_settings().get("channel") or {})
    return deep_merge(base, settings.get("channel") or {})


def _ref_price(listed: float, predicted: float | None) -> float:
    """无挂单时：优先用预测/当日锚定价，否则用最新日均。"""
    if predicted is not None and predicted > 0:
        return float(predicted)
    return float(listed or 0)


def _offline_unit_price(listed_or_predicted: float, channel: dict) -> tuple[float, dict]:
    """假定线下撮合较公开参考价更便宜，返回用于成本估算的单价与 meta。"""
    prefer = bool(channel.get("prefer_offline", True))
    discount = float(channel.get("offline_discount_vs_listed") or 0.0)
    discount = max(0.0, min(0.3, discount))
    base = float(listed_or_predicted or 0)
    if prefer and discount > 0 and base > 0:
        offline = round(base * (1.0 - discount), 4)
        return offline, {
            "channel": "offline_preferred",
            "listed_ref_price": base,
            "offline_assumed_price": offline,
            "offline_discount": discount,
            "price_basis": "predicted_or_daily_avg_not_orderbook",
        }
    return base, {
        "channel": "listed_fallback",
        "listed_ref_price": base,
        "price_basis": "predicted_or_daily_avg_not_orderbook",
    }


def _channel_note(meta: dict, instrument: str) -> str:
    if meta.get("channel") == "offline_preferred":
        d = float(meta.get("offline_discount") or 0) * 100
        ref = meta.get("listed_ref_price")
        off = meta.get("offline_assumed_price")
        return (
            f"优先尝试线下撮合采购{instrument}"
            f"（假定较公开参考价低约 {d:.1f}%："
            f"参考 {ref} → 线下估 {off} 元/吨）；"
            f"公开侧无实时挂单，价格为日均/预测锚定，线上挂牌作兜底"
        )
    return (
        f"公开侧无实时挂单，{instrument} 价格为日均/预测锚定；"
        f"若无法线下成交再走线上挂牌"
    )


def _build_core_actions(ctx: StrategyContext) -> list[PlanAction]:
    acc = ctx.accounting
    mkt = ctx.market
    prof = _profile(ctx.settings, ctx.risk_profile)
    channel = _channel_cfg(ctx.settings)
    listing_fee, block_fee = resolve_fee_rates(ctx.settings.get("cost"))
    actions: list[PlanAction] = []

    cea_ref = _ref_price(ctx.cea_price, ctx.cea_price_predicted)
    ccer_ref = _ref_price(ctx.ccer_price, ctx.ccer_price_predicted)

    # 优先消耗自有 CCER
    if acc.own_ccer_usable > 0:
        actions.append(
            PlanAction(
                action="use_ccer",
                qty=acc.own_ccer_usable,
                unit_price=0.0,
                window=mkt.time_window,
                note="优先全额消耗自有存量 CCER（不涉及市场渠道）",
            )
        )

    residual = acc.residual_gap_after_own_ccer
    spread = mkt.cea_ccer_spread
    if spread is None:
        spread = cea_ref - ccer_ref

    # 跨品种：价差大且允许外购时填满合规上限
    room = max(0.0, acc.ccer_cap - acc.own_ccer_usable)
    if (
        residual > 0
        and room > 0
        and prof.get("allow_buy_external_ccer")
        and spread is not None
        and spread > max(5.0, cea_ref * 0.05)
    ):
        buy_ccer = min(room, residual)
        unit, meta = _offline_unit_price(ccer_ref, channel)
        actions.append(
            PlanAction(
                action="buy_ccer",
                qty=buy_ccer,
                unit_price=unit,
                window="mid" if mkt.price_band != "high" else "early",
                note=(
                    "CEA-CCER 价差较大，外购 CCER 填满合规上限以降本；"
                    + _channel_note(meta, "CCER")
                ),
                meta=meta,
            )
        )
        residual -= buy_ccer

    # 配额买卖
    if residual > 0:
        unit, meta = _offline_unit_price(cea_ref, channel)
        fee = fee_rate_for_channel(
            meta.get("channel"),
            listing_fee_rate=listing_fee,
            block_fee_rate=block_fee,
        )
        if mkt.price_band == "high" and mkt.time_window != "late":
            actions.append(
                PlanAction(
                    action="buy_cea",
                    qty=residual,
                    unit_price=unit,
                    window="late",
                    note=(
                        "价格高位，建议延后至更合适窗口采购；临近清缴仍须兜底；"
                        + _channel_note(meta, "CEA")
                    ),
                    meta=meta,
                )
            )
        else:
            note = "价格低位分批采购" if mkt.price_band == "low" else "按履约缺口采购配额"
            if mkt.time_window == "late":
                penalty = float((ctx.settings.get("cost") or {}).get("overdue_penalty_per_t") or 200)
                buy_cost = trade_cash_cny(residual, unit, fee_rate=fee, side="buy")
                penalty_cost = cash_cny(residual, penalty)
                note += f"；高价采购约 {buy_cost:.0f} vs 罚款约 {penalty_cost:.0f}"
            note += "；" + _channel_note(meta, "CEA")
            actions.append(
                PlanAction(
                    action="buy_cea",
                    qty=residual,
                    unit_price=unit,
                    window=mkt.time_window,
                    note=note,
                    meta=meta,
                )
            )
    elif residual < 0:
        surplus = abs(residual)
        sell_cap = ctx.sellable_cea if ctx.sellable_cea > 0 else surplus
        sell_qty = min(surplus, sell_cap)
        carry = ctx.carry_forward
        excess = float(carry.excess) if carry else 0.0
        deadline_label = (
            carry.deadline.isoformat()
            if carry and carry.deadline
            else (carry.deadline_md if carry else "06-10")
        )

        if excess > 1e-9:
            # 超额不可长期囤积：结转日前卖出变现，或提前卖出扩净卖出以抬高结转上限
            unit, meta = _offline_unit_price(cea_ref, channel)
            sell_unit = cea_ref
            expand = float(carry.sell_to_expand_cap) if carry else excess / 2.5
            prefer_sell = min(excess, sell_cap) if sell_cap > 0 else excess
            note = (
                f"预计年末持仓约 {carry.year_end_holding:g} 万吨，"
                f"最大可结转 {carry.max_carry:g} 万吨"
                f"（基础 {carry.base_qty:g} + 净卖出 {carry.net_sell:g}×{carry.net_sell_multiplier:g}），"
                f"超额 {excess:g} 万吨须在结转日 {deadline_label} 前处置；"
                f"可直接卖出超额变现，或至少再卖约 {expand:g} 万吨以提高净卖出、扩大可结转存量，"
                f"否则超额到期失效"
            )
            actions.append(
                PlanAction(
                    action="sell_cea",
                    qty=prefer_sell,
                    unit_price=sell_unit,
                    window="early" if mkt.time_window == "late" else mkt.time_window,
                    note=note + f"；参考价 {sell_unit} 元/吨",
                    meta={
                        **meta,
                        "channel": "offline_preferred_sell",
                        "listed_ref_price": sell_unit,
                        "carry_excess": excess,
                        "carry_deadline": deadline_label,
                    },
                )
            )
        elif prof.get("allow_sell_surplus") and mkt.price_band == "high" and sell_qty > 0:
            # 出售：线下也可能更优，但卖出侧仍用参考价估算收入
            unit, meta = _offline_unit_price(cea_ref, channel)
            # 出售时假定线下成交价不低于参考价的保守口径：用参考价
            sell_unit = cea_ref
            actions.append(
                PlanAction(
                    action="sell_cea",
                    qty=sell_qty,
                    unit_price=sell_unit,
                    window=mkt.time_window,
                    note=(
                        "价格高位，分批卖出富余配额；"
                        "可优先线下撮合寻找买方，公开挂牌作兜底"
                        f"（参考价 {sell_unit} 元/吨，非实时挂单）"
                    ),
                    meta={**meta, "channel": "offline_preferred_sell", "listed_ref_price": sell_unit},
                )
            )
        elif prof.get("allow_stockpile") and mkt.price_band == "low":
            unit, meta = _offline_unit_price(cea_ref, channel)
            actions.append(
                PlanAction(
                    action="buy_cea",
                    qty=min(surplus * 0.3, sell_cap or surplus * 0.3),
                    unit_price=unit,
                    window="early",
                    note="低位适度囤存 CEA 对冲下一年排放；" + _channel_note(meta, "CEA"),
                    meta=meta,
                )
            )
        else:
            cap_note = ""
            if carry:
                cap_note = (
                    f"；测算最大可结转约 {carry.max_carry:g} 万吨"
                    f"（结转日 {deadline_label}），请勿超过上限囤积"
                )
            actions.append(
                PlanAction(
                    action="sell_cea",
                    qty=0,
                    unit_price=0,
                    window="",
                    note="富余配额可在结转上限内留存次年" + cap_note,
                    meta={"informational": True},
                )
            )

    return [a for a in actions if a.qty > 0 or a.meta.get("informational")]


def generate_plans(ctx: StrategyContext) -> list[dict[str, Any]]:
    compliance_cfg = ctx.settings.get("compliance") or {}
    listing_fee, block_fee = resolve_fee_rates(ctx.settings.get("cost"))
    large_split = float(compliance_cfg.get("large_trade_split_threshold") or 5.0)
    single = float(ctx.single_trade_limit or 0)
    budget = ctx.annual_budget_cap
    channel = _channel_cfg(ctx.settings)

    # 三套方案目前共享同一 CEA+CCER 动作集；差异体现在画像与文案分层
    raw_actions = _build_core_actions(ctx)
    trade_actions = [a for a in raw_actions if not a.meta.get("informational")]
    info_actions = [a for a in raw_actions if a.meta.get("informational")]
    filtered = filter_plan_actions(
        trade_actions,
        ccer_cap=ctx.accounting.ccer_cap,
        annual_budget_cap=budget,
        single_trade_limit=single,
        large_split_threshold=large_split,
        listing_fee_rate=listing_fee,
        block_fee_rate=block_fee,
    )
    all_actions = filtered.actions + info_actions
    net_save = 0.0
    for a in filtered.actions:
        rate = float(a.meta.get("fee_rate") or 0)
        if a.action == "sell_cea":
            # 卖出实收（成交总额 − 手续费）计入净节约
            net_save += trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="sell")
        # 线下相对公开参考价的假定节省
        listed = a.meta.get("listed_ref_price")
        if (
            a.action in ("buy_cea", "buy_ccer")
            and listed is not None
            and a.meta.get("channel") == "offline_preferred"
        ):
            net_save += cash_cny(a.qty, max(0.0, float(listed) - float(a.unit_price)))

    plans: list[dict[str, Any]] = []
    for key, title, desc in PLAN_SPECS:
        plans.append(
            {
                "key": key,
                "title": title,
                "description": desc,
                "actions": [a.to_dict() for a in all_actions],
                "total_cost": filtered.total_cost,
                "net_saving": net_save,
                "compliance": {
                    "ok": filtered.ok,
                    "issues": [i.to_dict() for i in filtered.issues],
                    "notes": filtered.notes,
                },
                "time_window": ctx.market.time_window,
                "market_action_tag": ctx.market.action_tag,
                "channel": {
                    "prefer_offline": bool(channel.get("prefer_offline", True)),
                    "offline_discount_vs_listed": float(
                        channel.get("offline_discount_vs_listed") or 0
                    ),
                    "price_note": "无实时挂单；成本按日均/预测价锚定，并假定线下更优",
                    "listing_fee_rate": listing_fee,
                    "block_fee_rate": block_fee,
                },
            }
        )
    return plans


def build_strategy_payload(
    *,
    risk_profile: str,
    annual_budget_cap: float,
    single_trade_limit: float,
    settings: dict | None,
    accounting: AccountingResult,
    market: MarketCycleResult,
    cea_price: float = 80.0,
    ccer_price: float = 60.0,
    sellable_cea: float = 0.0,
    cea_price_predicted: float | None = None,
    ccer_price_predicted: float | None = None,
    carry_forward: CarryForwardResult | None = None,
    # 兼容旧调用签名（已忽略）
    enterprise_attrs: dict | None = None,
    green_premium_per_mwh: float = 0.0,
    grec_price: float = 0.0,
    own_renewable_mwh: float = 0.0,
) -> dict[str, Any]:
    del enterprise_attrs, green_premium_per_mwh, grec_price, own_renewable_mwh
    merged = deep_merge(default_settings(), settings or {})
    ctx = StrategyContext(
        risk_profile=risk_profile or "balanced",
        annual_budget_cap=float(annual_budget_cap or 0),
        single_trade_limit=float(single_trade_limit or 0),
        settings=merged,
        accounting=accounting,
        market=market,
        cea_price=float(cea_price or 80),
        ccer_price=float(ccer_price or 60),
        sellable_cea=float(sellable_cea or 0),
        cea_price_predicted=cea_price_predicted,
        ccer_price_predicted=ccer_price_predicted,
        carry_forward=carry_forward,
    )
    plans = generate_plans(ctx)
    out: dict[str, Any] = {
        "accounting": accounting.to_dict(),
        "market_tags": market.to_dict(),
        "plans": plans,
        "risk_profile": ctx.risk_profile,
        "profile_config": _profile(merged, ctx.risk_profile),
        "channel_config": _channel_cfg(merged),
        "price_basis": {
            "cea_listed_or_daily": ctx.cea_price,
            "ccer_listed_or_daily": ctx.ccer_price,
            "cea_predicted": ctx.cea_price_predicted,
            "ccer_predicted": ctx.ccer_price_predicted,
            "note": "公开市场无实时挂单数据；推荐价为日均/预测锚定，非盘口。",
        },
    }
    if carry_forward is not None:
        out["carry_forward"] = carry_forward.to_dict()
    return out
