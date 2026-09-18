"""mqtt_source 包：消息摄取核心（订阅线程的消息入口与解析落库）。

- _record_message：一条 MQTT 消息的完整处理（cloud/#、state/#、$SYS/#、data/#）；
- _log_msg：原始消息日志；_record_replay / take_replay：断点续传历史；
- _gc_expired：缓存清理（被整体赋值的 _last_gc_ts 经 _shared.X 访问）。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import _shared
from ._shared import (BROKER_STATS, CLOUD_DEVICES, MESSAGE_LOG, MESSAGE_LOG_MAX,
                      READINGS, REPLAY_HISTORY, REPLAY_HISTORY_MAX, _LOCK,
                      _MAIN_PROPS, _PRIMARY_KEYS, _STATE, cloud_agent)
from .box_state import _record_box_state
from .parsing import (_identify_cloud_device, _is_invalid_reading,
                      _main_property_of_topic, _primary_value)


def _log_msg(topic: str, payload: Any) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "payload": payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)[:2000],
    }
    with _LOCK:
        MESSAGE_LOG.append(rec)
        if len(MESSAGE_LOG) > MESSAGE_LOG_MAX:
            del MESSAGE_LOG[: len(MESSAGE_LOG) - MESSAGE_LOG_MAX]
        _STATE["message_count"] += 1
        _STATE["last_message_at"] = time.time()


def _ext_entry(box: str) -> Any:
    """查外部源条目映射（box 前缀 → {id,name,box,enabled}）；未登记返回 None。"""
    try:
        from ..data_sources import config as _ds_config
        return _ds_config.external_by_box(box)
    except Exception:
        return None


def _classify_source(data: Dict[str, Any], box: str = "") -> "tuple[str, str, Any]":
    """消息归属：返回 (kind, ext_prefix, 外部源条目)，一次目录查询同时得到三者。

    原实现先判 kind、再按前缀回查一次目录，热路径上每条消息查两遍。判据：
    - 前缀命中 external 条目 → external + 该条目（启停由该源决定）；
    - payload src 以 external 开头但前缀**未登记** → external + 条目 None：不按任何源
      启停过滤（外部数据不该被 box 开关误杀，见 test_mw_message_not_treated_as_box）；
    - 其余（真实盒子，能碳一体机云端上报）→ box。

    注：模拟数据由独立服务（platform/cloud-deploy/sim-source/）生成并经中间件 mqtt
    适配器接入，与其它外部源一样按登记前缀归属 external 条目。
    """
    b = str(box or data.get("box") or "").strip().lower()
    entry = _ext_entry(b) if b else None
    if entry is not None:
        return "external", str(entry.get("box") or b), entry
    src = data.get("src")
    if isinstance(src, str) and src.startswith("external"):
        return "external", b, None
    return "box", "", None


def _box_source_active() -> bool:
    """真实盒子数据源（能碳一体机）是否启用；查询失败时默认启用（不误杀数据）。"""
    try:
        from ..data_sources import config as _ds_config
        return _ds_config.is_source_enabled("box")
    except Exception:
        return True


def _record_ext_message(prefix: str, topic: str, payload: Any) -> None:
    """外部源消息：按前缀累计统计（最近读数）。

    统计写 _shared._EXT_STATS（external.status_of 读取，供数据源卡片「最近读数」）。
    注：历史版本曾在此按 config.target 自动关联仿真设备，该行为**已取消**——设备与仿真
    工序的关联一律由用户在平台手动建立，自动关联会在改绑后反复抢占，语义不可控。
    """
    now = time.time()
    with _LOCK:
        st = _shared._EXT_STATS.setdefault(prefix, {})
        st["received"] = int(st.get("received") or 0) + 1
        st["last_at"] = now
        st["last_topic"] = topic
        st["last_msg"] = {
            "ts": now, "topic": topic,
            "payload": payload if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False)[:500],
        }


def _record_message(msg) -> None:
    """解析一条 MQTT 消息：更新 READINGS（数值字段）、$SYS 统计并记入消息日志。

    平台只有云端 Broker 一个订阅入口（中间件转投的外部数据同在该 Broker），
    因此不再需要按端点区分统计口径。
    """
    topic = getattr(msg, "topic", "")
    try:
        payload = msg.payload.decode("utf-8", "replace")
    except Exception:
        payload = repr(getattr(msg, "payload", b""))

    # ext/#：外部数据**上行空间**——外部数据源（仪表/PLC/数据中台）经网线接入能碳一体机，
    # 一体机把原始数据上行到本空间交给云端中间件转换；平台只消费中间件转换后的标准数据
    # （data/ext-*/…），此处直接跳过，避免同一条数据被摄取两次、避免建出无归属设备。
    if topic.startswith("ext/"):
        return

    # cloud/#：云端 agent 推送（概览/CRD/日志，MQTT 长连接数据通道，替代 SSH）。
    # 只更新 cloud_agent 缓存并广播给前端，不计入设备读数/消息流（避免刷屏）。
    if topic.startswith("cloud/"):
        try:
            data = json.loads(payload)
        except Exception:
            return
        if isinstance(data, dict):
            cloud_agent.handle_push(topic, data)
        return

    # state/#：盒子侧状态上报（运行服务列表/部署结果回报），供盒子卡片展示。
    # 不计入设备读数/消息流（避免污染云端设备识别）。
    if topic.startswith("state/"):
        try:
            data = json.loads(payload)
        except Exception:
            return
        if isinstance(data, dict):
            _record_box_state(topic, data)
        return

    _log_msg(topic, payload)

    # $SYS/broker/*：Broker 统计（实时仪表盘数据源，参照 dashboard.py）
    if topic.startswith("$SYS/broker/"):
        key = topic[len("$SYS/broker/"):]
        val: Any = payload.strip()
        try:
            val = int(val)
        except Exception:
            try:
                val = float(val)
            except Exception:
                pass
        with _LOCK:
            if key == "clients/connected":
                BROKER_STATS["clients_connected"] = val
            elif key == "clients/maximum":
                BROKER_STATS["clients_max"] = val
            elif key == "messages/received":
                BROKER_STATS["broker_recv"] = val
            elif key == "messages/sent":
                BROKER_STATS["broker_sent"] = val
            elif key in ("subscriptions/count", "messages/subscriptions/count"):
                # mosquitto: $SYS/broker/subscriptions/count；amqtt: $SYS/broker/messages/subscriptions/count
                BROKER_STATS["subscriptions"] = val
            elif key == "uptime":
                BROKER_STATS["uptime"] = val
            elif key == "version":
                BROKER_STATS["version"] = val
        return

    with _LOCK:
        BROKER_STATS["panel_recv"] += 1

    # 尝试解析 JSON 并展平数值字段（支持嵌套 dict / 形如 {"device":"xx","values":{...}} 的报文）
    try:
        data = json.loads(payload)
    except Exception:
        return
    if not isinstance(data, dict):
        return

    flat: Dict[str, Any] = {}

    def _walk(node: Dict[str, Any], prefix: str = "") -> None:
        for k, v in node.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                _walk(v, key)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                flat[key] = float(v)
    _walk(data)

    now = time.time()
    cloud_id, box = _identify_cloud_device(topic, data)
    # 忽略设备（重复链路/废弃设备）：仍记入消息日志，但不识别为云端设备、不同步读数
    if cloud_id and cloud_id in _shared._IGNORED_DEVICES:
        with _LOCK:
            CLOUD_DEVICES.pop(cloud_id, None)
            READINGS.pop(cloud_id, None)
        return
    # 统一数据源接入（box 能碳一体机 / external 外部源 均按目录启停过滤；
    # external 含中间件接入的外部数据（含独立模拟源），停用后该前缀消息不再驱动仿真）：
    kind, ext_prefix, entry = _classify_source(data, box)
    if kind == "box":
        gate = _box_source_active()
    else:
        # 已登记外部源：按该源启停；前缀未登记的外部形态数据：不过滤（见 _classify_source）
        gate = True if entry is None else bool(entry.get("enabled", True))
    if cloud_id and not gate:
        with _LOCK:
            CLOUD_DEVICES.pop(cloud_id, None)
            READINGS.pop(cloud_id, None)
        return
    # 外部源：按前缀累计最近读数统计（见 _record_ext_message；不做任何自动关联）
    if ext_prefix:
        _record_ext_message(ext_prefix, topic, payload)
    prop = _main_property_of_topic(topic)
    if prop:
        # 属性级主题（data/<box>/<device>/<instance>/<property>）：payload 仅 {t, v}，
        # 把值同时登记到 fields[属性名]，使 twins/设备详情能按属性名取到最新值
        v = flat.get("v")
        if v is not None:
            flat[prop] = v
    with _LOCK:
        for field, value in flat.items():
            READINGS[field] = {"t": now, "v": value}
        if cloud_id:
            cur = CLOUD_DEVICES.get(cloud_id)
            # 属性级主题：仅主读数属性更新 primary，附属寄存器消息保留原 primary
            if prop is None:
                primary = _primary_value(flat)
            elif prop in _MAIN_PROPS:
                primary = _primary_value(flat)
            else:
                primary = (cur or {}).get("primary")
            # 主读数为仪表无效标志码（0xFFFE 等）→ 视为无有效数据，不同步真实读数
            if primary is not None and _is_invalid_reading(primary):
                primary = None
            # fields 合并保留各属性最新值（不因单条属性消息而丢失其它字段）
            merged = dict((cur or {}).get("fields") or {})
            merged.update(flat)
            CLOUD_DEVICES[cloud_id] = {
                "id": cloud_id,
                "box": box,
                "topic": topic,
                "last_seen": now,
                "fields": merged,
                "primary": primary,
            }
            # 兼容静态 mapping 直读：把主读数同时登记到 READINGS[cloud_id]（无有效数据时清除残留）
            if primary is not None:
                READINGS[cloud_id] = {"t": now, "v": primary}
            else:
                READINGS.pop(cloud_id, None)
        # 周期清理：长期未上报的云端设备残留缓存（防内存泄漏）
        _gc_expired()
    # 云边协同：payload 带真实时间戳(ts)的消息 = 边缘断点续传历史，记录供折线图回填。
    # 注意：必须在 _LOCK 块外调用（_record_replay 内部自行加锁，嵌套会死锁）。
    _record_replay(cloud_id, prop, flat)


# ------------------------- 云边协同：断点续传历史 -------------------------

def _record_replay(cloud_id: str, prop: Optional[str], flat: Dict[str, float]) -> None:
    """记录边缘断点续传的历史点（消息 payload 带真实采集时间戳 ts）。

    仅当 payload 含 ts（epoch 秒，>1e12 视为毫秒）且存在主读数字段时记录，
    供平台折线图 history 回填云边断连期间的缺口。
    """
    ts = flat.get("ts") or flat.get("timestamp") or flat.get("t")
    if ts is None:
        return
    try:
        ts = float(ts)
        if ts > 1e12:  # 毫秒 → 秒
            ts /= 1000.0
    except (TypeError, ValueError):
        return
    field = prop or None
    if field is None:
        for k in _PRIMARY_KEYS:
            if k in flat and k != "ts":
                field = k
                break
    if not field:
        return
    v = flat.get(field)
    if v is None or _is_invalid_reading(v):
        return
    with _LOCK:
        lst = REPLAY_HISTORY.setdefault(cloud_id, {}).setdefault(field, [])
        lst.append((ts, float(v)))
        if len(lst) > REPLAY_HISTORY_MAX:
            del lst[: len(lst) - REPLAY_HISTORY_MAX]


def take_replay(cloud_id: str, field: str) -> List[tuple]:
    """取出并清空某云端设备某字段的补传历史点（供折线图 history 回填断连缺口）。"""
    with _LOCK:
        h = REPLAY_HISTORY.get(cloud_id or "")
        if not h:
            return []
        lst = h.pop(field, [])
        if not h:
            REPLAY_HISTORY.pop(cloud_id or "", None)
        return lst


def _gc_expired(now: Optional[float] = None) -> None:
    """周期清理长期未上报的云端设备缓存（防内存泄漏）。

    - CLOUD_DEVICES/READINGS[cloud_id]/REPLAY_HISTORY[cloud_id]：超过 GC_TTL 未上报的云端设备
    - 调用方需已持有 _LOCK（_record_message 内）。
    """
    now = time.time() if now is None else now
    if now - _shared._last_gc_ts < _shared._GC_MIN_INTERVAL:
        return
    _shared._last_gc_ts = now
    stale = [cid for cid, info in CLOUD_DEVICES.items()
             if now - float(info.get("last_seen") or 0) > _shared.GC_TTL]
    for cid in stale:
        CLOUD_DEVICES.pop(cid, None)
        READINGS.pop(cid, None)
        REPLAY_HISTORY.pop(cid, None)
        # fields 前缀字段（如 "weight" / "box.weight"）也一并清理，避免 READINGS 无限增长
        for k in [k for k in READINGS if k in cid or cid in k]:
            READINGS.pop(k, None)
