"""核心仿真 REST 路由（接口层）。

职责：HTTP 参数校验 / 请求响应映射；业务用例编排统一委托 application 服务层
（simulation_service / strategy_service / optimizer_service），路由本身不含业务实现。

迁移历史：端点自 main.py 整体迁入（2026-08），路径与响应契约保持完全兼容。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..application.optimizer_service import optimizer_service
from ..application.simulation_service import simulation_service
from ..application.strategy_service import strategy_service
from ..cluster import cluster_devices
from ..models import (ParseRequest, ParseResult, ParsedOp, ProcessModel,
                      SimulateRequest, SimulateResponse, Strategy)

router = APIRouter()


# ------------------------- 健康 / 诊断 -------------------------

@router.get("/api/health")
def health():
    return {"status": "ok", "service": "steel-carbon-twin"}


@router.get("/api/cache/stats")
def cache_stats():
    """仿真缓存命中率（诊断用）：连续重复仿真（前端轮询/防抖后请求）应命中缓存。"""
    return simulation_service.cache_stats()


# ------------------------- 预置模型 / 元数据 -------------------------

@router.get("/api/model/preset", response_model=ProcessModel)
def get_preset():
    return simulation_service.get_preset()


@router.get("/api/presets/strategies")
def get_preset_strategies():
    return simulation_service.get_preset_strategies()


@router.get("/api/factors")
def get_factors():
    """返回默认排放因子表（燃料 NCV/CC、电网因子、碳酸盐/电极因子），供前端配置面板初始化。"""
    return simulation_service.get_factors()


@router.get("/api/param-schema")
def get_param_schema():
    """返回工序参数分级元数据（config/optim、label、单位、参考范围），供前端编辑器渲染。"""
    return simulation_service.get_param_schema()


@router.get("/api/devices")
def get_devices():
    """内置监测设备库：设备类型元数据 + 各工序设备规格 + 档位库。"""
    return simulation_service.get_devices()


# ------------------------- 解析 / 仿真 -------------------------

@router.post("/api/parse", response_model=ParseResult)
def parse(req: ParseRequest):
    """自然语言策略解析：优先 LLM 拆解，无 key / 超时 / 解析失败回退确定性启发式。"""
    units = [u.model_dump() for u in req.model.units] if req.model else None
    return simulation_service.parse(req.text, units)


@router.post("/api/simulate", response_model=SimulateResponse)
def do_simulate(req: SimulateRequest):
    """执行基线仿真，必要时叠加策略操作并计算前后 delta。"""
    return simulation_service.simulate(req)


@router.post("/api/apply")
def apply_parsed(model: ProcessModel = Body(...),
                 ops: List[ParsedOp] = Body(default_factory=list),
                 factors: Optional[Dict[str, Any]] = Body(None)):
    """直接对当前流程应用一组操作（无需先保存）。前端以 JSON body 提交 {model, ops, factors}。"""
    return simulation_service.apply(model, ops, factors)


# ------------------------- 策略库 CRUD -------------------------

@router.get("/api/strategies", response_model=List[Strategy])
def list_strategies():
    return strategy_service.list()


@router.post("/api/strategies", response_model=Strategy)
def create_strategy(
    name: str = Body(..., description="策略名称"),
    description: str = Body("", description="策略描述"),
    raw_text: str = Body("", description="策略原文"),
    ops: List[ParsedOp] = Body(default_factory=list, description="策略操作列表"),
):
    """创建策略。前端以 JSON body 提交 {name, description, raw_text, ops}，故参数需显式声明为 Body。"""
    return strategy_service.create(name=name, description=description,
                                   raw_text=raw_text, ops=ops)


@router.get("/api/strategies/{sid}", response_model=Strategy)
def get_strategy(sid: str):
    s = strategy_service.get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="strategy not found")
    return s


@router.put("/api/strategies/{sid}", response_model=Strategy)
def update_strategy(sid: str, name: Optional[str] = None, description: Optional[str] = None,
                    raw_text: Optional[str] = None, ops: Optional[str] = None):
    """更新策略的名称/描述/原文/操作（None 字段保持原值）。ops 为 JSON 数组字符串（如 ops=[{...}]），可为空。"""
    parsed_ops = None
    if ops is not None and ops.strip():
        try:
            parsed_ops = [ParsedOp.model_validate(o) for o in json.loads(ops)]
        except Exception:  # noqa: BLE001
            parsed_ops = None
    s = strategy_service.update(sid, name=name, description=description,
                                raw_text=raw_text, ops=parsed_ops)
    if not s:
        raise HTTPException(status_code=404, detail="strategy not found")
    return s


@router.delete("/api/strategies/{sid}")
def delete_strategy(sid: str):
    return {"deleted": strategy_service.delete(sid)}


@router.post("/api/strategies/{sid}/apply")
def apply_strategy(sid: str, model: ProcessModel = Body(...),
                   factors: Optional[Dict[str, Any]] = Body(None)):
    """将已保存策略应用到当前流程。前端以 JSON body 提交 {model, factors}。"""
    result = strategy_service.apply_to(sid, model, factors)
    if "error" in result:
        return result
    return result


# ------------------------- 求解 / 分析能力（守恒审计） -------------------------

@router.post("/api/audit")
def do_audit(model: ProcessModel = Body(...)):
    """碳元素守恒审计：逐工序核对碳输入与各去向（排CO₂/固钢/入渣/捕集/产品携出），返回闭合余量。"""
    return simulation_service.audit(model)


# ------------------------- 工况数据分析（聚类） -------------------------

class ClusterSeriesPoint(BaseModel):
    t: float
    v: float


class ClusterDevice(BaseModel):
    id: str
    label: Optional[str] = None
    unit: Optional[str] = None
    series: List[ClusterSeriesPoint] = Field(default_factory=list)


class ClusterRequest(BaseModel):
    """聚类分析请求：多台设备在所选时间段内的 {t, v} 序列（前端按时间窗过滤后上传）。"""
    devices: List[ClusterDevice] = Field(..., min_length=1)
    k: Optional[int] = Field(None, ge=2, le=10, description="簇数，缺省自动选择")


@router.post("/api/cluster")
def do_cluster(req: ClusterRequest):
    """多设备时间序列聚类分析（工况数据分析 → 聚类分析）。

    输入：{devices: [{id, label?, unit?, series:[{t,v}]}], k?}
    输出：{n, k, method, silhouette, features, clusters:[{cluster, size, devices, centroid, summary}]}
    """
    try:
        return cluster_devices(
            [d.model_dump() for d in req.devices],
            k=req.k,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------- 命令行窗口：自然语言聊天 -------------------------

class ChatRequest(BaseModel):
    text: str
    history: List = Field(default_factory=list)  # [[role, content], ...]
    mode: str = "chat"          # chat | code | plan


@router.post("/api/chat")
def chat(req: ChatRequest):
    """命令行窗口的自然语言对话端点。无 LLM key / 网络异常时返回 ok=False 与兜底提示。"""
    return simulation_service.chat(req.text, req.history, req.mode)


@router.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """流式聊天端点（SSE）：逐段推送增量文本，前端逐字渲染；失败时流内产出兜底提示。"""
    return StreamingResponse(
        simulation_service.chat_stream(req.text, req.history, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------- AI 优化模型（GA / PSO / RL 在线训练） -------------------------
# 训练上下文同步：前端在流程模型变化/进入策略面板时调用；模型变更自动重建各优化器。
# 后台定时训练由 optimizers.TrainingScheduler 常驻线程驱动（无需前端轮询触发训练）。

def _optimizer_or_404(oid: str):
    try:
        return optimizer_service.get_state(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")


@router.post("/api/optimizers/context")
def set_optimizer_context(model: ProcessModel = Body(...),
                          factors: Optional[Dict[str, Any]] = Body(None)):
    """同步 AI 优化训练上下文（当前流程模型 + 排放因子）。"""
    return optimizer_service.set_context(model, factors)


@router.get("/api/optimizers")
def list_optimizers():
    """AI 优化模型列表与训练状态（前端每数秒轮询，展示随实时数据逐渐变优）。"""
    return optimizer_service.list_states()


@router.get("/api/optimizers/{oid}")
def get_optimizer(oid: str):
    return _optimizer_or_404(oid)


@router.post("/api/optimizers/{oid}/start")
def start_optimizer(oid: str):
    """开启自动训练：后台调度线程将随实时传感器数据定时迭代。"""
    try:
        return optimizer_service.start(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/optimizers/{oid}/stop")
def stop_optimizer(oid: str):
    try:
        return optimizer_service.stop(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")


@router.post("/api/optimizers/{oid}/train")
def train_optimizer(oid: str, steps: int = Body(1, ge=1, le=50, embed=True)):
    """手动触发训练（steps 步），用于无自动调度时的即时迭代。"""
    try:
        return optimizer_service.train(oid, steps)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/optimizers/{oid}/reset")
def reset_optimizer(oid: str):
    try:
        return optimizer_service.reset(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")


@router.put("/api/optimizers/{oid}/hyper")
def set_optimizer_hyper(oid: str, patch: Dict[str, float] = Body(...)):
    try:
        return optimizer_service.set_hyper(oid, patch)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")


@router.post("/api/optimizers/{oid}/apply")
def apply_optimizer(oid: str):
    """把「当前生效版本」的最优参数应用到流程（返回新模型 + 仿真结果）。"""
    try:
        return optimizer_service.apply(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.put("/api/optimizers/{oid}/settings")
def set_optimizer_settings(oid: str, patch: Dict[str, Any] = Body(...)):
    """更新控制与自训练设置：{auto_control?: bool, schedule?: {interval?, window?}}。"""
    try:
        return optimizer_service.set_settings(oid, patch)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")


@router.post("/api/optimizers/{oid}/archive")
def archive_optimizer(oid: str):
    """把当前最优参数保存为模型版本（仅优于当前版本才替换生效）。"""
    try:
        return optimizer_service.archive(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.post("/api/optimizers/{oid}/switch")
def switch_optimizer_version(oid: str, version_id: str = Body(..., embed=True)):
    """在历史模型版本间切换（旧版本保留，可随时切回）。"""
    try:
        return optimizer_service.switch_version(oid, version_id)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/optimizers/{oid}/ack")
def ack_optimizer(oid: str):
    """确认提醒：清除手动调优提醒 / 自动控制待下发标记。"""
    try:
        return optimizer_service.ack(oid)
    except KeyError:
        raise HTTPException(404, "未知的优化模型")
