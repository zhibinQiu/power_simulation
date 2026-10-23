"""动作求解器：「当前温度 + 目标温度 + 时限」-> 能耗最小的离散动作序列。

为什么是动态规划，不是连续 QP
------------------------------
两个执行器的设定值都是离散档位（风扇实测 8 档、制冷片实测 6 档），连续 QP 解出的
V=17.3 V 这种值在硬件上根本发不出去，投影到最近档位又会破坏最优性甚至破坏可行性。
DP 直接在档位格上搜索，解一定可执行；也天然支持「每段动作保持 ≥ 300 s」这类
结构性约束（连续 QP 要表达它得引入整数变量）。

为什么不用 numpy
----------------
平台本身的运行环境不保证带 numpy（后端只有本模块用到它）。整条 DP 只是
「档位 × 温度网格」上的一次二维递推，纯 Python 完全跑得动：单段 40 档 × ~5600 格
≈ 22 万次内循环，实测 0.2~0.5 s/段，对 15 s 控制周期仍有数十倍余量。
把 numpy 从依赖里去掉，能让平台在任何 Python 环境下起来就能用，不必为了一个
线性插值去装科学计算栈。

目标函数
--------
    min  Σ_k P(a_k)·L                     （L = 每段时长，P 由 energy_model 给）
    s.t. T_N ≤ T_target + tol_K            （终端，软约束但权重压倒能耗）
         T_k ≤ T_max（可选全程红线）
能耗项只认两个固定函数，切换成本 / 寿命成本 / 噪声成本都不在此 —— 它们不是电耗。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from . import params as P
from .energy_model import Action, build_action_set
from .thermal_model import ThermalParams


@dataclass
class SolverConfig:
    min_hold_s: float = P.MIN_HOLD_S   # 动作最小保持时长 [s]（tau/10 ≈ 172，取 300）
    tol_K: float = P.TOL_K             # 终端达标容差 [K]
    w_terminal: float = 1.0e6          # 终端未达标线性罚斜率 [J/K]
    w_infeasible: float = 1.0e7        # 终端未达标固定跳变罚 [J]
    w_redline: float = 1.0e5           # 红线越界软罚 [J/(K·s)]
    allow_5a: bool = P.ALLOW_5A
    grid_dK: float = P.GRID_DK
    grid_margin: float = 8.0


@dataclass
class Segment:
    """一段恒定动作。"""

    action: Action
    duration_s: float
    T_start: float
    T_end: float

    @property
    def energy_j(self) -> float:
        return self.action.energy(self.duration_s)

    def as_dict(self, index: int = 0) -> dict:
        return {
            "index": index,
            "v_fan": self.action.v_fan,
            "i_tec": self.action.i_tec,
            "power_w": round(self.action.power, 4),
            "duration_s": round(self.duration_s, 1),
            "T_start": round(self.T_start, 3),
            "T_end": round(self.T_end, 3),
            "energy_wh": round(self.energy_j / 3600.0, 5),
        }


@dataclass
class SolveResult:
    ok: bool
    plan: List[Segment] = field(default_factory=list)
    traj: List[float] = field(default_factory=list)
    energy_j: float = 0.0
    final_T: float = float("nan")
    message: str = ""
    baseline_j: float = 0.0

    @property
    def energy_wh(self) -> float:
        return self.energy_j / 3600.0

    @property
    def baseline_wh(self) -> float:
        return self.baseline_j / 3600.0

    @property
    def saving(self) -> float:
        if self.baseline_j <= 0:
            return float("nan")
        return 1.0 - self.energy_j / self.baseline_j


def solve(
    t_now: float,
    t_target: float,
    horizon_s: float,
    tenv: float,
    twater: float = P.TWATER_DEFAULT,
    params: Optional[ThermalParams] = None,
    cfg: Optional[SolverConfig] = None,
    t_max: Optional[float] = None,
) -> SolveResult:
    """求「在 horizon_s 内降到 t_target 附近、总电耗最小」的分段动作序列。"""
    params = params or ThermalParams()
    cfg = cfg or SolverConfig()
    if horizon_s <= 0:
        raise ValueError("时限必须为正")

    # ---- 段结构：段数不是优化出来的，是算出来的 -------------------------
    n_seg = max(1, int(horizon_s // cfg.min_hold_s))
    seg_len = horizon_s / n_seg

    actions = build_action_set(include_5a=cfg.allow_5a)
    n_act = len(actions)

    # ---- 温度网格 ------------------------------------------------------
    # 上界必须覆盖 t_now，不能被 t_max 截断 —— 否则起点落在网格外，前向执行会被
    # clip 到错误格点（表现为「选了远低于必要功率的动作」，很难从结果反推原因）。
    b = params.free_equilibrium(tenv, twater)
    lo = min(t_target, t_now, b) - cfg.grid_margin
    hi = max(t_now, b) + cfg.grid_margin
    n_grid = int(round((hi - lo) / cfg.grid_dK)) + 1
    dk = cfg.grid_dK
    inv_dk = 1.0 / dk
    grid = [lo + k * dk for k in range(n_grid)]

    alpha = 1.0 - math.exp(-seg_len / params.tau_s)
    tss = [params.steady_state(a, tenv, twater) for a in actions]
    seg_cost = [a.power * seg_len for a in actions]
    # trans = grid + (tss - grid)·α 展开成「g·(1-α) + tss·α」，逐格计算时省一次减法
    keep = 1.0 - alpha
    tss_shift = [t * alpha for t in tss]

    # ---- 终端代价：容差内零罚 + 超差重罚（lexicographic：先达标、后省电） ----
    # 不能用一个线性软惩罚：线性罚会让求解器为了再压低 0.04 K 而多花一倍电。
    # eps 不能省：grid 是 lo + k·dK 累加出来的，恰好落在容差边界的格点可能是
    # 38.050000000000004，严格 `slack > 0` 会把它判成不可行并罚 1e7，
    # 策略表插值又把罚金摊到邻近温度 —— 表现为「明明有更省且达标的解却选了贵 17% 的」。
    t_lim = t_target + cfg.tol_K + 1e-9
    w_term = cfg.w_terminal
    w_inf = cfg.w_infeasible
    v_next = []
    for g in grid:
        if g > t_lim:
            v_next.append(w_term * (g - t_lim) + w_inf)
        else:
            v_next.append(0.0)

    # ---- 反向递推 ------------------------------------------------------
    # 每个格点上做「线性插值取下一段代价 + 跨动作取最小」。逐动作更新最优表，
    # 不建 (A, G) 矩阵 —— 内存 O(G)，单段 O(A·G) 次浮点运算。
    x_max = n_grid - 1.000001
    w_red = cfg.w_redline
    policy: List[List[int]] = []
    for _s in range(n_seg):
        policy.append([0] * n_grid)

    arange_g = range(n_grid)
    for s in range(n_seg - 1, -1, -1):
        best_cost = [0.0] * n_grid      # 当前段从各格点出发的最优代价（初始占位）
        best_act = [0] * n_grid
        for ai in range(n_act):
            sc = seg_cost[ai]
            k_shift = tss_shift[ai]
            # 第 0 个动作直接填充（相当于初始化），其余动作只在严格更优时替换，
            # 与 np.argmin 的「并列取首个」语义一致。
            init = (ai == 0)
            for j in arange_g:
                # 下一段结束时的温度
                tq = grid[j] * keep + k_shift
                x = (tq - lo) * inv_dk
                if x < 0.0:
                    x = 0.0
                elif x > x_max:
                    x = x_max
                i0 = int(x)
                f = x - i0
                vn = v_next[i0] * (1.0 - f) + v_next[i0 + 1] * f
                cost = sc + vn
                if t_max is not None:
                    over = tq - t_max
                    if over > 0.0:
                        cost += (w_red * over) * seg_len
                if init or cost < best_cost[j]:
                    best_cost[j] = cost
                    best_act[j] = ai
        policy[s] = best_act
        v_next = best_cost

    # ---- 前向执行 ------------------------------------------------------
    t = float(t_now)
    traj = [t]
    plan: List[Segment] = []
    energy = 0.0
    for s in range(n_seg):
        i = int(round((t - lo) * inv_dk))
        i = max(0, min(n_grid - 1, i))
        a = actions[policy[s][i]]
        t_next = params.advance(t, a, seg_len, tenv, twater)
        plan.append(Segment(a, seg_len, t, t_next))
        traj.append(t_next)
        energy += a.energy(seg_len)
        t = t_next

    # 基准：同场景下一直用最大功率（24 V + 3 A，禁用 5 A 时）
    a_max = Action(P.FULL_V, 5.0) if cfg.allow_5a else Action(P.FULL_V, P.FULL_I)
    baseline = a_max.power * horizon_s

    ok = t <= t_target + cfg.tol_K
    msg = "达标" if ok else f"未达标（差 {t - t_target:+.2f} K）"
    if not ok and not cfg.allow_5a:
        msg += "；5 A 档已禁用，可放开试"

    return SolveResult(ok=ok, plan=plan, traj=traj, energy_j=energy,
                       final_T=t, message=msg, baseline_j=baseline)


# --------------------------------------------------------------------------
# 纯风扇可达性判据
# --------------------------------------------------------------------------
def fan_only_reach(t_now: float, horizon_s: float, tenv: float,
                   twater: float = P.TWATER_DEFAULT,
                   params: Optional[ThermalParams] = None,
                   v_fan: float = P.FULL_V) -> float:
    """只靠风扇（I=0）在 horizon_s 后能达到的温度。

    这个判据比跑一遍 DP 更有用，因为决策本质是**阈值型**的：风扇能达标就绝不该
    开 TEC（能效差一个数量级以上）；够不够，用这个式子直接算。
    """
    params = params or ThermalParams()
    return params.advance(t_now, Action(v_fan, 0.0), horizon_s, tenv, twater)


def fan_only_is_enough(t_now: float, t_target: float, horizon_s: float, tenv: float,
                       twater: float = P.TWATER_DEFAULT,
                       params: Optional[ThermalParams] = None,
                       tol_k: float = P.TOL_K) -> tuple:
    """返回 (是否够, 纯风扇可达温度, 余量)；余量接近 0（±0.2 K）说明正处在决策临界点。"""
    t_reach = fan_only_reach(t_now, horizon_s, tenv, twater, params)
    margin = t_reach - t_target
    return (margin <= tol_k, t_reach, margin)
