# -*- coding: utf-8 -*-
"""CEA 配额逐年滚动核算（清缴链）。

为什么需要这个模块
------------------
台账 `cea_holdings` 存的是「年度发放量（flow）」——每年一行 `free_quota`，
不是「当前结存（stock）」，也没有「已清缴消耗」字段。旧逻辑用

    if is_all_years or match_year or vy >= market_start_year:

把所有「市场纳入年及以后」的发放量全部累加进目标年度，且从不扣减各年度
清缴排放。结果同一批配额被永久重复计入：冀东钢铁跑 2027 年度时，
2025 年发放的 1550 万吨 + 2026 年发放的 200 万吨全部被算成 2027 年可用，
得出「盈余 1581 万吨」，而真实情况是逐年累计缺口。

本模块按业务真实口径重算：从纳入年起逐年清缴，年末结存传给下一年，
只把真正留到目标年的余额计入「可用」，并把每年过程留痕供报告追溯。

滚动规则
--------
1. 年初结存 = 上年年末结存（负值不结转，缺口必须靠当年配额或买入补足）。
2. 当年可用 = 年初结存 + 当年发放 + 当年买入 − 当年卖出。
3. 年末结存 = 当年可用 − 当年核查排放。
4. 台账手填的 `carry_forward_qty` 只在「上年无任何台账记录、无法滚动」时兜底；
   若与滚动结存冲突，以滚动结存为准并给出提示。
5. 历史年度缺核查排放数据时，结存不向下传递（无法核销即视为不可用），并提示。
"""

from __future__ import annotations

from dataclasses import dataclass, field

_EPS = 1e-9


@dataclass
class RollYear:
    """单个年度的滚动明细，供报告与告警追溯。"""

    year: int
    opening: float = 0.0          # 年初结存（上年转来，负值按 0）
    allocated: float = 0.0        # 当年发放
    allocated_estimated: bool = False
    carried_recorded: float = 0.0  # 台账手填结转
    carry_in: float = 0.0          # 实际采用的年初结转
    buy: float = 0.0
    sell: float = 0.0
    emission: float | None = None
    closing: float | None = None   # 年末结存；None 表示缺排放数据无法核销

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "opening": round(self.opening, 4),
            "allocated": round(self.allocated, 4),
            "allocated_estimated": self.allocated_estimated,
            "carried_recorded": round(self.carried_recorded, 4),
            "carry_in": round(self.carry_in, 4),
            "buy": round(self.buy, 4),
            "sell": round(self.sell, 4),
            "emission": None if self.emission is None else round(self.emission, 4),
            "closing": None if self.closing is None else round(self.closing, 4),
        }


@dataclass
class RollResult:
    target_year: int
    usable: float = 0.0          # 目标年可用配额（年初结存 + 发放 + 买入 − 卖出）
    allocated_free: float = 0.0  # 目标年当年发放
    carry_in: float = 0.0        # 目标年年结转过来的结存
    bought: float = 0.0
    sold: float = 0.0
    sellable: float = 0.0        # 目标年可售上限
    years: list[RollYear] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target_year": self.target_year,
            "usable": round(self.usable, 4),
            "allocated_free": round(self.allocated_free, 4),
            "carry_in": round(self.carry_in, 4),
            "bought": round(self.bought, 4),
            "sold": round(self.sold, 4),
            "sellable": round(self.sellable, 4),
            "years": [y.to_dict() for y in self.years],
            "warnings": list(self.warnings),
        }


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _index_holdings(holdings: list[dict]) -> dict[int, dict]:
    """按配额年度归集台账，同年多条记录累加。"""
    out: dict[int, dict] = {}
    for h in holdings or []:
        try:
            vy = int(h.get("vintage_year") or 0)
        except (TypeError, ValueError):
            continue
        if vy <= 0:
            continue
        cur = out.setdefault(
            vy,
            {
                "free_quota": 0.0,
                "carry_forward_qty": 0.0,
                "estimated_free_quota": 0.0,
                "sellable_cap": None,
                "net_sell_qty": 0.0,
                "buy_qty": 0.0,
            },
        )
        cur["free_quota"] += max(0.0, _f(h.get("free_quota")))
        cur["carry_forward_qty"] += max(0.0, _f(h.get("carry_forward_qty")))
        cur["estimated_free_quota"] += max(0.0, _f(h.get("estimated_free_quota")))
        cur["net_sell_qty"] += _f(h.get("net_sell_qty"))
        cur["buy_qty"] += _f(h.get("buy_qty"))
        cap = h.get("sellable_cap")
        if cap is not None:
            cur["sellable_cap"] = _f(cap) + (cur["sellable_cap"] or 0.0)
    return out


def _index_emissions(emissions: list[dict]) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in emissions or []:
        try:
            y = int(r.get("year") or 0)
        except (TypeError, ValueError):
            continue
        if y <= 0:
            continue
        v = r.get("verified_total")
        if v is None:
            continue
        out[y] = out.get(y, 0.0) + _f(v)
    return out


def roll_cea_over_years(
    *,
    holdings: list[dict],
    emissions: list[dict],
    trades_by_year: dict | None,
    target_year: int,
    market_start_year: int = 0,
    max_span_years: int = 30,
) -> RollResult:
    """从纳入年逐年滚动到目标年，返回目标年可用配额与全过程明细。"""
    target_year = int(target_year)
    holding_map = _index_holdings(holdings)
    emission_map = _index_emissions(emissions)
    trades = trades_by_year or {}

    start = int(market_start_year or 0)
    if start <= 0 or start > target_year:
        known = [y for y in holding_map if y <= target_year]
        start = min(known) if known else target_year
    if target_year - start > max_span_years:
        start = target_year - max_span_years

    res = RollResult(target_year=target_year)
    prev_closing: float | None = 0.0
    prev_had_record = True

    for year in range(start, target_year + 1):
        h = holding_map.get(year)
        row = RollYear(year=year)

        # ---- 当年发放 ----
        if h:
            row.allocated = h["free_quota"]
            if row.allocated <= _EPS and h["estimated_free_quota"] > _EPS:
                row.allocated = h["estimated_free_quota"]
                row.allocated_estimated = True
        row.carried_recorded = h["carry_forward_qty"] if h else 0.0

        # ---- 年初结转：滚动结存优先，缺历史记录时用手填值兜底 ----
        if prev_had_record and prev_closing is not None:
            row.opening = max(0.0, prev_closing)
            row.carry_in = row.opening
            if row.carried_recorded > _EPS and abs(row.carried_recorded - row.opening) > 0.5:
                res.warnings.append(
                    f"{year} 年度台账结转量 {row.carried_recorded:g} 万吨与滚动结存 "
                    f"{row.opening:g} 万吨不一致，已按滚动结存计算"
                )
        else:
            row.carry_in = max(0.0, row.carried_recorded)
            row.opening = row.carry_in

        # ---- 当年交易流水：有流水以流水为准，否则回退台账手填 ----
        agg = trades.get(year)
        if agg:
            row.buy = _f(agg.get("buy"))
            row.sell = _f(agg.get("sell"))
        elif h:
            row.buy = h["buy_qty"]
            row.sell = h["net_sell_qty"]

        # ---- 当年结存 ----
        available = row.opening + row.allocated + row.buy - row.sell
        if year == target_year:
            res.usable = max(0.0, available)
            res.allocated_free = row.allocated
            res.carry_in = row.carry_in
            res.bought = row.buy
            res.sold = row.sell
            cap = h.get("sellable_cap") if h else None
            res.sellable = _f(cap) if cap is not None else res.usable
            row.emission = emission_map.get(year)
            row.closing = available - row.emission if row.emission is not None else None
            res.years.append(row)
            if not h or (row.allocated <= _EPS and not row.allocated_estimated):
                res.warnings.append(
                    f"{target_year} 年度台账未录入配额分配量，当年发放按 0 计入；"
                    "仅上年结转结存可用于本年度履约"
                )
            if row.allocated_estimated:
                res.warnings.append(
                    f"{target_year} 年度按估算配额 {row.allocated:g} 万吨计入（台账未录入实际分配量）"
                )
            break

        row.emission = emission_map.get(year)
        if row.emission is None:
            # 缺排放数据：无法核销，结存不向下传递
            row.closing = None
            res.warnings.append(
                f"{year} 年度缺少核查排放数据，无法核定结存，"
                f"结转至 {year + 1} 年度的结存按 0 计"
            )
            prev_closing = None
            prev_had_record = False
        else:
            row.closing = available - row.emission
            prev_closing = row.closing
            prev_had_record = h is not None
        res.years.append(row)

    return res
