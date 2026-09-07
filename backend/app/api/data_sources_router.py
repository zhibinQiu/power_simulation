"""统一数据源接入 API（能碳一体机 + 经中间件接入的外部数据源/模拟数据）。

- GET   /api/data-sources           统一数据源列表（类型 + 配置 + 运行时状态 + 中间件服务状态）
- POST  /api/data-sources/toggle    启停某数据源 {id, enabled}
- POST  /api/data-sources/save      保存配置并同步到中间件 {id, name?, config?, enabled?}
- POST  /api/data-sources/add       注册新外部数据源到中间件 {name?, config?}
- POST  /api/data-sources/remove    注销外部数据源 {id}
- POST  /api/data-sources/test      测试接入配置连通性 {config}（不落盘）
- GET   /api/data-sources/types     可用接入类型与参数 schema

说明：box（能碳一体机）为平台订阅通道的登记项，无需手工配置（Broker 在
「系统连接图 → 云端配置」设置）；external（外部数据源，含模拟数据）为「注册到
数据中间件」的数据源——平台登记 box 前缀/target 并把采集参数注册到中间件，
中间件采集后发布到其内置 Broker，平台直接订阅中间件取数。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from .. import data_sources

router = APIRouter(prefix="/api/data-sources", tags=["数据源接入"])


def _err(msg: str) -> Dict[str, Any]:
    return {"ok": False, "error": msg}


@router.get("")
def data_sources_list():
    """统一数据源列表（一体机/外部源并列，含配置、运行状态与中间件服务状态）。"""
    return data_sources.list_sources(force=False)


@router.post("/toggle")
def data_sources_toggle(payload: Dict[str, Any]):
    """启停某数据源：{id, enabled}（external 同时启停中间件侧适配器采集）。"""
    if not isinstance(payload, dict):
        return _err("请求体必须为 JSON 对象")
    source_id = str(payload.get("id") or "")
    if not source_id:
        return _err("缺少数据源 id")
    enabled = bool(payload.get("enabled"))
    try:
        return data_sources.toggle(source_id, enabled)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"操作中间件失败：{e}")


@router.post("/save")
def data_sources_save(payload: Dict[str, Any]):
    """保存数据源配置并同步到中间件：{id, name?, config?, enabled?}。

    external 的 config 结构：{box（发布前缀）, adapter（接入类型，当前 mqtt）,
    params（类型专属参数）, desc}。（历史 target 自动关联已取消）
    """
    if not isinstance(payload, dict):
        return _err("请求体必须为 JSON 对象")
    source_id = str(payload.get("id") or "")
    if not source_id:
        return _err("缺少数据源 id")
    try:
        return data_sources.save(
            source_id,
            name=payload.get("name"),
            config=payload.get("config"),
            enabled=payload.get("enabled"),
        )
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"同步中间件失败：{e}")


@router.post("/add")
def data_sources_add(payload: Dict[str, Any]):
    """注册新外部数据源到中间件：{name?, config?, enabled?}（默认停用）。"""
    if not isinstance(payload, dict):
        payload = {}
    try:
        return data_sources.add_external(
            name=payload.get("name"),
            config=payload.get("config"),
            enabled=bool(payload.get("enabled", False)),
        )
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"注册到中间件失败：{e}")


@router.post("/remove")
def data_sources_remove(payload: Dict[str, Any]):
    """注销外部数据源：{id}（平台内置 box 不可删除；中间件侧同步注销）。"""
    if not isinstance(payload, dict):
        return _err("请求体必须为 JSON 对象")
    source_id = str(payload.get("id") or "")
    if not source_id:
        return _err("缺少数据源 id")
    try:
        return data_sources.remove(source_id)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"注销中间件数据源失败：{e}")


@router.post("/test")
def data_sources_test(payload: Dict[str, Any]):
    """测试外部源接入配置（真实探测连通性，不保存）：{config, id?}。"""
    if not isinstance(payload, dict):
        return _err("请求体必须为 JSON 对象")
    try:
        res = data_sources.test_config(payload.get("config") or {},
                                       payload.get("id") or "")
        return {"ok": bool(res.get("ok")), **res}
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"测试失败：{e}")


@router.get("/types")
def data_sources_types():
    """可用接入类型与参数 schema（来自中间件适配器注册表）。"""
    return {"ok": True, "types": data_sources.adapter_types()}
