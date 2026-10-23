"""能耗模型：两个执行器的「设定值 -> 瞬时电功率」固定函数。

设计原则
--------
1. 功率只依赖设定值（V 或 I），不依赖温度状态 —— 这是标定结论，不是简化：
   风扇功率不能由 V·I 自洽算出（两通道不同步）；制冷片的 dT 项漂移实测只有 ±2%。
2. 两个函数量级差 30 倍以上（风扇满档 1.62 W，制冷片 3 A 21.2 W），
   所以「能耗最小」的主导项几乎全部来自制冷片 —— 这直接决定了最优解的形状：
   风扇够用就绝不该开 TEC。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from . import params as P


# --------------------------------------------------------------------------
# 制冷片 P(I)
# --------------------------------------------------------------------------
def p_tec(i: float) -> float:
    """制冷片瞬时电功率 [W]：P = 2.0693·I² + 0.8562·I"""
    if i < 0:
        raise ValueError(f"制冷片电流不能为负：{i}")
    return P.TEC_A * i * i + P.TEC_B * i


# --------------------------------------------------------------------------
# 风扇 P(V)
# --------------------------------------------------------------------------
def _v_set_to_actual(v_set: float) -> float:
    """设定电压 -> 该档位的实测电压。只对已标定档位做映射，其余按线性近似。"""
    if v_set in P.FAN_P_TABLE:
        return P.FAN_P_TABLE[v_set][0]
    if v_set >= 23.0:
        return v_set - 0.48      # 24 V 档附近电源上限压降
    return v_set


def _p_fan_lowv(v: float) -> float:
    """2~8 V 段查表 + 线性内插（公式在该段失效）。"""
    ks = sorted(P.FAN_P_LOWV)
    if v <= ks[0]:
        return P.FAN_P_LOWV[ks[0]]
    if v >= ks[-1]:
        return P.FAN_P_LOWV[ks[-1]]
    for a, b in zip(ks[:-1], ks[1:]):
        if a <= v <= b:
            t = (v - a) / (b - a)
            return P.FAN_P_LOWV[a] + t * (P.FAN_P_LOWV[b] - P.FAN_P_LOWV[a])
    return P.FAN_P_LOWV[ks[-1]]


def p_fan(v: float, *, v_is_actual: bool = False) -> float:
    """风扇瞬时电功率 [W]。

    v_is_actual=False（默认，传设定值）时会把 24 V 档映射到实测 23.52 V；
    V<9 区间公式失效（转子起转凹陷），自动退化为查表。
    """
    if v <= 0:
        return 0.0
    vv = v if v_is_actual else _v_set_to_actual(v)
    if vv < P.FAN_FORMULA_VMIN:
        return _p_fan_lowv(vv)
    if vv > P.FAN_FORMULA_VMAX:
        raise ValueError(f"风扇电压超出量程：{vv} V（上限 {P.FAN_FORMULA_VMAX}）")
    return P.FAN_A * vv * vv + P.FAN_B * vv


# --------------------------------------------------------------------------
# 动作
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Action:
    """一个离散动作 = 一组（风扇设定电压, 制冷片设定电流）。"""

    v_fan: float = 0.0
    i_tec: float = 0.0

    @property
    def p_fan(self) -> float:
        return p_fan(self.v_fan)

    @property
    def p_tec(self) -> float:
        return p_tec(self.i_tec)

    @property
    def power(self) -> float:
        """瞬时总电功率 [W]"""
        return self.p_fan + self.p_tec

    def energy(self, dt: float) -> float:
        """恒定动作保持 dt 秒的电能 [J]"""
        return self.power * dt

    def label(self) -> str:
        return f"{self.v_fan:g} V / {self.i_tec:g} A"

    def as_dict(self) -> dict:
        return {"v_fan": self.v_fan, "i_tec": self.i_tec, "power_w": round(self.power, 4)}


def build_action_set(
    include_5a: bool = False,
    fan_levels: Sequence[float] | None = None,
    tec_levels: Sequence[float] | None = None,
) -> List[Action]:
    """构造离散动作集：默认 8 档风扇 × 5 档电流 = 40 个动作（5 A 默认剔除）。"""
    vs = P.FAN_V_ACTIONS if fan_levels is None else tuple(fan_levels)
    is_ = P.TEC_I_LEVELS if tec_levels is None else tuple(tec_levels)
    if not include_5a:
        is_ = tuple(i for i in is_ if i not in P.TEC_I_BLACKLIST)
    return [Action(v, i) for v in vs for i in is_]


# --------------------------------------------------------------------------
# 自检：公式 vs 实测档位
# --------------------------------------------------------------------------
def check_against_measured() -> List[dict]:
    """逐档对比公式与实测功率，供「能否启用」的可用性判据使用。"""
    rows: List[dict] = []
    for v_set, (v_act, p_meas, n) in sorted(P.FAN_P_TABLE.items()):
        p_mod = p_fan(v_set)
        rel = (p_mod - p_meas) / p_meas if p_meas > 1e-9 else 0.0
        rows.append({"dev": "fan", "level": v_set, "p_meas": p_meas,
                     "p_model": round(p_mod, 4), "rel_err": round(rel, 4), "n": n})
    for i_set, p_meas in sorted(P.TEC_P_MEAS.items()):
        p_mod = p_tec(i_set)
        rel = (p_mod - p_meas) / p_meas if p_meas > 1e-9 else 0.0
        rows.append({"dev": "tec", "level": i_set, "p_meas": p_meas,
                     "p_model": round(p_mod, 4), "rel_err": round(rel, 4), "n": 0})
    return rows
