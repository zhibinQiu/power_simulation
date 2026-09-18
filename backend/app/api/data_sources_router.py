"""统一数据源接入 API（能碳一体机 + 经中间件接入的外部数据源/模拟数据）。

- GET   /api/data-sources           统一数据源列表（类型 + 配置 + 运行时状态 + 中间件服务状态）
- GET   /api/data-sources/signals   可绑定信号目录（按源分组的设备及其全部数值，供编排绑定实测值）
- POST  /api/data-sources/toggle    启停某数据源 {id, enabled}
- POST  /api/data-sources/save      保存配置并同步到中间件 {id, name?, config?, enabled?}
- POST  /api/data-sources/add       注册新外部数据源到中间件 {name?, config?}
- POST  /api/data-sources/remove    删除数据源 {id}（内置源与外部源统一，无例外）
- POST  /api/data-sources/restore   恢复被删除的平台内置数据源 {id}（默认 box 能碳一体机）
- POST  /api/data-sources/test      测试接入配置连通性 {config}（不落盘）

可用接入类型见 /api/middleware/types（中间件适配器注册表，单一来源，不在此重复暴露）。

说明：box（能碳一体机）为平台订阅通道的登记项，无需手工配置（Broker 在
「系统连接图 → 云端配置」设置）；external（外部数据源，含模拟数据）为「注册到
数据中间件」的数据源——平台登记 box 前缀并把采集参数注册到中间件，中间件采集
转换为标准 MQTT 后直发云端 Broker，平台经唯一订阅入口（云端 Broker）取数。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from .. import data_sources
from .rest import json_api as _json_api

router = APIRouter(prefix="/api/data-sources", tags=["数据源接入"])


def _id(payload: Dict[str, Any], default: str = "") -> str:
    """取数据源 id；缺失抛 ValueError（由 _json_api 转成回执）。"""
    sid = str(payload.get("id") or default).strip()
    if not sid:
        raise ValueError("缺少数据源 id")
    return sid


@router.get("")
def data_sources_list():
    """统一数据源列表（一体机/外部源并列，含配置、运行状态与中间件服务状态）。"""
    return data_sources.list_sources(force=False)


@router.get("/signals")
def data_sources_signals():
    """可绑定信号目录：按数据源分组列出当前上报的设备及其全部数值（供编排绑定实测值）。

    一台设备可上报多个数值（values[] 逐条列出），每条带稳定 key（box/device/field）。"""
    return data_sources.signal_catalog()


@router.post("/toggle")
@_json_api("操作中间件失败")
def data_sources_toggle(payload: Dict[str, Any]):
    """启停某数据源：{id, enabled}（external 同时启停中间件侧适配器采集）。"""
    return data_sources.toggle(_id(payload), bool(payload.get("enabled")))


@router.post("/save")
@_json_api("同步中间件失败")
def data_sources_save(payload: Dict[str, Any]):
    """保存数据源配置并同步到中间件：{id, name?, config?, enabled?}。

    external 的 config 结构：{box（发布前缀）, adapter（接入类型，当前 mqtt）,
    params（类型专属参数）, desc}。（历史 target 自动关联已取消）
    """
    return data_sources.save(
        _id(payload),
        name=payload.get("name"),
        config=payload.get("config"),
        enabled=payload.get("enabled"),
    )


@router.post("/add")
@_json_api("注册到中间件失败", allow_empty=True)
def data_sources_add(payload: Dict[str, Any]):
    """注册新外部数据源到中间件：{name?, config?, enabled?}（默认停用）。"""
    return data_sources.add_external(
        name=payload.get("name"),
        config=payload.get("config"),
        enabled=bool(payload.get("enabled", False)),
    )


@router.post("/remove")
@_json_api("删除数据源失败")
def data_sources_remove(payload: Dict[str, Any]):
    """删除数据源：{id}。统一管理、无例外——内置源（能碳一体机）与外部源都可删除：

    - external：中间件侧同步注销采集；
    - box：平台立即停止采纳盒子上报数据（重启不再自动补建），可经 /restore 加回。
    """
    return data_sources.remove(_id(payload))


@router.post("/restore")
@_json_api("恢复内置数据源失败")
def data_sources_restore(payload: Dict[str, Any]):
    """恢复被删除的平台内置数据源：{id}（当前仅 box 能碳一体机；恢复后默认启用）。"""
    return data_sources.restore_builtin(_id(payload, default="box"))


@router.post("/test")
@_json_api("测试失败")
def data_sources_test(payload: Dict[str, Any]):
    """测试外部源接入配置（真实探测连通性，不保存）：{config, id?}。"""
    res = data_sources.test_config(payload.get("config") or {}, payload.get("id") or "")
    return {**res, "ok": bool(res.get("ok"))}
