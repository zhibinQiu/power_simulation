"""data_sources 包：统一数据源接入管理（门面 Facade）。

统一概念（用户诉求：能碳一体机接入 / 外部数据源 都是「一种数据源接入」）：
平台把每个向它提供实时数据的来源登记为一条数据源（id/type/name/enabled），统一列表、
统一启停、统一状态；所有源最终都汇入同一条摄取管道（订阅 → CLOUD_DEVICES/READINGS
→ links 关联 → 驱动仿真）：
- box       能碳一体机（KubeEdge 盒子）：数据经**云端 Broker** 主动上报，平台无独立
            运行线程；enabled 控制摄取侧是否采纳真实盒子消息。
- external  外部数据源：注册到**数据中间件**（platform/cloud-deploy/middleware/），
            由中间件采集并转换为标准 MQTT 发布到云端 Broker，平台按 box 前缀识别归属。
            模拟数据也是一种外部源：由独立服务（platform/cloud-deploy/sim-source/）
            生成后经中间件 mqtt 适配器接入——**平台与中间件自身都不产生模拟数据**。

平台订阅入口（见 mqtt_source.client）：**只有云端 Broker 一个**——一体机的 data/# 与
中间件转投的外部数据在同处该 Broker，共享同一条摄取管道，按 box 前缀归属到源条目。

包内分层（轻量化：门面只做编排，细节各有归属）：
- config.py    目录真源 + 派生视图缓存（enabled / box 前缀 / 外部源列表）
- external.py  外部源配置校验/规范化 + 注册请求体 + 运行状态
- status.py    运行状态组装（源类型 → 状态生成器策略表）
- signals.py   可绑定信号目录（带短缓存）
- 本文件       生命周期、列表/启停/增删改、连通性测试

生命周期：main.py lifespan 调 start()（登记默认源 + 与中间件对账同步）；
REST（/api/data-sources/*）热增删改启停（平台自身无采集线程需停止）。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

from . import config as _config
from . import external as _external
from . import signals as _signals
from . import status as _status
from ..integrations import middleware_client

TYPE_LABELS = _config.TYPE_LABELS
TYPE_DESC = _status.TYPE_DESC
signal_catalog = _signals.signal_catalog          # re-export（REST 与流程编排使用）

_lock = threading.RLock()


def reset_cache() -> None:
    """清空派生缓存（目录视图 + 信号目录 + 中间件读缓存）：写操作/测试复位后调用。"""
    _config.reset_cache()
    _signals.reset_cache()
    middleware_client.reset_cache()


def sync_with_middleware() -> Dict[str, Any]:
    """与中间件对账：把本地已登记但中间件缺失的外部源补注册（中间件重建后恢复）。

    返回 {ok, checked, registered, errors, online}。中间件不可达时不报错，仅标记。
    """
    out: Dict[str, Any] = {"ok": True, "checked": 0, "registered": 0, "errors": [],
                           "online": False}
    # 一次快照同时给出「中间件是否在线」与「已注册 id 列表」——
    # 原先 status(health) + list_sources 各发一次 HTTP，且两者缓存互不共享
    snap = middleware_client.sources_snapshot(force=True)
    out["online"] = bool(snap.get("online"))
    if not out["online"]:
        out["ok"] = False
        out["errors"].append(snap.get("error") or "中间件服务不可达")
        return out
    mw_ids = {str(s.get("id")) for s in (snap.get("sources") or [])}
    for src in _config.external_configs():
        out["checked"] += 1
        sid = str(src.get("id"))
        if sid in mw_ids:
            continue
        try:
            middleware_client.add_source(_external.middleware_payload(src))
            out["registered"] += 1
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"{src.get('name')}: {e}")
            out["ok"] = False
    return out


def start() -> Dict[str, Any]:
    """登记默认目录（box 缺失且未被用户删除时补建）并与中间件对账补注册。"""
    try:
        _config.load_config(force=True)
        ids = {str(s.get("id")) for s in _config.entries()}
        if "box" not in ids and "box" not in _config.builtin_removed_ids():
            _config.upsert_source(_config.builtin_template("box"))
    except Exception:  # noqa: BLE001
        pass
    sync = {"ok": False, "online": False, "errors": ["未执行"]}
    try:
        sync = sync_with_middleware()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "sync": sync,
            "sources": [s.get("id") for s in _config.entries(force=True)]}


# ------------------------- 状态 / 列表 -------------------------

def _middleware_view(snap: Dict[str, Any]) -> Dict[str, Any]:
    """列表页的中间件徽标视图（online/error 来自数据源快照，不额外请求 health）。"""
    return {
        "enabled": bool(snap.get("enabled")),
        "base_url": snap.get("base_url"),
        "token_set": bool(snap.get("token_set")),
        "online": bool(snap.get("online")),
        "error": snap.get("error") or "",
        "sources": len(snap.get("sources") or []),
        "detail": {},
        "types": [],
    }


def list_sources(force: bool = False) -> Dict[str, Any]:
    """统一数据源列表：目录条目 + 类型文案 + 运行时状态（含中间件服务状态）。

    一次中间件快照（sources_snapshot）同时供「每个外部源的运行状态」与「顶部在线徽标」
    使用——原先分别走 list_sources/health 两次 HTTP。
    """
    snap = middleware_client.sources_snapshot(force=force)
    mw_map = {str(s.get("id")): s for s in (snap.get("sources") or [])}
    out: List[Dict[str, Any]] = []
    for raw in _config.entries(force):
        view = _config.source_public_view(raw)
        t = view.get("type")
        view["label"] = TYPE_LABELS.get(t, t)
        view["desc"] = TYPE_DESC.get(t, "")
        view["status"] = _status.source_status(raw, mw_map)
        out.append(view)
    return {"ok": True, "sources": out, "middleware": _middleware_view(snap)}


# ------------------------- 启停 / 保存 / 增删 -------------------------

def _require(source_id: str) -> Dict[str, Any]:
    src = _config.find_source(source_id, force=True)
    if src is None:
        raise ValueError(f"数据源不存在：{source_id}")
    return src


def _changed(note: str) -> Dict[str, Any]:
    """写操作统一回执：清缓存 + 返回最新列表（前端一次拿到一致状态）。"""
    reset_cache()
    return {"ok": True, "note": note, "sources": list_sources(force=True)["sources"]}


def toggle(source_id: str, enabled: bool) -> Dict[str, Any]:
    """启停某数据源（box 影响摄取过滤；external 同时启停中间件适配器）。"""
    with _lock:
        src = _require(source_id)
        t = src.get("type")
        enabled = bool(enabled)
        if t == "box":
            src["enabled"] = enabled
            _config.upsert_source(src)
            note = ("「能碳一体机」数据源已启用（盒子实时数据恢复驱动仿真）" if enabled else
                    "「能碳一体机」数据源已停用（盒子实时数据不再驱动仿真；外部数据源不受影响）")
            return _changed(note)
        if t == "external":
            # 先改中间件（采集实际执行方），成功再落本地目录
            middleware_client.set_enabled(source_id, enabled)
            src["enabled"] = enabled
            _config.upsert_source(src)
            return _changed(f"外部数据源「{src.get('name')}」已{'启用' if enabled else '停用'}"
                            f"（中间件已{'开始' if enabled else '停止'}采集）")
        raise ValueError(f"不支持的数据源类型：{t}")


def save(source_id: str, name: str | None = None,
         config: Dict[str, Any] | None = None,
         enabled: bool | None = None) -> Dict[str, Any]:
    """保存数据源配置并热应用（external 同步到中间件；box 无手工配置）。"""
    with _lock:
        src = _require(source_id)
        t = src.get("type")
        if t == "box":
            # 清缓存后返回最新列表：前端写操作后统一拿到一致状态
            return _changed("「能碳一体机」数据源无需手工配置"
                            "（Broker 在「系统连接图 → 云端配置」中设置）")
        if t == "external":
            cfg = _external.normalize_external_config(
                config if config is not None else (src.get("config") or {}), source_id,
                sources=_config.external_configs())
            updated = dict(src)
            updated["config"] = cfg
            if name:
                updated["name"] = str(name).strip() or updated.get("name", "外部数据源")
            if enabled is not None:
                updated["enabled"] = bool(enabled)
            # 先同步中间件（参数非法在此抛出，本地不落盘）
            middleware_client.update_source(source_id, _external.middleware_payload(updated))
            _config.upsert_source(updated)
            return _changed(f"外部数据源「{updated.get('name')}」已保存并同步到中间件")
        raise ValueError(f"不支持的数据源类型：{t}")


def add_external(name: str | None = None,
                 config: Dict[str, Any] | None = None,
                 enabled: bool = False) -> Dict[str, Any]:
    """新增一条外部数据源：本地登记 + 注册到中间件（默认停用，保存后再启用）。"""
    with _lock:
        adapter = "mqtt"
        if isinstance(config, dict):
            adapter = str(config.get("adapter") or "mqtt").strip().lower()
        src = _config.default_external(name or "", adapter)
        cfg = _external.normalize_external_config(
            config if config is not None else (src.get("config") or {}), src["id"],
            sources=_config.external_configs())
        src["config"] = cfg
        src["enabled"] = bool(enabled)
        # 先注册到中间件（校验/连通在中间件侧完成），成功再落本地目录
        middleware_client.add_source(_external.middleware_payload(src))
        _config.upsert_source(src)
        return _changed(f"已注册外部数据源「{src.get('name')}」到数据中间件")


def remove(source_id: str) -> Dict[str, Any]:
    """删除数据源（内置源与外部源一视同仁，无例外）。

    - external：先注销中间件侧采集，再删本地目录；
    - box 等内置源：删本地目录并记录「用户已删除」——平台立即停止采纳其数据
      （含重启后不再自动补建），可用 restore_builtin 原样加回。
    """
    with _lock:
        src = _require(source_id)
        name = src.get("name")
        if src.get("type") == "external":
            box = str((src.get("config") or {}).get("box") or "")
            # 先注销中间件侧，再删本地目录（中间件不可达且确为 404 时仍允许清理本地）
            middleware_client.remove_source(source_id)
            _config.remove_source(source_id)
            if box:
                try:
                    from ..mqtt_source import _shared as ms
                    with ms._LOCK:
                        ms._EXT_STATS.pop(box, None)
                except Exception:  # noqa: BLE001
                    pass
            return _changed(f"已删除外部数据源「{name}」（中间件同步注销）")
        _config.remove_source(source_id)
        if _config.builtin_template(source_id):
            _config.mark_builtin_removed(source_id)
        return _changed(f"已删除数据源「{name}」（平台立即停止采纳其数据，可在本区块重新添加）")


def restore_builtin(source_id: str = "box") -> Dict[str, Any]:
    """恢复被删除的平台内置数据源（默认 box 能碳一体机）：清删除标记 + 重新登记。"""
    with _lock:
        tpl = _config.builtin_template(source_id)
        if tpl is None:
            raise ValueError(f"不是平台内置数据源：{source_id}")
        _config.restore_builtin(source_id)
        _config.upsert_source(tpl)
        return _changed(f"已重新添加内置数据源「{tpl.get('name')}」")


# ------------------------- 测试连接 / 类型清单 -------------------------

def test_config(config: Dict[str, Any], source_id: str = "") -> Dict[str, Any]:
    """测试外部源接入配置（转发中间件做真实连通性探测，不落盘）。"""
    if not isinstance(config, dict):
        raise ValueError("测试内容必须是 JSON 对象")
    sid = source_id or "probe"
    cfg = _external.normalize_external_config(config, sid,
                                              sources=_config.external_configs())
    payload = {
        "id": sid,
        "type": cfg["adapter"],
        "name": "连通性测试",
        "box": cfg["box"],
        "enabled": True,
        **(cfg.get("params") or {}),
    }
    return middleware_client.test_source(payload)


def adapter_types() -> List[Dict[str, Any]]:
    """可用接入类型（取中间件注册表；不可达时回退本地已知类型）。"""
    try:
        types = middleware_client.types()
        if types:
            return types
    except Exception:  # noqa: BLE001
        pass
    return [{"type": t, "label": _config.ADAPTER_LABELS.get(t, t),
             "desc": "订阅外部 MQTT Broker 的主题（中间件不可达，参数需手工填写）",
             "fields": []} for t in _config.ADAPTERS]
