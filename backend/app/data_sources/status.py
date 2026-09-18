"""数据源运行状态：类型策略表 + 状态组装。

源类型 → 状态生成器用一张小策略表（_BUILDERS）描述：新增一种数据源类型只需
注册一行，无需在列表/状态组装里散落 if-else（原实现即为此模式）。

盒卡口径注意：外部源（登记前缀 ext-*）的设备不混入「云端设备数」，最近消息也
只反映一体机数据。
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import config as _config
from . import external as _external

TYPE_LABELS = _config.TYPE_LABELS
TYPE_DESC = {
    "box": "能碳一体机云端（默认接入）：KubeEdge 盒子/传感器经云端 Broker 主动上报，平台订阅摄取后经关联驱动仿真",
    "external": "外部数据源注册到数据中间件，由中间件采集并转换为标准 MQTT 发布到云端 Broker，平台按 box 前缀识别归属（模拟数据由独立服务生成后经中间件接入）",
}


def box_status() -> Dict[str, Any]:
    """能碳一体机（box）数据源运行状态：Broker/主题/设备数/读数/链路/最近消息。"""
    from ..mqtt_source import _shared as ms
    with ms._LOCK:
        st = dict(ms._STATE)
        # 外部源前缀集合取自目录派生视图（秒级缓存），不再每次调用重建
        ext_boxes = _config.external_boxes()
        # 盒卡只统计一体机盒子设备：外部源（登记前缀 ext-*）设备不混入「云端设备数」
        st["cloud_devices"] = sum(1 for d in ms.CLOUD_DEVICES.values()
                                  if str(d.get("box") or "").strip().lower() not in ext_boxes)
        st["readings"] = len(ms.READINGS)
        st["links"] = len(dict(ms._LINKS))
        st["broker_host"] = ms._BROKER.get("host")
        st["broker_port"] = ms._BROKER.get("port")
        st["topics"] = list(ms._TOPICS)
        # 最近消息只反映一体机（box）数据：外部源消息不计入盒卡
        last = None
        for m in reversed(ms.MESSAGE_LOG):
            parts = str(m.get("topic") or "").split("/")
            if len(parts) > 1 and parts[1].strip().lower() in ext_boxes:
                continue
            last = m
            break
    st.pop("recent_messages", None)
    st["last_msg"] = last
    return st


def _external_status(source: Dict[str, Any], mw_map: Dict[str, Any]) -> Dict[str, Any]:
    st = _external.status_of(str(source.get("id") or ""), mw_map=mw_map)
    st["enabled"] = bool(source.get("enabled") is not False)
    return st


# 源类型 → 状态生成器
_BUILDERS: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = {
    "box": lambda _source, _mw_map: box_status(),
    "external": _external_status,
}


def source_status(source: Dict[str, Any], mw_map: Dict[str, Any]) -> Dict[str, Any]:
    """按源类型生成运行状态（未注册类型返回空状态）。"""
    fn = _BUILDERS.get(str(source.get("type") or ""))
    return fn(source, mw_map) if fn else {}
