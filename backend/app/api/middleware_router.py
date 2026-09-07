"""数据中间件服务 API（平台 ⇄ 中间件：连接配置、状态、数据源类型、对账同步）。

- GET  /api/middleware/status     中间件服务状态（在线/内置 Broker/数据源数）
- POST /api/middleware/config     保存中间件连接配置（地址/Token/Broker 端口）并热重连订阅
- POST /api/middleware/test       测试中间件连通性（不改配置）
- POST /api/middleware/sync       与中间件对账（本地已登记但中间件缺失的外部源补注册）
- GET  /api/middleware/types      可用数据源接入类型与参数 schema（前端表单渲染）
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from .. import middleware_client

router = APIRouter(prefix="/api/middleware", tags=["数据中间件服务"])


def _err(msg: str) -> Dict[str, Any]:
    return {"ok": False, "error": msg}


@router.get("/status")
def middleware_status():
    """中间件服务状态：在线与否、内置 Broker、输出桥、已注册数据源数。"""
    st = middleware_client.status(force=True)
    return {"ok": True, "middleware": st,
            "config": middleware_client.public_config()}


@router.post("/config")
def middleware_save_config(payload: Dict[str, Any]):
    """保存中间件连接配置：{enabled?, base_url?, token?, broker?: {host, port, username, password}}。

    保存后立即按新地址重连「中间件」订阅端点（云端 Broker 订阅不受影响）。
    """
    if not isinstance(payload, dict):
        return _err("请求体必须为 JSON 对象")
    try:
        cfg = middleware_client.save_config(payload)
    except ValueError as e:
        return _err(str(e))
    try:
        from .. import mqtt_source
        mqtt_source.restart_middleware()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "config": cfg,
            "middleware": middleware_client.status(force=True),
            "note": "中间件配置已保存并应用（订阅开关变化时平台订阅端点随之启停）"}


@router.post("/test")
def middleware_test(payload: Dict[str, Any]):
    """测试中间件连通性：可用临时地址测试（{base_url?, token?}），不落盘。"""
    if not isinstance(payload, dict):
        payload = {}
    tmp = {}
    for k in ("base_url", "token"):
        if payload.get(k) is not None:
            tmp[k] = payload[k]
    if tmp:
        saved = middleware_client.load_config()
        merged = dict(saved)
        merged.update(tmp)
        # 用临时配置探测：直接复用 _request 的底层逻辑（不走全局缓存）
        try:
            import httpx
            url = str(merged.get("base_url") or "").rstrip("/")
            headers = {"Content-Type": "application/json"}
            if merged.get("token"):
                headers["Authorization"] = f"Bearer {merged['token']}"
            with httpx.Client(timeout=6.0) as cli:
                r = cli.get(f"{url}/api/health", headers=headers)
            data = r.json()
            if r.status_code >= 400:
                return _err(data.get("error") or f"HTTP {r.status_code}")
            return {"ok": True, "detail": data,
                    "note": f"中间件可达（{url}），内置 Broker "
                            f"{'运行中' if (data.get('broker') or {}).get('running') else '未运行'}"}
        except Exception as e:  # noqa: BLE001
            return _err(f"无法连接中间件：{e}")
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
