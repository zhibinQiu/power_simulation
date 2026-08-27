"""碳市场行情周期判断（月度分位，非高频）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


@dataclass
class MarketCycleResult:
    price_band: str  # low | mid | high | unknown
    time_window: str  # early | mid | late
    action_tag: str  # buy | sell | hold
    current_price: float | None
    cea_ccer_spread: float | None
    ccer_supply_tag: str  # loose | tight | unknown
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _percentile_band(
    prices: list[float],
    current: float,
    low_p: float = 0.30,
    mid_p: float = 0.70,
) -> str:
    if not prices:
        return "unknown"
    ordered = sorted(prices)
    n = len(ordered)
    low_cut = ordered[max(0, min(n - 1, int(n * low_p) - 1))]
    mid_cut = ordered[max(0, min(n - 1, int(n * mid_p) - 1))]
    if current <= low_cut:
        return "low"
    if current <= mid_cut:
        return "mid"
    return "high"


def _time_window(month: int) -> str:
    if month <= 4:
        return "early"
    if month <= 9:
        return "mid"
    return "late"


def judge_market_cycle(
    cea_monthly_prices: list[float],
    current_cea_price: float | None,
    current_ccer_price: float | None = None,
    *,
    as_of: date | None = None,
    low_percentile: float = 0.30,
    mid_percentile: float = 0.70,
    ccer_issue_trend: float | None = None,
) -> MarketCycleResult:
    today = as_of or date.today()
    window = _time_window(today.month)
    price = current_cea_price
    if price is None and cea_monthly_prices:
        price = cea_monthly_prices[-1]
    band = (
        _percentile_band(cea_monthly_prices, price, low_percentile, mid_percentile)
        if price is not None
        else "unknown"
    )
    spread = None
    if price is not None and current_ccer_price is not None:
        spread = float(price) - float(current_ccer_price)

    if ccer_issue_trend is None:
        supply = "unknown"
    elif ccer_issue_trend >= 0:
        supply = "loose"
    else:
        supply = "tight"

    # 标签：适合采购 / 出售 / 观望
    if band == "low" and window != "late":
        action = "buy"
        rationale = "CEA 处于历史低位区间，适合分批采购或适度囤存"
    elif band == "high" and window == "late":
        action = "sell"
        rationale = "年末履约紧张期且价格高位，盈余企业适合分批卖出"
    elif band == "high" and window != "late":
        action = "hold"
        rationale = "价格高位，缺口企业宜延后采购并优先消耗自有 CCER"
    elif window == "late" and band != "low":
        action = "buy" if band != "high" else "hold"
        rationale = "临近清缴，缺口企业需评估采购紧急度与罚款兜底"
    else:
        action = "hold"
        rationale = "价格与时间窗口中性，建议观望或按计划小额执行"

    return MarketCycleResult(
        price_band=band,
        time_window=window,
        action_tag=action,
        current_price=price,
        cea_ccer_spread=spread,
        ccer_supply_tag=supply,
        rationale=rationale,
    )
