"""可绑定信号目录（流程编排用）：按数据源分组，列出各源当前上报的全部数值。

数据来源两条链路合并：
- MQTT data/#：mqtt_source.CLOUD_DEVICES（一体机 + 外部源，按 box 前缀归属）；
- 云端 CRD twins：cloud_agent.crds()（MQTT 未上报但 CRD 有新鲜值的设备也可见）。

前端 3s 轮询本目录，故整体带 1s 短缓存（多标签页并发时只算一次），
并在数据源增删改后由 reset_cache() 立即失效。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from . import config as _config

TYPE_LABELS = _config.TYPE_LABELS

# 非测量字段（时间戳/序号等消息自带字段）：不作为可绑定数值列出（与摄取侧主读数挑选口径一致）
_NON_METRIC_FIELDS = {"ts", "time", "timestamp", "t", "seq", "no", "index", "id"}

_CATALOG_TTL = 1.0
_lock = threading.RLock()
_catalog_ts = 0.0
_catalog: Dict[str, Any] = {"ok": True, "sources": []}


def reset_cache() -> None:
    """清空目录缓存（数据源增删改 / 测试复位时调用）。"""
    global _catalog_ts
    with _lock:
        _catalog_ts = 0.0


def _is_metric_field(field: str) -> bool:
    return str(field or "").split(".")[-1].strip().lower() not in _NON_METRIC_FIELDS


def signal_catalog(force: bool = False) -> Dict[str, Any]:
    """可绑定信号目录：按数据源分组，列出该源当前上报的每台设备及其**全部数值**。

    供「流程编排 → 附加传感 / 可变设备」把工艺下的设备绑定到数据源实测值：
    - 分组即数据源目录条目（box 能碳一体机 / external 外部源，按 box 前缀归属）；
    - 一台设备往往上报多个数值（如称重设备同时有 weight / temperature），
      此处逐条列出（values[]），每条给出稳定 key（box/device/field），
      前端凭 key 绑定，运行态按 key 取实时读数。
    """
    global _catalog_ts, _catalog
    now = time.time()
    with _lock:
        if not force and _catalog_ts and now - _catalog_ts < _CATALOG_TTL:
            return _catalog
        out = _build(now)
        _catalog, _catalog_ts = out, now
        return out


def _never_ts(_v: Any) -> None:
    """CRD 时间戳解析的退化实现：解析能力不可用时一律判为「不新鲜」（宁可缺，不可错）。"""
    return None


def _crd_freshness() -> "tuple[float, Any]":
    """CRD twin 新鲜度判定所需的窗口常量与时间戳解析函数。"""
    try:
        from ..box_console._shared import DATA_FRESH_SECONDS, parse_crd_ts
        return float(DATA_FRESH_SECONDS), parse_crd_ts
    except Exception:  # noqa: BLE001
        return 120.0, _never_ts


def _crd_field_map(now: float) -> Dict[str, Dict[str, float]]:
    """云端 CRD twins 的新鲜读数：{设备名: {属性: 值}}。

    主链路 Mapper→DMI→edgecore→CloudHub→Device CRD→agent 缓存；MQTT 未上报但 CRD
    有新鲜值的设备也应在目录里可见。
    """
    from .. import cloud_agent
    from ..mqtt_source.parsing import _twin_recent

    cr = cloud_agent.crds()
    if not (cr or {}).get("ok"):
        return {}
    window, parse_ts = _crd_freshness()
    out: Dict[str, Dict[str, float]] = {}
    for d in cr.get("devices") or []:
        cid = str(d.get("name") or "").strip()
        if not cid:
            continue
        fields: Dict[str, float] = {}
        for t in d.get("twins") or []:
            pn = str(t.get("propertyName") or "").strip()
            if not pn or not _twin_recent(t, now, window, parse_ts):
                continue
            try:
                fields[pn] = float(t.get("reported"))
            except (TypeError, ValueError):
                continue
        if fields:
            out[cid] = fields
    return out


def _merge_crd_readings(cloud: Dict[str, Any], now: float) -> None:
    """把 CRD 读数并入 MQTT 设备表：同一设备字段取并集，MQTT 已有的值优先（更新鲜）。"""
    try:
        for cid, fields in _crd_field_map(now).items():
            cur = cloud.get(cid)
            if cur is None:
                cloud[cid] = {"id": cid, "box": "", "topic": "", "last_seen": None,
                              "fields": fields, "primary": None}
                continue
            merged = dict(cur.get("fields") or {})
            for k, v in fields.items():
                merged.setdefault(k, v)
            cur["fields"] = merged
    except Exception:  # noqa: BLE001 —— CRD 链路不可达不应让整个信号目录失败
        pass


def _build(now: float) -> Dict[str, Any]:
    # 延迟导入：mqtt_source 侧对 data_sources 是函数内延迟引用，避免模块级循环
    from ..mqtt_source import _shared as ms
    from ..mqtt_source.parsing import _is_invalid_reading

    with ms._LOCK:
        cloud = {k: dict(v or {}) for k, v in ms.CLOUD_DEVICES.items()}

    # 云端 CRD twins 与 MQTT data/# 两链路合并
    _merge_crd_readings(cloud, now)

    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    def _group(sid: str, name: str, stype: str, enabled: bool) -> Dict[str, Any]:
        if sid not in groups:
            groups[sid] = {"id": sid, "name": name or sid, "type": stype,
                           "enabled": bool(enabled), "devices": []}
            order.append(sid)
        return groups[sid]

    # 先按目录条目建组（保证停用/暂无数据的源也出现，前端可提示）
    for s in _config.entries():
        _group(str(s.get("id") or ""), s.get("name") or TYPE_LABELS.get(s.get("type"), "数据源"),
               str(s.get("type") or ""), s.get("enabled") is not False)

    for cid, info in sorted(cloud.items(),
                            key=lambda kv: float(kv[1].get("last_seen") or 0), reverse=True):
        box = str(info.get("box") or "").strip()
        # 与摄取侧同一套归属规则：box 前缀 → 外部源（config 内已按前缀建索引，O(1)）
        entry = _config.external_by_box(box)
        if entry is not None:
            g = _group(str(entry.get("id") or box), entry.get("name") or str(entry.get("id") or box),
                       "external", entry.get("enabled") is not False)
        else:
            g = _group("box", TYPE_LABELS["box"], "box", True)
        values: List[Dict[str, Any]] = []
        for f, v in (info.get("fields") or {}).items():
            if isinstance(v, bool) or not _is_metric_field(str(f)):
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            values.append({
                "field": str(f),
                "value": round(fv, 4),
                "invalid": bool(_is_invalid_reading(fv)),
                "key": f"{box}/{cid}/{f}" if box else f"{cid}/{f}",
            })
        if not values:
            continue
        values.sort(key=lambda x: x["field"])
        g["devices"].append({
            "id": str(cid),
            "device": str(cid),
            "box": box,
            "last_seen": info.get("last_seen"),
            "values": values,
        })
    return {"ok": True, "sources": [groups[i] for i in order]}
