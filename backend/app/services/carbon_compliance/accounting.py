"""碳排放量核算引擎（确定性公式）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class AccountingInput:
    scope1_combustion: float = 0.0
    scope1_process: float = 0.0
    scope2_power: float = 0.0
    purchased_mwh: float = 0.0
    market_green_mwh: float = 0.0
    self_gen_mwh: float = 0.0
    free_cea_quota: float = 0.0
    own_ccer_eligible: float = 0.0
    grid_emission_factor: float = 0.5703
    ccer_max_ratio: float = 0.05
    verified_override: float | None = None


@dataclass
class AccountingResult:
    scope1_total: float
    scope2_from_power: float
    raw_total: float
    reducible_power: float
    verified_emission: float
    free_cea_quota: float
    # 履约缺口：已扣减自有 CCER（受 5% 抵销比例上限约束）；正=缺口，负=富余
    compliance_gap: float
    ccer_cap: float
    own_ccer_eligible: float
    own_ccer_usable: float
    residual_gap_after_own_ccer: float
    # 抵扣前缺口（核查排放 − 可用 CEA）与实际抵扣量，用于口径追溯
    gap_before_ccer: float = 0.0
    ccer_offset_used: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def compute_accounting(inp: AccountingInput) -> AccountingResult:
    """履约核查口径仅计 Scope1（化石燃料 + 工艺过程）；官方核查总量可覆盖。

    数量字段单位均为万吨。
    """
    scope1 = float(inp.scope1_combustion or 0) + float(inp.scope1_process or 0)
    # Scope2 / 外购电 / 绿电核减不参与全国碳市场履约核查总量
    scope2 = 0.0
    reducible = 0.0
    raw = scope1
    if inp.verified_override is not None:
        verified = float(inp.verified_override)
    else:
        verified = max(0.0, scope1)
    free = float(inp.free_cea_quota or 0)
    # 抵扣前缺口（毛缺口）
    gap_gross = verified - free
    ratio = float(inp.ccer_max_ratio if inp.ccer_max_ratio is not None else 0.05)
    ratio = min(1.0, max(0.0, ratio))
    # CCER 抵销上限 = 应清缴碳排放配额（即核查排放）× 抵销比例
    # 政策依据：重点排放单位每年使用 CCER 抵销的比例不得超过应清缴碳排放配额的 5%
    ccer_cap = max(0.0, verified * ratio)
    own = max(0.0, float(inp.own_ccer_eligible or 0))
    # 本履约可动用 CCER = min(自有可抵扣, 抵销上限, 抵扣前缺口)；富余企业为 0
    own_usable = min(own, ccer_cap, max(0.0, gap_gross))
    # 履约缺口按「已扣 CCER」口径：缺口里能用 CCER 抵扣的部分不再计入缺口
    gap_net = gap_gross - own_usable
    return AccountingResult(
        scope1_total=scope1,
        scope2_from_power=scope2,
        raw_total=raw,
        reducible_power=reducible,
        verified_emission=verified,
        free_cea_quota=free,
        compliance_gap=gap_net,
        ccer_cap=ccer_cap,
        own_ccer_eligible=own,
        own_ccer_usable=own_usable,
        residual_gap_after_own_ccer=gap_net,
        gap_before_ccer=gap_gross,
        ccer_offset_used=own_usable,
    )
