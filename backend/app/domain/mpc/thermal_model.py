"""温度响应模型：一阶 RC 灰箱，用于动作求解器的前向预测。

为什么是一阶 RC 而不是"直接回归 T(t+X)"
----------------------------------------
求解器要在时域内滚动 S 段、每段 L 秒，需要任意时刻的状态；回归器只能回答
"从当前算 X 秒后"，无法在中途换动作，也无法施加"动作保持 ≥ 300 s"这类约束。
RC 结构可以连续滚动，且只有一个可辨识参数 tau。

刻意没有做的事
--------------
没有把 600 s 增益外推到平衡温度去算"稳在 X 度需要多大电流"：20 min 的数据 +
tau=30 min 只走完一半瞬态，任何平衡态结论都是外推。本模型在 600 s 处精确命中
实测，超出 600 s 会偏保守（低估降温幅度），对安全侧有利。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from . import params as P
from .energy_model import Action


def k_i_eff(i: float) -> float:
    """制冷片的等效稳态温度增益 [K]（Tss 里的 I 项）。

    0~3 A：线性，斜率 K_I_LIN（-0.373 K/A）
    3~5 A：斜率线性衰减到 0 ⇒ 5 A 相对 3 A 只多降 0.373 K，却多花 34.8 W。
    这个拐点不是拍出来的：3→5 A 在 10 min 视界 -0.88 K、20 min 视界 +0.36 K，
    符号不稳，而焦耳热从 21.2 W 涨到 56.0 W，故 3 A 以上收益按最保守方式归零。
    """
    if i <= 0:
        return 0.0
    if i <= P.K_I_KNEE:
        return P.K_I_LIN * i
    if i >= P.K_I_END:
        return P.K_I_LIN * P.K_I_KNEE
    span = P.K_I_END - P.K_I_KNEE
    x = i - P.K_I_KNEE
    return P.K_I_LIN * P.K_I_KNEE + P.K_I_LIN * x - P.K_I_LIN * x * x / (2.0 * span)


@dataclass
class ThermalParams:
    """温度响应的全部可调参数（离线标定后可整体替换）。"""

    tau_s: float = P.TAU_S
    k_v: float = P.K_V
    b0: float = P.B0
    b_env: float = P.B_ENV
    tenv_ref: float = P.TENV_REF
    #: 水桶温度影响系数：默认 0 —— 实测 Tw 漂移是最大漏变量，但跨运行回归里
    #: 加水温后风扇系数反而更负（动作与水温共线），单独系数不可靠，留给偏置观测器吸收。
    b_water: float = 0.0
    twater_ref: float = P.TWATER_DEFAULT

    def free_equilibrium(self, tenv: float, twater: float = P.TWATER_DEFAULT) -> float:
        """零动作时的平衡温度 b [℃]"""
        return (self.b0
                + self.b_env * (tenv - self.tenv_ref)
                + self.b_water * (twater - self.twater_ref))

    def steady_state(self, a: Action, tenv: float,
                     twater: float = P.TWATER_DEFAULT) -> float:
        """给定动作与环境后的稳态温度 Tss [℃]"""
        return (self.free_equilibrium(tenv, twater)
                + self.k_v * a.v_fan
                + k_i_eff(a.i_tec))

    def advance(self, t: float, a: Action, dt: float, tenv: float,
                twater: float = P.TWATER_DEFAULT) -> float:
        """从 t 出发，恒定动作 a 保持 dt 秒后的温度。"""
        tss = self.steady_state(a, tenv, twater)
        alpha = 1.0 - math.exp(-dt / self.tau_s)
        return t + (tss - t) * alpha

    def advance_traj(self, t: float, a: Action, dt: float, n: int, tenv: float,
                     twater: float = P.TWATER_DEFAULT) -> List[float]:
        """滚动 n 步（每步 dt 秒），返回轨迹（含起点）。"""
        out = [t]
        for _ in range(n):
            t = self.advance(t, a, dt, tenv, twater)
            out.append(t)
        return out

    def time_to(self, t0: float, a: Action, t_target: float, tenv: float,
                twater: float = P.TWATER_DEFAULT) -> Optional[float]:
        """恒定动作 a 从 t0 降到 t_target 所需时间 [s]；到不了返回 None。"""
        tss = self.steady_state(a, tenv, twater)
        if tss >= t_target:
            return None
        return -self.tau_s * math.log((t_target - tss) / (t0 - tss))


def horizon_gain(p: ThermalParams, a: Action, horizon_s: float, tenv: float,
                 twater: float = P.TWATER_DEFAULT, t0: float = 45.0) -> float:
    """某动作相对「零动作」在 horizon_s 内的额外降温 [K]（负值 = 更凉）。"""
    a0 = Action(0.0, 0.0)
    return (p.advance(t0, a, horizon_s, tenv, twater)
            - p.advance(t0, a0, horizon_s, tenv, twater))
