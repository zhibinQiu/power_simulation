"""data_sources 包：统一数据源接入目录配置（config/data_sources.json）。

统一概念（用户诉求：能碳一体机 / 外部数据源都是「一种数据源接入」）：
- box        能碳一体机（KubeEdge 云端盒子）：数据经云端 Broker → 平台订阅线程摄取。
             平台侧无独立运行线程；enabled 控制摄取侧是否采纳真实盒子消息。
- external   外部数据源：**注册到数据中间件**（platform/cloud-deploy/middleware/，
             HTTP 管理 API），由中间件采集并转换为标准 MQTT 直发云端 Broker，
             平台按 box 前缀识别归属。
             本目录只登记「平台侧需要的字段」：box 前缀（识别归属/启停过滤）、
             type/params（注册到中间件的适配器配置快照）。
             （历史 target「自动关联仿真设备」已取消，关联一律由用户手动建立）

本文件为唯一真源（box/external 全部条目的 name/enabled/config）；中间件侧以
middleware.json 指向的服务为准，平台启动时 sync_with_middleware 做一次对账补齐。

性能约定（摄取线程每消息查询 + 前端轮询高频读取）：
- 目录只驻留一份内存快照（load_config），派生视图（enabled 映射 / box 前缀映射 /
  外部源列表）由 **一次遍历同时产出** 并带短 TTL 缓存，避免逐消息深拷贝整个目录；
- 写目录（upsert/remove）即时清空派生缓存，保证前端看到的状态立即一致。
"""
from __future__ import annotations

import copy
import os
import threading
import time
import uuid
from typing import Any, Dict, List

from ..core.storage import read_json_file, write_json_atomic

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "data_sources.json")

TYPE_LABELS = {
    "box": "能碳一体机",
    "external": "外部数据源",
}

# 外部数据源适配器类型（与中间件 adapters 注册表的 type 对应；目前仅 mqtt）。
# 模拟数据不是适配器类型：由独立服务生成后经 mqtt 接入。
# 全仓唯一定义点——external.py 从此导入，避免同一事实散落多处。
ADAPTERS = ("mqtt",)
# 适配器类型展示名（与 ADAPTERS 一一对应）
ADAPTER_LABELS = {"mqtt": "外部 MQTT"}

# 目录条目中「由代码派生」的字段（type/name 决定 label/desc/builtin），不落盘：
# 存储它们只会与派生值互相漂移（改了 TYPE_DESC 而文件里还是旧文案）。
_DERIVED_KEYS = ("label", "desc", "builtin")

_lock = threading.RLock()  # 可重入：派生视图构建时仍持有目录锁
_current: Dict[str, Any] | None = None

# 派生视图缓存：{enabled: {id: bool}, ext_by_box: {prefix: {...}}, ext_list: [源条目]}
_VIEW_TTL = 2.0
_view_ts = 0.0
_views: Dict[str, Any] = {"enabled": {}, "ext_by_box": {}, "ext_list": [],
                          "ext_boxes": frozenset()}

# 平台内置数据源模板：与手工注册的源完全同权（可启停、可删除、删除后可原样加回），
# 不做「某些源不可删」的例外——删除后记录在 removed_builtins，重启不再自动补建。
_BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "box": {"id": "box", "type": "box", "name": "能碳一体机", "enabled": True},
}


def _defaults() -> Dict[str, Any]:
    return {
        "sources": [copy.deepcopy(_BUILTIN_TEMPLATES["box"])],
        "removed_builtins": [],
    }


def load_config(force: bool = False) -> Dict[str, Any]:
    """读取 data_sources.json（不存在时写默认，含 box 内置目录项）。"""
    global _current
    with _lock:
        if _current is not None and not force:
            return _current
        cfg = _defaults()
        saved = read_json_file(CONFIG_PATH, {})
        if isinstance(saved, dict) and isinstance(saved.get("sources"), list):
            cfg["sources"] = [s for s in saved["sources"] if isinstance(s, dict)]
            removed = saved.get("removed_builtins")
            if isinstance(removed, list):
                cfg["removed_builtins"] = [str(x) for x in removed if isinstance(x, str)]
        elif not os.path.exists(CONFIG_PATH):
            try:  # 首次运行：落盘默认目录，便于运维直接编辑
                write_json_atomic(CONFIG_PATH, cfg)
            except OSError:
                pass
        _current = cfg
        return cfg


def builtin_template(source_id: str) -> Dict[str, Any] | None:
    """平台内置数据源模板（深拷贝，写路径可改）；非内置返回 None。"""
    tpl = _BUILTIN_TEMPLATES.get(str(source_id or ""))
    return copy.deepcopy(tpl) if tpl else None


def builtin_removed_ids() -> List[str]:
    """已被用户删除的内置源 id（start() 不再自动补建）。"""
    return list(load_config().get("removed_builtins") or [])


def mark_builtin_removed(source_id: str) -> None:
    """记录「内置源已被删除」：重启不补建，且摄取侧按停用处理。"""
    with _lock:
        cfg = load_config(force=True)
        removed = cfg.setdefault("removed_builtins", [])
        if source_id not in removed:
            removed.append(source_id)
            _persist(cfg)


def restore_builtin(source_id: str) -> bool:
    """清除「内置源已删除」标记（配合 upsert_source 原样加回）。"""
    with _lock:
        cfg = load_config(force=True)
        removed = cfg.setdefault("removed_builtins", [])
        if source_id not in removed:
            return False
        removed.remove(source_id)
        _persist(cfg)
        return True


def reset_cache() -> None:
    """清空派生视图缓存（写目录后 / 测试复位时调用）。"""
    global _view_ts
    with _lock:
        _view_ts = 0.0
        _views.update({"enabled": {}, "ext_by_box": {}, "ext_list": [],
                       "ext_boxes": frozenset()})


def _persist(cfg: Dict[str, Any]) -> None:
    global _current
    with _lock:
        _current = cfg
    reset_cache()
    try:
        write_json_atomic(CONFIG_PATH, cfg)
    except OSError as e:
        raise ValueError(f"数据源目录写入失败：{e}") from e


def entries(force: bool = False) -> List[Dict[str, Any]]:
    """内部只读目录（**不得修改**，供状态/信号组装等高频路径零拷贝读取）。"""
    return load_config(force).get("sources") or []


def public_sources(force: bool = False) -> List[Dict[str, Any]]:
    """深拷贝源目录列表（写操作会改条目，前端回显用）。"""
    return copy.deepcopy(entries(force))


def entry(source_id: str, force: bool = False) -> Dict[str, Any] | None:
    """内部只读查找单条源（**不得修改**，供状态组装等高频路径零拷贝读取）。"""
    for s in entries(force):
        if s.get("id") == source_id:
            return s
    return None


def find_source(source_id: str, force: bool = False) -> Dict[str, Any] | None:
    """对外查找（深拷贝副本，写路径会修改条目）。"""
    for s in public_sources(force):
        if s.get("id") == source_id:
            return s
    return None


def _clean_entry(source: Dict[str, Any]) -> Dict[str, Any]:
    """去掉派生存储字段（label/desc/builtin 由 type 推导，落盘只会导致文案漂移）。"""
    for k in _DERIVED_KEYS:
        source.pop(k, None)
    return source


def upsert_source(source: Dict[str, Any]) -> None:
    """新增或覆盖目录中的一条源（id 相同即覆盖）。"""
    cfg = load_config(force=True)
    sources = cfg.setdefault("sources", [])
    _clean_entry(source)
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


# ------------------------- 派生视图（一次遍历产出，短 TTL 缓存） -------------------------

def _view_state(max_age: float = _VIEW_TTL) -> Dict[str, Any]:
    """enabled 映射 / box 前缀→外部源 / 外部源列表（只读，勿修改返回对象）。"""
    global _view_ts, _views
    now = time.time()
    with _lock:
        if _view_ts and now - _view_ts < max_age:
            return _views
        enabled: Dict[str, bool] = {}
        ext_by_box: Dict[str, Dict[str, Any]] = {}
        ext_list: List[Dict[str, Any]] = []
        ext_boxes: frozenset = frozenset()
        boxes: List[str] = []
        for s in entries():
            sid = str(s.get("id") or "")
            if not sid:
                continue
            on = s.get("enabled") is not False
            enabled[sid] = on
            if s.get("type") == "external":
                ext_list.append(s)
                box = str((s.get("config") or {}).get("box") or "").strip().lower()
                if box:
                    # 条目自带 box：摄取侧据此归类并统计，无需再回查目录
                    ext_by_box[box] = {"id": sid, "name": s.get("name"),
                                       "box": box, "enabled": on}
                    boxes.append(box)
        # 已被删除的内置源：摄取侧按「停用」处理（is_source_enabled 缺省为 True，
        # 不显式置 False 会导致删除后仍在采纳其数据）
        for sid in (load_config().get("removed_builtins") or []):
            enabled.setdefault(str(sid), False)
        ext_boxes = frozenset(boxes)
        _views = {"enabled": enabled, "ext_by_box": ext_by_box,
                  "ext_list": ext_list, "ext_boxes": ext_boxes}
        _view_ts = now
        return _views


def is_source_enabled(source_id: str, max_age: float = 1.0) -> bool:
    """按目录 id 查数据源是否启用（带秒级缓存，供摄取线程高频查询）。

    外部源不经过此函数——摄取侧按 box 前缀一次查到条目（含 enabled），
    见 external_by_box。未登记默认启用（不误杀数据）。
    """
    return bool(_view_state(max_age)["enabled"].get(source_id, True))


def external_boxes(max_age: float = _VIEW_TTL) -> frozenset:
    """已登记外部源的 box 前缀集合（派生视图，零重建）。

    供盒卡状态把外部源设备从「云端设备数」里剔除，替代原先每次调用重新遍历
    目录拼集合的写法。
    """
    return _view_state(max_age)["ext_boxes"]


def external_configs() -> List[Dict[str, Any]]:
    """所有外部源条目（含 config；只读，勿修改）。"""
    return list(_view_state()["ext_list"])


def external_by_box(box: str, max_age: float = 1.0) -> Dict[str, Any] | None:
    """按 box 前缀查外部源条目映射（id/name/enabled）；未登记返回 None。

    供摄取线程高频调用：消息 box 前缀命中即归属 external 源，可按 enabled 过滤。
    未登记的前缀返回 None（消息按真实盒子/其它语义处理，不误杀数据）。
    """
    return _view_state(max_age)["ext_by_box"].get(str(box or "").strip().lower())


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
    """目录条目 → 对外视图（去内部字段；浅拷贝，调用方只读）。"""
    t = source.get("type")
    view = {
        "id": source.get("id"),
        "type": t,
        "name": source.get("name") or TYPE_LABELS.get(t, "数据源"),
        "builtin": t in ("box",),
        "enabled": bool(source.get("enabled") is not False),
        "config": {},
    }
    if t == "external":
        cfg = dict(source.get("config") or {})
        params = cfg.get("params")
        cfg["params"] = dict(params) if isinstance(params, dict) else {}
        cfg.setdefault("adapter", "mqtt")
        cfg["adapter_label"] = ADAPTER_LABELS.get(cfg.get("adapter"), cfg.get("adapter"))
        view["config"] = cfg
    return view
