"""策略推荐引擎：CEA + CCER 履约动作 → 三套分层方案。

绿电/绿证为国家强制/披露路径，不纳入本引擎推荐。
公开侧无实时挂单，价格以日均/预测价为锚，采购优先建议线下撮合。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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


# (key, 标题, 说明, 风险画像, 渠道口径)
# 三档必须独立计算，否则三张卡片的成本必然一模一样：
#   画像   决定「允许哪些动作」（保守不外购CCER/不卖富余/不囤存；进取全开）
#   渠道口径 决定「同一动作的单价假设」（线下撮合有折扣，挂牌没有）
PLAN_SPECS = (
    (
        "min_cost",
        "最低成本履约方案",
        "仅 CEA+CCER 满足清缴刚需，优先线下撮合降本（保守画像）",
        "conservative",
        "offline",
    ),
    (
        "optimized",
        "成本优化综合方案",
        "CEA+CCER + 择时窗口，线下优先、线上挂牌兜底（平衡画像）",
        "balanced",
        "hybrid",
    ),
    (
        "full_compliance",
        "稳健履约方案",
        "CEA+CCER 全覆盖，按公开参考价即时成交以确保履约（进取画像）",
        "aggressive",
        "listed",
    ),
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


def _channel_cfg(settings: dict, mode: str = "offline") -> dict:
    """渠道口径 → 单价假设。

    - offline：线下撮合为主，用配置的折价（offline_discount_vs_listed）
    - hybrid：线下为主、线上挂牌兜底，折价按对折计（成交量一半走线下）
    - listed：按公开日均/预测参考价挂牌成交，不打折（履约确定性最高）

    公开侧无实时挂单，以上折扣是估算假设，不是盘口。
    """
    merged = deep_merge(
        default_settings().get("channel") or {}, settings.get("channel") or {}
    )
    prefer = bool(merged.get("prefer_offline", True))
    discount = max(0.0, min(0.3, float(merged.get("offline_discount_vs_listed") or 0.0)))
    if not prefer or mode == "listed":
        return {**merged, "prefer_offline": False, "offline_discount_vs_listed": 0.0}
    ratio = 0.5 if mode == "hybrid" else 1.0
    return {
        **merged,
        "prefer_offline": True,
        "offline_discount_vs_listed": round(discount * ratio, 6),
    }


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


def _build_core_actions(
    ctx: StrategyContext, channel: dict | None = None
) -> list[PlanAction]:
    acc = ctx.accounting
    mkt = ctx.market
    prof = _profile(ctx.settings, ctx.risk_profile)
    if channel is None:
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
            if carry and getattr(carry, "policy", "") == "unlimited":
                # 现行政策无结转数量限制：盈余不构成强制处置，只在综合方案里给可选动作
                note = (
                    "现行政策已取消配额结转数量限制，富余配额可全额结转至下一年度，"
                    "不存在超额失效，可按价格与资金安排择机出售"
                )
                meta = {"informational": True, "carry_policy": "unlimited"}
            else:
                cap_note = ""
                if carry:
                    cap_note = (
                        f"；测算最大可结转约 {carry.max_carry:g} 万吨"
                        f"（结转日 {deadline_label}），请勿超过上限囤积"
                    )
                note = "富余配额可在结转上限内留存次年" + cap_note
                meta = {"informational": True}
            actions.append(
                PlanAction(
                    action="sell_cea",
                    qty=0,
                    unit_price=0,
                    window="",
                    note=note,
                    meta=meta,
                )
            )

    return [a for a in actions if a.qty > 0 or a.meta.get("informational")]


def _plan_cost(
    actions: list[PlanAction], *, listing_fee: float, block_fee: float
) -> float:
    """计划现金成本：买入应付为正、卖出实收为负（净支出口径）。"""
    total = 0.0
    for a in actions:
        rate = float(a.meta.get("fee_rate") or 0)
        if not rate:
            rate = fee_rate_for_channel(
                a.meta.get("channel"),
                listing_fee_rate=listing_fee,
                block_fee_rate=block_fee,
            )
        if a.action.startswith("sell"):
            total -= trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="sell")
        else:
            total += trade_cash_cny(a.qty, a.unit_price, fee_rate=rate, side="buy")
    return total



# 三档的批次节奏：保守一次性锁量、平衡分两批、进取分三批等价格回落。
# 以往每档只有一条动作、一个窗口，「分几批、每批多少」全靠撰写模型自己编，
# 于是报告里的「分 3 批、每批 424 万吨」与引擎算出的成本、吨数对不上。
PLAN_BATCH_SPEC: dict[str, int] = {
    "min_cost": 1,
    "optimized": 2,
    "full_compliance": 3,
}
_WINDOW_ORDER = ("early", "mid", "late")
_WINDOW_ZH = {"early": "年初窗口", "mid": "年中窗口", "late": "年末窗口"}


def _batch_windows(start: str, n: int) -> list[str]:
    """每批的执行窗口：从当前窗口起逐批向后顺延，不回溯到已经过去的窗口。

    窗口只有年初/年中/年末三档；批次多于剩余窗口时，后续批次沿用最后一个窗口，
    表示「在同一窗口内分多次成交」。
    """
    try:
        i = _WINDOW_ORDER.index(start)
    except ValueError:
        i = 1
    return [_WINDOW_ORDER[min(i + k, len(_WINDOW_ORDER) - 1)] for k in range(max(n, 1))]


def _money_cn(v: float) -> str:
    """金额中文口径：超过 1 亿用亿元、超过 1 万用万元。"""
    v = float(v or 0)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f} 亿元"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f} 万元"
    return f"{v:.0f} 元"


def _split_action_batches(
    action: PlanAction, n: int, *, start_window: str
) -> list[PlanAction]:
    """把一条买卖动作拆成 n 批，吨数合计与拆分前严格一致（余数落在最后一批）。"""
    qty = float(action.qty or 0)
    if n <= 1 or qty <= 0:
        return [action]
    per = round(qty / n, 4)
    windows = _batch_windows(start_window, n)
    out: list[PlanAction] = []
    remaining = qty
    for idx in range(n):
        take = per if idx < n - 1 else round(remaining, 4)
        remaining = round(remaining - take, 6)
        if take <= 0:
            continue
        w = windows[idx]
        when = _WINDOW_ZH.get(w, w)
        if idx > 0 and windows[idx - 1] == w:
            when += "内继续分批成交"
        meta = dict(action.meta or {})
        meta.update({"batch_seq": idx + 1, "batch_count": n, "batch_qty": take})
        # 本批金额：拆批后单价不变，按本批吨数单独算应付/实收，
        # 避免把整笔的成本对比重复写成每一批的成本
        side = "sell" if action.action.startswith("sell") else "buy"
        cash = trade_cash_cny(
            take, action.unit_price, fee_rate=float(action.meta.get("fee_rate") or 0), side=side
        )
        money_kind = "实收" if side == "sell" else "应付"
        head = (
            f"第 {idx + 1}/{n} 批（{when}，{take:g} 万吨，"
            f"本批{money_kind}约 {_money_cn(abs(cash))}）"
        )
        # 动作原说明里的成本/罚款对比是整笔口径，只在首批保留并显式标注
        if idx == 0 and action.note:
            note = f"{head}｜整笔口径：{action.note}"
        else:
            note = head
        out.append(replace(action, qty=take, window=w, note=note, meta=meta))
    return out


def _apply_plan_batches(
    actions: list[PlanAction], n: int, *, start_window: str
) -> list[PlanAction]:
    """按档位节奏拆批：只拆买卖配额/CCER 的动作，提示性动作原样保留。"""
    out: list[PlanAction] = []
    for a in actions:
        if a.meta.get("informational") or a.action not in (
            "buy_cea",
            "buy_ccer",
            "sell_cea",
        ):
            out.append(a)
            continue
        if n <= 1:
            tag = (
                "一次性锁量成交，不分批"
                if a.action.startswith("buy")
                else "一次性成交，不分批"
            )
            out.append(replace(a, note=(f"{a.note}；{tag}" if a.note else tag)))
            continue
        # 起点跟动作自身窗口走：高价档的动作已被引擎放到「年末窗口」，
        # 分批不能把它拉回当前窗口，否则等于在高位提前买入
        out.extend(
            _split_action_batches(a, n, start_window=(a.window or start_window))
        )
    return out


def generate_plans(ctx: StrategyContext) -> list[dict[str, Any]]:
    compliance_cfg = ctx.settings.get("compliance") or {}
    listing_fee, block_fee = resolve_fee_rates(ctx.settings.get("cost"))
    large_split = float(compliance_cfg.get("large_trade_split_threshold") or 5.0)
    single = float(ctx.single_trade_limit or 0)
    budget = ctx.annual_budget_cap

    plans: list[dict[str, Any]] = []
    for key, title, desc, profile_name, channel_mode in PLAN_SPECS:
        # 每一档独立代入「画像 + 渠道口径」重新生成动作并独立过滤，
        # 这样保守/平衡/进取的动作清单与成本才可能真正不同。
        plan_ctx = replace(ctx, risk_profile=profile_name) if profile_name else ctx
        channel = _channel_cfg(ctx.settings, channel_mode)

        raw_actions = _build_core_actions(plan_ctx, channel=channel)
        trade_actions = [a for a in raw_actions if not a.meta.get("informational")]
        info_actions = [a for a in raw_actions if a.meta.get("informational")]
        # 拦截前的全额测算：预算/CCER 上限把动作拦住时，UI 仍能显示「本来要花多少」
        planned_cost = _plan_cost(
            trade_actions, listing_fee=listing_fee, block_fee=block_fee
        )
        filtered = filter_plan_actions(
            trade_actions,
            ccer_cap=ctx.accounting.ccer_cap,
            annual_budget_cap=budget,
            single_trade_limit=single,
            large_split_threshold=large_split,
            listing_fee_rate=listing_fee,
            block_fee_rate=block_fee,
        )
        # 拆批放在合规过滤之后：预算/单笔限额仍按「整笔动作」判定（与改动前一致），
        # 只有真正通过合规校验、会被执行的动作才排批次，避免「预算只够一批」被写成完整采购计划
        all_actions = _apply_plan_batches(
            filtered.actions,
            PLAN_BATCH_SPEC.get(key, 1),
            start_window=ctx.market.time_window,
        ) + info_actions

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

        blocked = not filtered.ok and not filtered.actions
        if not blocked and not any(a.action.startswith("buy") for a in filtered.actions):
            filtered.notes.append(
                "本期无采购动作：履约缺口已被可用配额/自有 CCER 覆盖，"
                "现金成本与净节约均为 0，无需额外支出"
            )
        # 实际要执行的批次清单：合规过滤后仍存活的买卖动作，供报告与界面直接引用，
        # 避免撰写侧另行编造「分几批、每批多少」
        _batch_rows = [
            {
                "seq": int(a.meta.get("batch_seq") or 1),
                "action": a.action,
                "qty": float(a.qty or 0),
                "window": a.window,
                "unit_price": float(a.unit_price or 0),
            }
            for a in all_actions
            if a.action in ("buy_cea", "buy_ccer", "sell_cea")
        ]
        plans.append(
            {
                "key": key,
                "title": title,
                "description": desc,
                "risk_profile": profile_name,
                "channel_mode": channel_mode,
                "actions": [a.to_dict() for a in all_actions],
                "total_cost": filtered.total_cost,
                # 拦截前的全额计划成本（total_cost 只统计通过合规过滤的动作）
                "planned_cost": planned_cost,
                "net_saving": net_save,
                # 被合规规则整体拦下时明确标记，避免 UI 把 0 元误读成「不花钱」
                "blocked": blocked,
                # 整体被拦时仍透出原始动作：用户需要看到「本来要做什么、多少钱」才能
                # 判断是不是预算/上限填错了，而不是只看到三个 0。
                "planned_actions": [a.to_dict() for a in trade_actions] if blocked else [],
                "compliance": {
                    "ok": filtered.ok,
                    "issues": [i.to_dict() for i in filtered.issues],
                    "notes": filtered.notes,
                },
                "time_window": ctx.market.time_window,
                "batch_count": PLAN_BATCH_SPEC.get(key, 1),
                "batches": _batch_rows,
                "market_action_tag": ctx.market.action_tag,
                "channel": {
                    "prefer_offline": bool(channel.get("prefer_offline", True)),
                    "offline_discount_vs_listed": float(
                        channel.get("offline_discount_vs_listed") or 0
                    ),
                    "price_note": (
                        "无实时挂单；成本按日均/预测价锚定，"
                        + (
                            "线上挂牌口径不打折"
                            if channel_mode == "listed"
                            else "线下撮合按配置折扣估算"
                        )
                    ),
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
