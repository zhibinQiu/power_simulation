"""data_sources 包：统一数据源接入目录配置（config/data_sources.json）。

统一概念（用户诉求：能碳一体机 / 外部数据源 / 模拟数据 都是「一种数据源接入」）：
- box        能碳一体机（KubeEdge 云端盒子）：数据经云端 Broker → 平台订阅线程摄取。
             平台侧无独立运行线程；enabled 控制摄取侧是否采纳真实盒子消息。
- external   外部数据源：**注册到数据中间件**（platform/cloud-deploy/middleware/，
             HTTP 管理 API），由中间件采集并转换为标准 MQTT 发布到云端 Broker
             （external 形态），平台按 box 前缀识别归属。
             模拟数据（独立服务 sim-source 生成）也是一种外部源，与其它源完全同构。
             本目录只登记「平台侧需要的字段」：box 前缀（识别归属/启停过滤）、
             type/params（注册到中间件的适配器配置快照）。
             （历史 target「自动关联仿真设备」已取消，关联一律由用户手动建立）

本文件为唯一真源（box/external 全部条目的 name/enabled/config）；中间件侧以
middleware.json 指向的服务为准，平台启动时 sync_with_middleware 做一次对账补齐。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "data_sources.json")

RESERVED = ("sim", "box", "platform", "local")
TYPE_LABELS = {
    "box": "能碳一体机",
    "external": "外部数据源",
}

# 外部数据源的适配器类型（与中间件 adapters 注册表的 type 对应）
ADAPTER_LABELS = {
    "mqtt": "外部 MQTT",
    "sim": "模拟数据",
}

_lock = threading.RLock()  # 可重入：is_source_enabled/external_by_box 持锁内还会调 load_config
_current: Dict[str, Any] | None = None

# enabled 查询的秒级缓存：ingest 每消息调 is_source_enabled，避免逐消息读文件/跨模块
_cache_ts = 0.0
_cache_enabled: Dict[str, bool] = {}


def _defaults() -> Dict[str, Any]:
    return {
        "version": 1,
        "sources": [
            {"id": "box", "type": "box", "name": "能碳一体机", "enabled": True},
        ],
    }


def load_config(force: bool = False) -> Dict[str, Any]:
    """读取 data_sources.json（不存在时写默认，含 box 内置目录项）。"""
    global _current
    with _lock:
        if _current is not None and not force:
            return _current
        cfg = _defaults()
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f) or {}
            if isinstance(saved, dict) and isinstance(saved.get("sources"), list):
                # 清洗遗留条目：内置模拟源（type=sim）已迁移为中间件数据源，
                # 目录里不再保留该内置项（下次持久化时自动落盘）。
                cfg["sources"] = [s for s in saved["sources"]
                                  if not (str(s.get("id")) == "sim"
                                          and str(s.get("type")) == "sim")]
        except FileNotFoundError:
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
        except Exception:
            cfg = _defaults()
        _current = cfg
        return cfg


def _persist(cfg: Dict[str, Any]) -> None:
    global _current, _cache_ts
    with _lock:
        _current = cfg
        _cache_ts = 0.0  # 使 enabled 缓存失效
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError as e:
        raise ValueError(f"数据源目录写入失败：{e}") from e


def public_sources(force: bool = False) -> List[Dict[str, Any]]:
    """深拷贝源目录列表（前端回显用）。"""
    cfg = load_config(force)
    return json.loads(json.dumps(cfg.get("sources") or []))


def find_source(source_id: str, force: bool = False) -> Dict[str, Any] | None:
    for s in public_sources(force):
        if s.get("id") == source_id:
            return s
    return None


def upsert_source(source: Dict[str, Any]) -> None:
    """新增或覆盖目录中的一条源（id 相同即覆盖）。"""
    cfg = load_config(force=True)
    sources = cfg.setdefault("sources", [])
    for i, s in enumerate(sources):
        if s.get("id") == source.get("id"):
            sources[i] = source
            _persist(cfg)
            return
    sources.append(source)
    _persist(cfg)


def remove_source(source_id: str) -> bool:
    cfg = load_config(force=True)
    sources = cfg.setdefault("sources", [])
    kept = [s for s in sources if s.get("id") != source_id]
    if len(kept) == len(sources):
        return False
    cfg["sources"] = kept
    _persist(cfg)
    return True


def _enabled_map(force: bool = False) -> Dict[str, bool]:
    """目录 enabled 映射。"""
    return {s.get("id"): bool(s.get("enabled") is not False)
            for s in public_sources(force)}


def is_source_enabled(kind_or_id: str, max_age: float = 1.0) -> bool:
    """某类/某 id 的数据源是否启用（带秒级缓存，供摄取线程高频查询）。

    kind 取值：'box'（真实盒子消息）、'external:<id>'（某外部源转投消息）。
    """
    global _cache_ts, _cache_enabled
    now = time.time()
    with _lock:
        if now - _cache_ts > max_age:
            try:
                _cache_enabled = _enabled_map()
            except Exception:
                _cache_enabled = {}
            _cache_ts = now
        return bool(_cache_enabled.get(kind_or_id, True))  # 未登记默认启用（不误杀）


def external_configs() -> List[Dict[str, Any]]:
    """所有外部源条目（含 config）。"""
    return [s for s in public_sources() if s.get("type") == "external"]


# 外部源前缀→条目 映射缓存（摄取线程每消息调用，秒级失效即可）
_ext_map_ts = 0.0
_ext_map: Dict[str, Dict[str, Any]] = {}


def _build_ext_map() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for s in external_configs():
        box = str((s.get("config") or {}).get("box") or "").strip().lower()
        if box:
            out[box] = {
                "id": s.get("id"),
                "name": s.get("name"),
                "enabled": bool(s.get("enabled") is not False),
            }
    return out


def external_by_box(box: str, max_age: float = 1.0) -> Dict[str, Any] | None:
    """按 box 前缀查外部源条目映射（id/enabled）；未登记返回 None。

    供摄取线程高频调用：消息 box 前缀命中即归属 external 源，可按 enabled 过滤。
    未登记的前缀返回 None（消息按真实盒子/其它语义处理，不误杀数据）。
    """
    global _ext_map_ts, _ext_map
    now = time.time()
    with _lock:
        if now - _ext_map_ts > max_age:
            try:
                _ext_map = _build_ext_map()
            except Exception:
                _ext_map = {}
            _ext_map_ts = now
        return _ext_map.get(str(box or "").strip().lower())


def new_external_id() -> str:
    return "ext_" + uuid.uuid4().hex[:6]


def default_external(name: str = "", adapter_type: str = "mqtt") -> Dict[str, Any]:
    """新建外部源登记结构（id/唯一 box 前缀/适配器类型）。

    实际采集执行在中间件：注册时把 type/params 一并提交，中间件据此创建适配器。
    """
    source_id = new_external_id()
    return {
        "id": source_id,
        "type": "external",
        "name": name or "外部数据源",
        "enabled": False,
        "config": {
            "box": source_id.replace("ext_", "ext-"),
            "adapter": adapter_type or "mqtt",
            "params": {},
            "desc": "",
        },
    }


def source_public_view(source: Dict[str, Any]) -> Dict[str, Any]:
    """目录条目 → 对外视图（去内部字段）。"""
    view = {
        "id": source.get("id"),
        "type": source.get("type"),
        "name": source.get("name") or TYPE_LABELS.get(source.get("type"), "数据源"),
        "builtin": source.get("type") in ("box",),
        "enabled": bool(source.get("enabled") is not False),
    }
    t = source.get("type")
    if t == "external":
        cfg = json.loads(json.dumps(source.get("config") or {}))
        # 兼容旧结构：adapter 字段早期叫 type
        if not cfg.get("adapter") and cfg.get("type"):
            cfg["adapter"] = cfg.pop("type")
        cfg.setdefault("adapter", "mqtt")
        cfg.setdefault("params", {})
        cfg["adapter_label"] = ADAPTER_LABELS.get(cfg.get("adapter"), cfg.get("adapter"))
        view["config"] = cfg
    else:  # box
        view["config"] = {}
    return view
