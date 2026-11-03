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
    # 本方仓位方向：gap（缺口，需采购）/ surplus（盈余，有量可售）/ unknown（未指定企业）
    position_side: str = "unknown"

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


def _normalize_side(side: str | None) -> str:
    key = str(side or "").strip().lower()
    return key if key in ("gap", "surplus") else "unknown"


def judge_market_cycle(
    cea_monthly_prices: list[float],
    current_cea_price: float | None,
    current_ccer_price: float | None = None,
    *,
    as_of: date | None = None,
    low_percentile: float = 0.30,
    mid_percentile: float = 0.70,
    ccer_issue_trend: float | None = None,
    side: str | None = None,
) -> MarketCycleResult:
    """判定价格位置与时间窗口，并在已知本方仓位时校正动作方向。

    动作标签本身只回答「这个价位、这个时窗适合做什么」，不含企业方向：
    高位+年末对盈余企业是卖点，对缺口企业却是追高风险。传 side 后，
    缺口方不会再拿到 sell、盈余方不会再拿到 buy，避免报告里出现反向建议。
    """
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

    # 方向校正：按本方实际仓位改写反向标签
    position_side = _normalize_side(side)
    if position_side == "gap" and action == "sell":
        action = "hold"
        rationale = (
            "价格处于高位且临近清缴，本方为配额缺口方，不具备出售条件；"
            "宜先消化自有 CCER，再按市场可承接量分批采购，不追高"
        )
    elif position_side == "surplus" and action == "buy":
        action = "hold"
        rationale = (
            "价格处于低位，本方为配额盈余方，无需采购；"
            "宜保留配额，等待高位或年末窗口择机出售"
        )

    return MarketCycleResult(
        price_band=band,
        time_window=window,
        action_tag=action,
        current_price=price,
        cea_ccer_spread=spread,
        ccer_supply_tag=supply,
        rationale=rationale,
        position_side=position_side,
    )
