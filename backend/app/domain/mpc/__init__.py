"""MPC 控温优化模型（迁移自 simulate_model/temp_optimize_model）。

模块构成
--------
- params.py  标称参数：功率函数系数、实测档位表、热模型参数、求解器/模式阈值。
             全平台只有这一处放「魔法数字」，其它模块一律从这里取。
- thermal_model.py 被控对象：一阶 RC 灰箱（T(h) = Tss + (T0-Tss)·e^(-h/tau)）。
- solver.py  决策：离散档位动态规划（不是连续 QP —— 硬件只认 8 档风扇 / 5 档电流）。
- service.py 服务层：可用性自检（能否启用）、目标温度 + 时限 -> 动作计划、
             把计划里的某一段下发到设备。
- actuator.py 执行器：v_fan -> fengshan-power.voltage_set（恒压）、
             i_tec -> zhileng-power.current_set（恒流），附 work_mode/output_on 前置。
- loop.py    闭环：三台反馈设备各上报一次 = 一轮 -> 用最新温度重解 -> 下发新的当前段。
             切换由「反馈齐一轮」驱动，不是按时长切段（现场采集周期不固定）。

为什么只迁移确定性部分
----------------------
原工程还有 models/xpred.py（12 头残差 MLP + torch checkpoint）与 modules/ 下的
预测/偏差/闭环控制器。它们解决的是「在线闭环跟踪」，而本平台这一页要回答的是
「给定目标温度和时限，能不能做到、要下发什么档位」—— 这一步完全由灰箱 + DP
决定，不依赖神经网络，也不需要 torch（平台后端依赖里没有它，也不该为这一页引入）。
被略去的部分与替代方案见 README.md「迁移范围」一节。
"""
from __future__ import annotations

from . import loop as _loop
from . import params as _params
from .feedback import get_feedback
from .service import (apply_step, get_mapping, get_plan, get_status,
                      set_enabled, stop_output)
from .solver import SolveResult, solve

MODEL_VERSION = _params.MODEL_VERSION
MODEL_NAME = _params.MODEL_NAME

__all__ = [
    "MODEL_NAME",
    "MODEL_VERSION",
    "SolveResult",
    "solve",
    "get_status",
    "get_plan",
    "get_feedback",
    "set_enabled",
    "apply_step",
    "stop_output",
    "get_mapping",
    "loop_start",
    "loop_stop",
    "loop_status",
]


def loop_start(t_target: float, horizon_s: float, *, dry_run: bool = False,
               note: str = "") -> dict:
    """求解一次 + 下发当前段 + 启动「反馈齐一轮就重解」的闭环。"""
    return _loop.start(t_target, horizon_s, dry_run=dry_run, note=note)


def loop_stop(reason: str = "手动停止", *, zero: bool = True) -> dict:
    """停止闭环（zero=True 时两路输出归零；停止永远真执行）。"""
    return _loop.stop(reason, zero=zero)


def loop_status() -> dict:
    """闭环状态快照（页面每 2 s 轮询）。"""
    return _loop.status()
