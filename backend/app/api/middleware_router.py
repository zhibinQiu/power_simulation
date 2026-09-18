"""数据中间件服务 API（平台 ⇄ 中间件：连接配置、状态、数据源类型、对账同步）。

- GET  /api/middleware/status     中间件服务状态（在线/运行形态/数据源数）
- POST /api/middleware/config     保存中间件连接配置（地址/Token）
- POST /api/middleware/test       测试中间件连通性（不改配置）
- POST /api/middleware/sync       与中间件对账（本地已登记但中间件缺失的外部源补注册）
- GET  /api/middleware/types      可用数据源接入类型与参数 schema（前端表单渲染）
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from .. import middleware_client
from .rest import json_api

router = APIRouter(prefix="/api/middleware", tags=["数据中间件服务"])


@router.get("/status")
def middleware_status():
    """中间件服务状态：在线与否、输出桥（云端 Broker 连接）、已注册数据源数。"""
    st = middleware_client.status(force=True)
    return {"ok": True, "middleware": st,
            "config": middleware_client.public_config()}


@router.post("/config")
@json_api("保存中间件配置失败")
def middleware_save_config(payload: Dict[str, Any]):
    """保存中间件连接配置：{enabled?, base_url?, token?}。

    中间件自身不跑 Broker，转换后的数据直发云端 Broker，因此保存后平台无需
    重连订阅——云端 Broker 订阅始终是唯一入口。
    """
    cfg = middleware_client.save_config(payload)
    return {"ok": True, "config": cfg,
            "middleware": middleware_client.status(force=True),
            "note": "中间件配置已保存并应用"}


@router.post("/test")
@json_api("无法连接中间件", allow_empty=True)
def middleware_test(payload: Dict[str, Any]):
    """测试中间件连通性：可用临时地址/Token 测试（{base_url?, token?}），不落盘。"""
    base = str(payload.get("base_url") or "").strip()
    token = payload.get("token")
    if base or token is not None:
        data = middleware_client.probe(base, str(token or ""))
        url = base or middleware_client.public_config().get("base_url") or ""
        return {"ok": True, "detail": data,
                "note": f"中间件可达（{url}），运行形态 {data.get('mode') or 'external'}"}
    st = middleware_client.status(force=True)
    return {"ok": bool(st.get("online")), "detail": st.get("detail") or {},
            "error": st.get("error") or "", "note": "已用当前配置探测"}


@router.post("/sync")
def middleware_sync():
    """与中间件对账：本地已登记但中间件缺失的外部数据源补注册。"""
    from .. import data_sources
    res = data_sources.sync_with_middleware()
    return {"ok": bool(res.get("ok")), **res}


@router.get("/types")
def middleware_types():
    """可用数据源接入类型（来自中间件注册表）。"""
    from .. import data_sources
    return {"ok": True, "types": data_sources.adapter_types()}
