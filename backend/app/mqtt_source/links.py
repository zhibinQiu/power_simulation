"""mqtt_source 包：云端设备 <-> 仿真设备实例关联表（持久化到 config/links.json）。

被整体重新赋值的 _LINKS/_LINKS_REV/_LINKS_FACTOR 一律经 _shared.X 属性读写。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from . import _shared
from ._shared import CLOUD_DEVICES, LINKS_FILE, _LOCK


def _load_links() -> None:
    links: Dict[str, str] = {}
    factors: Dict[str, float] = {}
    for field, dev in _shared._MAPPING.items():    # 前端配置的静态映射作为 seed
        if field and dev:
            links[field] = dev
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f) or {}
        for c, l in (saved.get("links") or {}).items():   # 运行时关联覆盖/补充
            if c and l:
                links[c] = l
        for c, f_ in (saved.get("factors") or {}).items():  # 读数换算系数
            try:
                factors[c] = float(f_)
            except (TypeError, ValueError):
                factors[c] = 1.0
    except Exception:
        pass
    _shared._LINKS = links
    _shared._LINKS_REV = {l: c for c, l in links.items()}
    _shared._LINKS_FACTOR = factors


def _save_links() -> None:
    try:
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump({"links": _shared._LINKS, "factors": _shared._LINKS_FACTOR},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_link(cloud_id: str, local_id: str, factor: float = 1.0) -> None:
    """建立/更新关联：云端设备 <-> 仿真设备实例（一对一，同一本地设备只能关联一个云端设备）。

    factor: 读数换算系数，云端上报原始读数 × factor = 同步到仿真设备的读数
            （如传感器原始单位为 kg/min，流程设备为 t/h，则 factor=0.06）。"""
    cloud_id = (cloud_id or "").strip()
    local_id = (local_id or "").strip()
    if not cloud_id or not local_id:
        raise ValueError("cloud_id 与 local_id 不能为空")
    try:
        factor = float(factor)
    except (TypeError, ValueError):
        factor = 1.0
    with _LOCK:
        for c, l in list(_shared._LINKS.items()):    # 同一本地设备解除旧关联
            if l == local_id and c != cloud_id:
                del _shared._LINKS[c]
                _shared._LINKS_FACTOR.pop(c, None)
        _shared._LINKS[cloud_id] = local_id
        _shared._LINKS_FACTOR[cloud_id] = factor
        _shared._LINKS_REV = {l: c for c, l in _shared._LINKS.items()}
        _save_links()


def remove_link(cloud_id: str) -> None:
    """解除关联：云端设备不再同步任何本地设备。"""
    cloud_id = (cloud_id or "").strip()
    with _LOCK:
        _shared._LINKS.pop(cloud_id, None)
        _shared._LINKS_FACTOR.pop(cloud_id, None)
        _shared._LINKS_REV = {l: c for c, l in _shared._LINKS.items()}
        _save_links()


def get_links() -> Dict[str, Any]:
    """关联列表 + 云端识别设备（供前端连接面板渲染关联 UI）。"""
    with _LOCK:
        links = [{"cloud_id": c, "local_id": l, "factor": _shared._LINKS_FACTOR.get(c, 1.0)}
                 for c, l in _shared._LINKS.items()]
        cloud_devices = [
            {
                "id": c,
                "box": d.get("box"),
                "topic": d.get("topic"),
                "last_seen": d.get("last_seen"),
                "primary": d.get("primary"),
                "fields": list(d.get("fields") or {}),
            }
            for c, d in CLOUD_DEVICES.items()
        ]
    return {"links": links, "cloud_devices": cloud_devices}


# 模块导入时以 mapping 为 seed 初始化一次（与原 mqtt_source.py 模块级调用时机一致）
_load_links()
