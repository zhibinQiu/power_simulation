"""编排方案持久化接口（流程编排 / AI 群控编排）。

此前编排方案只存在浏览器 localStorage，开发机做好的编排无法带到服务器。
本接口把编排数据落到 ``backend/data/designs/<bucket>.json``（按场景分档），
随 ``platform/bs-deploy/update.sh`` 同步到各实例：

  GET    /api/designs/{bucket}             -> 整桶数据 { sceneId: payload }
  GET    /api/designs/{bucket}/{scene}     -> 单场景编排数据（不存在返回 null）
  PUT    /api/designs/{bucket}             -> 写入某场景 { scene, data }
  DELETE /api/designs/{bucket}/{scene}     -> 删除某场景编排数据

bucket 白名单：flow（流程编排）/ agc（AI 群控编排）。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.scene.design_store import (
    BUCKETS,
    delete_scene,
    read_bucket,
    read_scene,
    write_scene,
)

router = APIRouter()


class DesignPayload(BaseModel):
    scene: str = Field(default="steel", description="场景 id（与 /api/scenes 的 id 一致）")
    data: Any = None


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


@router.delete("/api/designs/{bucket}/{scene}")
def delete_scene_design(bucket: str, scene: str) -> Dict[str, Any]:
    """删除某场景的编排存档（清空画布 / 删除编排模型时用）。"""
    try:
        data = delete_scene(bucket, scene)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "bucket": bucket, "scene": scene, "data": data}
