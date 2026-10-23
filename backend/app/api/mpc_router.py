"""MPC 控温优化模型路由。

- GET  /api/mpc/status   模型可用性自检 + 启用状态 + 参数/档位一览
- POST /api/mpc/enable   {"enabled": true|false} 启用 / 停用（自检不过时拒绝启用）
- POST /api/mpc/plan     {"t_target": 39, "horizon_min": 12, ...} 目标温度 + 时限 -> 动作计划
- POST /api/mpc/apply    {"v_fan": 24, "i_tec": 3} 把某一段真正下发到设备点位
- POST /api/mpc/stop     {"reason": "..."} 两路输出归零
- GET  /api/mpc/mapping  v_fan / i_tec -> 设备点位的映射
- POST /api/mpc/loop/start {"t_target": 39, "horizon_min": 12} 下发当前段并启动闭环
- POST /api/mpc/loop/stop  {"reason": "..."} 停止闭环并归零
- GET  /api/mpc/loop     闭环状态（轮次、各设备本轮是否已反馈、当前动作、剩余时间）
- GET  /api/mpc/feedback 实时反馈点位（当前温度 / 室温 / 水桶温度）的 MQTT 读数
- GET  /api/mpc/logs     决策日志（新→旧，默认 100 条）
- DELETE /api/mpc/logs   清空决策日志

放在独立路由里而不是塞进 simulation_router：本域只依赖 app/domain/mpc 的纯计算，
不碰仿真状态机 / 实时数据，整体搬走不影响平台其它部分。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .rest import err, json_api

router = APIRouter()


@router.get("/api/mpc/status")
def mpc_status():
    """模型状态：能不能启用、为什么、以及全部标称参数。"""
    from ..domain.mpc import get_status
    try:
        return get_status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取 MPC 模型状态失败：{e}",
                "available": False, "enabled": False, "checks": []}


class EnableRequest(BaseModel):
    enabled: bool = Field(True, description="true 启用 / false 停用")


@router.post("/api/mpc/enable")
def mpc_enable(req: EnableRequest):
    """启用 / 停用 MPC 控制模型（状态落盘，重启后保持）。"""
    from ..domain.mpc import set_enabled
    try:
        return set_enabled(bool(req.enabled))
    except Exception as e:  # noqa: BLE001
        return err(f"切换 MPC 模型启用状态失败：{e}")


class PlanRequest(BaseModel):
    """规划请求体（仅作文档与类型说明；实际由 json_api 按 dict 接收，
    以便统一把参数错误转成 {"ok": false, "error": "..."} 的中文回执）。"""

    t_now: float = Field(45.0, description="当前温度 [℃]")
    t_target: float = Field(39.0, description="目标温度 [℃]（必须低于当前温度）")
    horizon_min: float = Field(12.0, description="要求在此时间内到达 [min]")
    tenv: Optional[float] = Field(None, description="室温 [℃]，缺省 26.5")
    twater: Optional[float] = Field(None, description="水桶温度 [℃]，缺省 31.0")
    t_max: Optional[float] = Field(None, description="全程红线 [℃]，可选")


@router.post("/api/mpc/plan")
@json_api("MPC 规划失败")
def mpc_plan(payload: dict):
    """目标温度 + 时限 -> 可达性判断、能耗最优分段动作、预测轨迹、恒定动作对比。"""
    from ..domain.mpc import get_plan

    t_now = float(payload.get("t_now", 45.0))
    t_target = float(payload.get("t_target", 39.0))
    horizon_min = float(payload.get("horizon_min", 12.0))
    tenv = payload.get("tenv")
    twater = payload.get("twater")
    t_max = payload.get("t_max")
    return get_plan(
        t_now=t_now,
        t_target=t_target,
        horizon_s=horizon_min * 60.0,
        tenv=None if tenv in (None, "") else float(tenv),
        twater=None if twater in (None, "") else float(twater),
        t_max=None if t_max in (None, "") else float(t_max),
    )


@router.get("/api/mpc/logs")
def mpc_logs(limit: int = 100):
    """决策日志：最近 limit 条「反馈温度 → 判定 → 下发档位 → 预计结果」。

    落盘在 backend/logs/mpc.log（JSONL），重启后仍在；页面刷新即从这里回读。
    """
    from ..domain.mpc import decision_log as DL
    try:
        items = DL.tail(limit)
        return {"ok": True, "count": len(items), "items": items, "path": DL.LOG_PATH}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取决策日志失败：{e}", "items": [], "count": 0}


@router.delete("/api/mpc/logs")
def mpc_logs_clear():
    """清空决策日志（演示前重置用）。"""
    from ..domain.mpc import decision_log as DL
    try:
        return {"ok": True, "cleared": DL.clear()}
    except Exception as e:  # noqa: BLE001
        return err(f"清空决策日志失败：{e}")


@router.get("/api/mpc/feedback")
def mpc_feedback():
    """左侧「目标与时限」三个输入的实时来源：zhileng-temp / env-temp / shuitong-temp。

    读数只来自 MQTT data/# 的真实上报；没有上报时 value=null（页面显示「无上报」），
    绝不回退到模拟值或默认值。
    """
    from ..domain.mpc import get_feedback
    try:
        return get_feedback()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取实时反馈失败：{e}", "sources": {}}


class ApplyRequest(BaseModel):
    """下发请求：把计划里的某一段写到设备点位。"""

    v_fan: float = Field(..., description="风扇设定电压 [V]，0~24 -> fengshan-power.voltage_set")
    i_tec: float = Field(..., description="制冷片设定电流 [A]，0~3 -> zhileng-power.current_set")
    hold_s: Optional[float] = Field(None, description="本段计划保持时长 [s]，仅用于日志")
    index: Optional[int] = Field(None, description="该段在计划里的序号（从 0 起），仅用于日志")
    note: str = Field("", description="日志里的一句话说明（如「第 2 段」）")
    dry_run: bool = Field(False, description="true = 只组装载荷不发布（现场联调核对点位用）")


@router.post("/api/mpc/apply")
@json_api("MPC 下发失败")
def mpc_apply(payload: dict):
    """把 (v_fan, i_tec) 真正下发到现场：风扇恒压写 voltage_set，制冷片恒流写 current_set。

    前置条件：模型自检通过 + 已启用。未启用时返回明确的中文错误，不会静默下发。
    dry_run=true 时只校验并回显将要发送的 6 条载荷，不碰设备。
    """
    from ..domain.mpc import apply_step

    return apply_step(
        v_fan=float(payload.get("v_fan")),
        i_tec=float(payload.get("i_tec")),
        hold_s=payload.get("hold_s"),
        index=payload.get("index"),
        note=str(payload.get("note") or ""),
        dry_run=bool(payload.get("dry_run")),
    )


@router.post("/api/mpc/stop")
@json_api("MPC 停止失败")
def mpc_stop(payload: dict):
    """两路输出归零（先断 output_on 再清设定）。不受「是否启用」限制。"""
    from ..domain.mpc import stop_output

    body = payload or {}
    return stop_output(reason=str(body.get("reason") or "手动停止"),
                       dry_run=bool(body.get("dry_run")))


@router.get("/api/mpc/mapping")
def mpc_mapping():
    """动作字段 -> 设备点位映射（页面显示「下发到哪」，也便于现场核对配置）。"""
    from ..domain.mpc import get_mapping
    try:
        return {"ok": True, "mapping": get_mapping()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取下发映射失败：{e}", "mapping": {}}


# --------------------------------------------------------------------------
# 闭环执行：反馈齐一轮 -> 重解 -> 下发当前段
# --------------------------------------------------------------------------
class LoopStartRequest(BaseModel):
    """闭环启动请求。"""

    t_target: float = Field(..., description="目标温度 [℃]（必须低于当前温度）")
    horizon_min: float = Field(12.0, description="到达时限 [min]，从点击下发这一刻起算")
    dry_run: bool = Field(False, description="true = 只算 + 只组装载荷，不启动闭环、不发 MQTT")
    note: str = Field("", description="日志里的一句话说明")


@router.post("/api/mpc/loop/start")
@json_api("MPC 闭环启动失败")
def mpc_loop_start(payload: dict):
    """用最新反馈求解一次、**立即下发当前段**，然后进入闭环。

    闭环的节拍不是计时器，而是「三台反馈设备（zhileng-temp / env-temp / shuitong-temp）
    各出现一次新上报」：每齐一轮就用最新温度 + 剩余时间重解一次，并把新的当前段
    下发到风扇电源 / 制冷片电源。
    """
    from ..domain.mpc import loop_start

    return loop_start(
        t_target=float(payload.get("t_target")),
        horizon_s=float(payload.get("horizon_min", 12.0)) * 60.0,
        dry_run=bool(payload.get("dry_run")),
        note=str(payload.get("note") or ""),
    )


@router.post("/api/mpc/loop/stop")
@json_api("MPC 闭环停止失败")
def mpc_loop_stop(payload: dict):
    """停止闭环并两路归零（停止不受 dry_run 影响，永远真执行）。"""
    from ..domain.mpc import loop_stop

    body = payload or {}
    return loop_stop(str(body.get("reason") or "页面停止闭环"))


@router.get("/api/mpc/loop")
def mpc_loop_state():
    """闭环状态：是否运行、轮次、当前动作、各设备本轮是否已反馈、剩余时间、流水。"""
    from ..domain.mpc import loop_status
    try:
        return loop_status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "running": False, "error": f"读取闭环状态失败：{e}"}
