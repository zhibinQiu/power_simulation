"""编排方案持久化接口（流程编排 / AI 群控编排）。

此前编排方案只存在浏览器 localStorage，开发机做好的编排无法带到服务器。
本接口把编排数据落到 ``backend/data/designs/<bucket>.json``（按场景分档），
随 ``platform/bs-deploy/update.sh`` 同步到各实例：

  GET    /api/designs/{bucket}             -> 整桶数据 { sceneId: payload }
  GET    /api/designs/{bucket}/{scene}     -> 单场景编排数据（不存在返回 null）
  PUT    /api/designs/{bucket}             -> 写入某场景 { scene, data }
  PUT    /api/designs/agc/running          -> 只写 AI 群控运行态 { scene, running }（不动 designs）
  DELETE /api/designs/{bucket}/{scene}     -> 删除某场景编排数据

bucket 白名单：flow（流程编排）/ agc（AI 群控编排）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.scene.design_store import (
    BUCKETS,
    delete_scene,
    read_bucket,
    read_last_scene,
    read_scene,
    update_scene_fields,
    write_last_scene,
    write_scene,
)

router = APIRouter()


class DesignPayload(BaseModel):
    scene: str = Field(default="steel", description="场景 id（与 /api/scenes 的 id 一致）")
    data: Any = None


class LastScenePayload(BaseModel):
    scene: str = Field(..., description="场景 id")
    label: str = Field(default="", description="工程显示名（仅用于提示）")


class RunningPayload(BaseModel):
    scene: str = Field(default="steel", description="场景 id（与 /api/scenes 的 id 一致）")
    running: List[str] = Field(default_factory=list, description="正在运行的模型 id（同时只允许一个）")


@router.get("/api/designs/{bucket}")
def get_bucket(bucket: str) -> Dict[str, Any]:
    """读取整个编排桶（前端启动时据此恢复本场景编排）。"""
    try:
        return {"ok": True, "bucket": bucket, "data": read_bucket(bucket)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/designs/{bucket}/{scene}")
def get_scene_design(bucket: str, scene: str) -> Dict[str, Any]:
    """读取某场景的编排数据；无存档返回 data=None（前端按默认方案构建）。"""
    try:
        return {"ok": True, "bucket": bucket, "scene": scene, "data": read_scene(bucket, scene)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/designs/{bucket}")
def put_scene_design(bucket: str, payload: DesignPayload) -> Dict[str, Any]:
    """保存某场景的编排数据（前端编排变更后调用，data 为整体覆盖）。"""
    if bucket not in BUCKETS:
        raise HTTPException(status_code=400, detail=f"未知的编排桶：{bucket}（可选：{', '.join(BUCKETS)}）")
    try:
        data = write_scene(bucket, payload.scene, payload.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "bucket": bucket, "scene": payload.scene, "data": data}


@router.put("/api/designs/agc/running")
def put_agc_running(payload: RunningPayload) -> Dict[str, Any]:
    """**只写 AI 群控的运行态**（启停），不动 designs。

    编排改动改为手动提交后，启停若仍走整档 PUT ``/api/designs/agc``，
    就会把本端内存里尚未提交的清单一起推上去，覆盖掉别人已提交的版本。
    这里只合并 ``running`` 字段；``found=False`` 表示服务端还没有该场景存档
    （前端应提示「先提交再启动」）。
    """
    try:
        found = update_scene_fields("agc", payload.scene, {"running": list(payload.running or [])})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "scene": payload.scene, "found": found}


@router.get("/api/agc/runtime")
def get_agc_runtime() -> Dict[str, Any]:
    """AI 群控服务端运行器状态：运行器是否在线、哪些模型在运行、各模型最近一轮执行结果。

    前端据此展示「运行中」绿色标识与画布高亮 —— 执行发生在服务端，因此关掉浏览器也照跑。
    """
    from ..domain.scene import agc_runner
    return agc_runner.runtime()


@router.get("/api/workspace/last-scene")
def get_last_scene() -> Dict[str, Any]:
    """全局「最后打开的工程」（{ scene, label, ts }；无记录返回 {}）。

    平台没有用户体系，所有人共用官网这一份记录：换浏览器 / 换电脑打开时自动落到
    同一个工程，避免「在机房温控建的策略，换个浏览器因为在默认钢包里而看不到」。
    """
    return {"ok": True, "data": read_last_scene()}


@router.put("/api/workspace/last-scene")
def put_last_scene(payload: LastScenePayload) -> Dict[str, Any]:
    """记下最后打开的工程（任何人切换工程都更新这一份全局记录）。"""
    try:
        data = write_last_scene(payload.scene, payload.label)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "data": data}


@router.delete("/api/designs/{bucket}/{scene}")
def delete_scene_design(bucket: str, scene: str) -> Dict[str, Any]:
    """删除某场景的编排存档（清空画布 / 删除编排模型时用）。"""
    try:
        data = delete_scene(bucket, scene)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "bucket": bucket, "scene": scene, "data": data}
