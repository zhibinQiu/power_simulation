"""CEA 结转额度测算。

最大可结转 = min(基础 + 净卖出 × 倍数, 年末持仓)。
超出上限的配额须在结转日前处置，否则到期失效。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


@dataclass
class CarryForwardResult:
    deadline_md: str
    deadline: date | None
    base_qty: float
    net_sell: float
    net_sell_multiplier: float
    year_end_holding: float
    formula_cap: float  # 基础 + 净卖出 × 倍数
    max_carry: float
    excess: float
    # 额外净卖出量：使结转上限覆盖年末持仓（同时降低持仓）
    sell_to_expand_cap: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["deadline"] = self.deadline.isoformat() if self.deadline else None
        return d


def parse_deadline_md(year: int, md: str) -> date:
    try:
        month_s, day_s = str(md or "06-10").split("-")
        return date(int(year), int(month_s), int(day_s))
    except Exception:
        return date(int(year), 6, 10)


def compute_carry_forward(
    *,
    base_qty: float,
    net_sell: float,
    year_end_holding: float,
    net_sell_multiplier: float = 1.5,
    deadline_md: str = "06-10",
    deadline_year: int | None = None,
    as_of: date | None = None,
) -> CarryForwardResult:
    """测算最大可结转与超额。

    卖出 Δ 会同时提高净卖出、降低年末持仓：
    超额 E = max(0, H − B − 1.5N) 时，Δ ≥ E / (1 + 倍数) 可使持仓落入上限内。
    """
    base = max(0.0, float(base_qty or 0))
    ns = float(net_sell or 0)
    holding = max(0.0, float(year_end_holding or 0))
    mult = float(net_sell_multiplier if net_sell_multiplier is not None else 1.5)
    if mult <= 0:
        mult = 1.5

    formula_cap = base + max(0.0, ns) * mult
    max_carry = min(formula_cap, holding)
    excess = max(0.0, holding - max_carry)

    # H - Δ <= B + mult*(N+Δ)  →  Δ >= excess / (1+mult)
    sell_to_expand = (excess / (1.0 + mult)) if excess > 0 else 0.0

    today = as_of or date.today()
    y = int(deadline_year or today.year)
    deadline = parse_deadline_md(y, deadline_md or "06-10")

    return CarryForwardResult(
        deadline_md=str(deadline_md or "06-10"),
        deadline=deadline,
        base_qty=base,
        net_sell=ns,
        net_sell_multiplier=mult,
        year_end_holding=holding,
        formula_cap=formula_cap,
        max_carry=max_carry,
        excess=excess,
        sell_to_expand_cap=sell_to_expand,
    )
