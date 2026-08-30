"""mqtt_source 包：消息解析（纯函数 + 读数解析）。

- 设备识别：_identify_cloud_device / _main_property_of_topic；
- 主读数选择：_primary_value / _is_invalid_reading；
- 云端设备反查与兜底读数：_box_device_name_of_cloud_id / _crd_twin_reading；
- 对外读数解析：resolve_reading（「关联制」）；
- 云端设备快照：snapshot_cloud_devices。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from . import _shared
from ._shared import (BOX_DEVICES_FILE, CLOUD_DEVICES, READINGS, _BOX_KEYS,
                      _DEVICE_ID_KEYS, _INVALID_READING_VALUES, _LOCK,
                      _PRIMARY_KEYS)


def _is_invalid_reading(v: Any) -> bool:
    """判断是否为仪表无效读数标志码（如称重仪表传感器异常时输出 0xFFFE=-65534）。"""
    if isinstance(v, bool) or v is None:
        return False
    try:
        return float(v) in _INVALID_READING_VALUES
    except (TypeError, ValueError):
        return False


def _main_property_of_topic(topic: str) -> Optional[str]:
    """从 KubeEdge Device 上报主题 data/<box>/<device>/<instance>/<property> 解析属性名；
    段数 <=3（单设备数据主题）或无 data 前缀时返回 None（主读数按 payload 字段决定）。"""
    parts = [p for p in topic.split("/") if p]
    if parts and parts[0] == "data" and len(parts) >= 5:
        return parts[-1].lower()
    return None


def _identify_cloud_device(topic: str, data: Dict[str, Any]) -> "tuple[str, str]":
    """从一条消息中识别「云端设备」及其所属盒子。

    云端设备优先取 payload 的设备标识字段（device/deviceId/...），
    否则按主题推断（data/<box>/<device> 或 data/<device>），兜底用主题本身。
    """
    dev: Optional[str] = None
    for k in _DEVICE_ID_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            dev = v.strip()
            break
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            dev = str(v)
            break
    box: Optional[str] = None
    # 盒子归属优先从主题推断（data/<box>/<device>[/<instance>/<property>]，第 2 段即 boxId）。
    # 该推断独立于 device 识别：payload 带 device 字段但无 box 字段时（如属性级主题
    # {t, v} 消息），必须仍能从主题取到 box，否则设备会被误归为「未分组」而多渲染一张假盒子卡片。
    parts = [p for p in topic.split("/") if p]
    if parts and parts[0] == "data":
        rest = parts[1:]
        if len(rest) >= 2:
            box = rest[0]
            if dev is None:
                dev = rest[1]
        elif len(rest) == 1 and dev is None:
            dev = rest[0]
    if dev is None:
        dev = topic
    # payload 显式 box 字段优先（覆盖主题推断，兼容盒子多设备聚合上报）
    for k in _BOX_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            box = v.strip()
            break
    return dev, box or "未分组"


def _primary_value(fields: Dict[str, float]) -> Optional[float]:
    """从设备数值字段中挑一个主读数：优先 value/v/val/reading 等，否则唯一字段，否则首字段。"""
    if not fields:
        return None
    for k in _PRIMARY_KEYS:
        if k in fields:
            return fields[k]
    if len(fields) == 1:
        return next(iter(fields.values()))
    for k, v in fields.items():
        if k.lower() in ("ts", "time", "timestamp", "t", "seq", "no", "index"):
            continue
        return v
    return next(iter(fields.values()))


def _box_device_name_of_cloud_id(cloud_id: str) -> Optional[str]:
    """反查盒子设备配置：哪个设备的 cloudDevice/name 等于 cloud_id（用于 CRD twins 匹配）。"""
    cid = str(cloud_id or "").strip()
    if not cid:
        return None
    try:
        with open(BOX_DEVICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    for d in (data.get("devices") or []):
        if str(d.get("cloudDevice") or "").strip() == cid:
            return str(d.get("name") or "").strip() or None
        if str(d.get("name") or "").strip() == cid:
            return cid
    return None


def _crd_twin_reading(cloud_id: str) -> Optional[float]:
    """兜底读数：云端 Device CRD twins 缓存（agent 5s 经 cloud/crds 主题推送）。

    MQTT data/# 链路（CLOUD_DEVICES）断连/无数据时，绑定同步仍可从 CRD twins 缓存取到读数。
    匹配 cloud_id 与云端设备名（name）；cloud_id 也可能是盒子设备配置的 cloudDevice 标识
    （如 202603041423），此时先从 box_devices.json 反查设备名再匹配。
    主读数属性（weight/value/...）优先，否则取 twins 中第一个有效 reported。
    返回 None 表示该设备当前无可用读数。
    """
    try:
        crds = _shared.cloud_agent.crds()
    except Exception:
        return None
    if not (crds or {}).get("ok"):
        return None
    cid = str(cloud_id or "").strip()
    names = {cid}
    n = _box_device_name_of_cloud_id(cid)   # cloudDevice 标识 → 设备名（如 202603041423 → chengzhong）
    if n:
        names.add(n)
    for d in (crds.get("devices") or []):
        if str(d.get("name", "")).strip() not in names:
            continue
        twins = d.get("twins") or []
        for pname in _PRIMARY_KEYS:
            for t in twins:
                if str(t.get("propertyName", "")).lower() == pname:
                    v = t.get("reported")
                    if v is not None and not _is_invalid_reading(v):
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return None
        for t in twins:                       # 无主读数属性时取第一个有效 reported
            v = t.get("reported")
            if v is not None and not _is_invalid_reading(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
    return None


def resolve_reading(device_id: str) -> Optional[float]:
    """按仿真设备实例 id 取真实读数 —— 采用「关联制」。

    只有该设备实例已与某个云端设备（能碳一体机盒子下的设备）建立关联时，
    才返回云端上报的主读数；未关联的设备一律返回 None（不同步）。

    关联来源：
    1. 用户在「能碳一体机管理」视图手动建立（config/links.json，cloud_id -> local_device_id）；
    2. 前端「配置 Broker」弹窗中的静态映射 mapping（静态配置，字段名视为云端设备）。

    返回 None 时调用方（realtime.py）不得回退到模拟数据。

    读数换算：若该关联配置了换算系数 factor（如传感器原始单位 kg/min → 流程设备 t/h），
    返回值为 原始读数 × factor。

    读数来源优先级：① MQTT data/# 实时链路（CLOUD_DEVICES.primary）② READINGS 字段直读
    ③ 云端 CRD twins 缓存兜底（MQTT 链路断连时仍可同步真实读数）。
    """
    with _LOCK:
        cloud_id = _shared._LINKS_REV.get(device_id)
        if not cloud_id:
            return None
        v = None
        cd = CLOUD_DEVICES.get(cloud_id)
        if cd and cd.get("primary") is not None:
            v = cd["primary"]
        else:
            r = READINGS.get(cloud_id)          # 兼容静态映射字段名直读
            if r is not None:
                v = r["v"]
        if v is None:
            v = _crd_twin_reading(cloud_id)     # MQTT data/# 链路无数据时读 CRD twins 缓存
        if v is None:
            return None
        factor = _shared._LINKS_FACTOR.get(cloud_id, 1.0)
        try:
            return float(v) * factor
        except (TypeError, ValueError):
            return None
    return None


def snapshot_cloud_devices() -> Dict[str, Dict[str, Any]]:
    """云端设备缓存快照（CLOUD_DEVICES 深拷贝，供盒子总览等只读消费）。"""
    with _LOCK:
        return {cid: dict(info) for cid, info in CLOUD_DEVICES.items()}
