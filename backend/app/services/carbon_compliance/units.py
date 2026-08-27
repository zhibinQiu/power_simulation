"""碳履约数量单位：万吨；市价仍为元/吨。"""

from __future__ import annotations

from typing import Literal

# 1 万吨 = 10000 吨（仅用于金额换算）
TONS_PER_WAN = 10000.0


def notional_cny(qty_wan: float, unit_price_per_ton: float) -> float:
    """成交总额（货值）：数量(万吨) × 10000 × 单价(元/吨) → 元。"""
    return float(qty_wan or 0) * TONS_PER_WAN * float(unit_price_per_ton or 0)


def fee_cny(qty_wan: float, unit_price_per_ton: float, *, fee_rate: float = 0.0) -> float:
    """手续费 = 成交总额 × 单边费率。"""
    return notional_cny(qty_wan, unit_price_per_ton) * abs(float(fee_rate or 0))


def cash_cny(qty_wan: float, unit_price_per_ton: float, *, fee_rate: float = 0.0) -> float:
    """兼容旧调用：成交总额 + 手续费（等价于总额×(1+r)，r 可为负表示卖出净收入）。"""
    n = notional_cny(qty_wan, unit_price_per_ton)
    return n + n * float(fee_rate or 0)


def trade_cash_cny(
    qty_wan: float,
    unit_price_per_ton: float,
    *,
    fee_rate: float = 0.0,
    side: Literal["buy", "sell"] = "buy",
) -> float:
    """含手续费的现金结果。

    - 手续费 = 成交总额 × |费率|
    - 买入应付 = 成交总额 + 手续费
    - 卖出实收 = 成交总额 − 手续费
    """
    n = notional_cny(qty_wan, unit_price_per_ton)
    fee = fee_cny(qty_wan, unit_price_per_ton, fee_rate=fee_rate)
    if side == "sell":
        return n - fee
    return n + fee


def resolve_fee_rates(cost: dict | None) -> tuple[float, float]:
    """返回 (挂牌单边费率, 大宗单边费率)。

    若未配置新字段，回退到旧版单一 ``trade_fee_rate``。
    """
    c = cost or {}
    legacy = float(c.get("trade_fee_rate") or 0)
    listing = c.get("listing_fee_rate")
    block = c.get("block_fee_rate")
    listing_r = float(listing) if listing is not None else legacy
    block_r = float(block) if block is not None else legacy
    return max(0.0, listing_r), max(0.0, block_r)


def fee_rate_for_channel(channel: str | None, *, listing_fee_rate: float, block_fee_rate: float) -> float:
    """按成交渠道选用费率：挂牌 / 大宗（线下撮合按大宗计）。"""
    ch = str(channel or "")
    if ch in ("offline_preferred", "offline_preferred_sell") or "offline" in ch:
        return float(block_fee_rate or 0)
    if ch in ("listed_fallback",) or "listed" in ch:
        return float(listing_fee_rate or 0)
    return 0.0
