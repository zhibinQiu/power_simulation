"""CEA 结转额度测算。

两种政策口径，按履约年度自动切换：

- legacy_limit（2023、2024 年度方案）：限值结转。
  最大可结转 = min(基础结转量 + 净卖出 × 倍数, 年末持仓)，超出上限的配额须在结转日前处置。
- unlimited（2025、2026 年度方案起）：取消配额结转数量限制，盈余配额可全额结转，
  不存在「超额失效」，excess 恒为 0。

另注：2019—2024 年度历史结余配额不可用于 2025 年度及以后清缴。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


POLICY_LEGACY = "legacy_limit"
POLICY_UNLIMITED = "unlimited"
# 2023、2024 年度方案的基础结转量（万吨，所有企业均有）
POLICY_DEFAULT_BASE_QTY = 1.0
# 2025、2026 年度方案取消结转限制，自该年度起口径切为 unlimited
POLICY_UNLIMITED_FROM_YEAR = 2025


def resolve_carry_policy(compliance_year: int, configured: str = "auto") -> str:
    """解析结转政策口径。

    configured 支持 auto / unlimited / legacy_limit：
    auto 按履约年度判定，2025 年度及以后走 unlimited（现行方案取消结转限制）。
    """
    val = str(configured or "auto").strip().lower()
    if val in ("unlimited", "limitless"):
        return POLICY_UNLIMITED
    if val in ("legacy", "legacy_limit", "limited"):
        return POLICY_LEGACY
    try:
        year = int(compliance_year or 0)
    except Exception:  # noqa: BLE001
        year = 0
    return POLICY_UNLIMITED if year >= POLICY_UNLIMITED_FROM_YEAR else POLICY_LEGACY


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
    # 政策口径：legacy_limit（限值结转）/ unlimited（不设数量限制）
    policy: str = POLICY_LEGACY

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
    policy: str = POLICY_LEGACY,
) -> CarryForwardResult:
    """测算最大可结转与超额。

    legacy_limit 下，卖出 Δ 会同时提高净卖出、降低年末持仓：
    超额 E = max(0, H − B − 1.5N) 时，Δ ≥ E / (1 + 倍数) 可使持仓落入上限内。

    unlimited 下不设数量限制：可结转量即年末持仓，超额恒为 0，
    不存在「到期失效」，也不再需要为扩大结转额度而出售。
    """
    base = max(0.0, float(base_qty or 0))
    ns = float(net_sell or 0)
    holding = max(0.0, float(year_end_holding or 0))
    mult = float(net_sell_multiplier if net_sell_multiplier is not None else 1.5)
    if mult <= 0:
        mult = 1.5
    pol = POLICY_UNLIMITED if str(policy or "").strip().lower() == POLICY_UNLIMITED else POLICY_LEGACY

    if pol == POLICY_UNLIMITED:
        # 全额结转：上限即持仓，无超额，无需为扩大上限而卖出
        formula_cap = holding
        max_carry = holding
        excess = 0.0
        sell_to_expand = 0.0
    else:
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
        policy=pol,
    )
