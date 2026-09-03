"""实时数据：Device.status.twins 实时上报值 + 趋势历史 + 云端 CRD/日志 + 消息流。

数据链路：边缘 Mapper → DMI → edgecore deviceTwin → CloudHub → 云端 Device CRD →
云端 agent 采集 → MQTT cloud/crds 推送 → cloud_agent 缓存；请求路径只读缓存（毫秒级）。
CloudCore 日志由 agent 每 3s 经 MQTT cloud/logs 推送。全程无 SSH、无平台侧轮询线程。

依赖方向：本模块依赖 devices.py（指纹/匹配）与 cloud_ops.py（k8s 名校验），被门面统一导出。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .. import cloud_agent
from .. import mqtt_source
from ._shared import (_TWIN_HISTORY, _TWIN_HISTORY_MAX, _load_devices,
                      DATA_FRESH_SECONDS, data_fresh, last_data_ts,
                      parse_crd_ts as _parse_crd_ts)
from .cloud_ops import _K8S_NAME_RE
from .devices import _device_fingerprint, _match_cloud_device


def _cloud_twins_map() -> Dict[str, Dict[str, Any]]:
    """返回云端 Device.status.twins 映射（device_name -> {twins, state, lastOnlineTime}）。

    数据链路：边缘 Mapper → DMI → edgecore deviceTwin → CloudHub → 云端 Device CRD →
    云端 agent 采集 → MQTT cloud/crds 推送 → cloud_agent 缓存。请求路径只读缓存。
    """
    now = time.time()
    mapping: Dict[str, Dict[str, Any]] = {}
    crds = cloud_agent.crds()
    if crds.get("ok"):
        for d in crds.get("devices", []):
            mapping[d.get("name", "")] = {
                "twins": d.get("twins", []),
                "state": d.get("state", ""),
                "lastOnlineTime": d.get("lastOnlineTime", ""),
                "updated": now,
            }
    return mapping


def cloud_logs() -> Dict[str, Any]:
    """云端 CloudCore 实时日志（agent 每 3s 经 MQTT cloud/logs 推送，环形缓冲最近 300 行）。"""
    return cloud_agent.logs()


def realtime_devices() -> Dict[str, Any]:
    """逐设备返回 Device.status.twins 实时上报值 + 趋势历史。

    双数据源（云端优先）：
    1) 云端 K3s CRD status.twins：边缘 Mapper 经 DMI→edgecore→CloudHub 实时同步（主链路，无需 MQTT 转发）；
    2) 云端 MQTT Broker data/#（mqtt_source.CLOUD_DEVICES）：box-mapper MQTT 实时发布（兜底）。
    """
    with mqtt_source._LOCK:  # noqa: SLF001
        cloud = {k: dict(v) for k, v in mqtt_source.CLOUD_DEVICES.items()}
    cloud_twins = _cloud_twins_map()
    data = _load_devices()
    raw_devs = data.get("devices", [])
    # 指纹预计算（每个设备只算一次，供 name 缺失时的配置指纹共享匹配）
    fp_cache = {d.get("name"): _device_fingerprint(d) for d in raw_devs}
    # 云端 twins 匹配：name → cloudDevice → 配置指纹共享（相同配置设备显示相同数据）
    ctw_map = {d.get("name"): cloud_twins.get(d.get("name"))
               or cloud_twins.get((d.get("cloudDevice") or "").strip()) for d in raw_devs}
    fp2ctw: Dict[str, Dict[str, Any]] = {}
    for d in raw_devs:
        c = ctw_map.get(d.get("name"))
        if c:
            fp2ctw.setdefault(fp_cache.get(d.get("name")), c)
    # MQTT 匹配：cloudDevice → name → 配置指纹共享
    cd_map = {d.get("name"): _match_cloud_device(d, cloud) for d in raw_devs}
    fp2cd: Dict[str, Dict[str, Any]] = {}
    for d in raw_devs:
        c = cd_map.get(d.get("name"))
        if c:
            fp2cd.setdefault(fp_cache.get(d.get("name")), c)
    now = time.time()
    out = []
    for d in raw_devs:
        name = d.get("name")
        fp = fp_cache.get(name)
        ctw = ctw_map.get(name) or fp2ctw.get(fp)
        cd = cd_map.get(name) or fp2cd.get(fp)
        fields = (cd.get("fields") or {}) if cd else {}
        twins = []
        for prop in d.get("properties", []):
            pname = prop.get("name")
            # ① 云端 K3s CRD twins（主链路，propertyName 大小写不敏感匹配；后台线程 5s 缓存）
            val = ts = None
            if ctw:
                for t in ctw.get("twins", []):
                    if str(t.get("propertyName", "")).lower() == pname.lower():
                        val = t.get("reported")
                        ts = _parse_crd_ts(t.get("timestamp", ""))
                        break
            # ② MQTT 链路（平台订阅实时推送，毫秒级）：时间戳比 CRD twins 新时优先，
            #    避免后台 5s 缓存带来的读数延迟；CRD 无值或时间戳更旧时由 MQTT 顶上
            mqtt_val = None
            if cd:
                mqtt_val = fields.get(pname)
                if mqtt_val is None:
                    mqtt_val = fields.get(pname.lower())
                if mqtt_val is None:
                    mqtt_val = fields.get(prop.get("mapping") or "")
            mqtt_ts = cd.get("last_seen") if cd else None
            if mqtt_val is not None and (ts is None or (mqtt_ts and mqtt_ts > ts)):
                val, ts = mqtt_val, mqtt_ts
            # 仪表无效标志码（0xFFFE 等）→ 标记 invalid，前端显示"无有效数据"
            invalid = val is not None and mqtt_source._is_invalid_reading(val)
            if invalid:
                val = None
            twins.append({
                "propertyName": pname,
                "reported": val,
                "observedDesired": None,
                "timestamp": ts if ts is not None else None,
                "unit": prop.get("unit", ""),
                "invalid": invalid,
            })
            # 趋势历史（t 统一为 epoch 秒）
            if val is not None:
                key = f"{name}::{pname}"
                hist = _TWIN_HISTORY.setdefault(key, [])
                # 云边协同：合并断连期间 MQTT 补传的历史点（带真实采集时间戳，回填缺口）
                if cd:
                    replay_fields = [pname]
                    if prop.get("mapping"):
                        replay_fields.append(prop["mapping"])
                    for rf in replay_fields:
                        for t, v in mqtt_source.take_replay(cd.get("id"), rf):
                            hist.append({"t": t, "v": v})
                # 时间戳兜底：读数无时间戳（CRD/MQTT 均未带）时用当前时间（毫秒精度），
                # 避免所有轮询点共用同一函数级 now 被同时间戳去重后只剩 1 个采样点
                ts_eff = ts if ts is not None else time.time()
                # 数据源时间戳未推进（重复/固定）时用当前时间推进，保证每个轮询周期都能累积新采样点
                if hist and ts_eff <= hist[-1]["t"]:
                    ts_eff = time.time()
                hist.append({"t": ts_eff, "v": val})
                hist.sort(key=lambda x: x["t"])
                # 同时间戳去重（补传点与实时点可能重复同一时刻；保留该时刻最新值）
                dedup = []
                prev_t = None
                for h in hist:
                    if prev_t is not None and h["t"] == prev_t:
                        dedup[-1] = h
                    else:
                        dedup.append(h)
                    prev_t = h["t"]
                if len(dedup) > _TWIN_HISTORY_MAX:
                    del dedup[: len(dedup) - _TWIN_HISTORY_MAX]
                _TWIN_HISTORY[key] = dedup
        last = last_data_ts((ctw or {}).get("twins", []), cd)
        out.append({
            "name": name, "model": d.get("model"), "node": d.get("node"),
            "box_ip": d.get("box_ip"),
            # 在线 = 有实时数据推送（最后数据时间在窗口内）；读不到数据即离线
            "state": "reporting" if (last and (now - last) <= DATA_FRESH_SECONDS) else "offline",
            # 最后在线时间 = 最后数据上报时间（CRD twins 或 MQTT，双通道最新），非注册时间
            "lastOnlineTime": last,
            "twins": twins,
            "history": {t["propertyName"]: _TWIN_HISTORY.get(f"{name}::{t['propertyName']}", [])
                        for t in twins},
        })
    # 防内存泄漏：清理已删除设备/属性的历史 key（保留当前设备仍在用的）
    active_keys = {f"{d.get('name')}::{p.get('name')}" for d in raw_devs for p in (d.get("properties") or [])}
    for k in [k for k in _TWIN_HISTORY if k not in active_keys]:
        _TWIN_HISTORY.pop(k, None)
    return {"devices": out, "time": now}


def cloud_crds(force: bool = False) -> Dict[str, Any]:
    """读取云端真实 DeviceModel / Device CRD（agent 采集推送缓存；force=True 时 HTTP 实时拉取）。

    对应云端管理台 GET /api/devices：返回模型列表（属性清单）+ 设备列表（twins 摘要）。
    云端不可达/未部署 CRD 时返回 ok=False + 具体错误（不返回仿真数据）。

    附加字段（供界面「在线/离线」判定，勿用原始 state——那是注册态）：
    - data_online：是否有实时数据推送（CRD twins 上报时间戳 / 平台 MQTT data/#，
      窗口 DATA_FRESH_SECONDS 内）；读不到数据即 False（离线）。
    - last_online：最后数据时间 = 最后在线时间（epoch 秒）。
    注意 crds() 非 force 返回共享缓存对象，此处一律拷贝后再附加字段，不污染缓存。
    """
    data = cloud_agent.crds(force=force)
    if not isinstance(data, dict):
        return data
    with mqtt_source._LOCK:  # noqa: SLF001
        cloud = {k: dict(v) for k, v in mqtt_source.CLOUD_DEVICES.items()}
    devs = []
    for d in data.get("devices", []):
        d2 = dict(d)
        cd = cloud.get((d2.get("name") or "").strip())
        fresh, last = data_fresh(d2.get("twins", []), cd)
        d2["data_online"] = fresh
        d2["last_online"] = last
        devs.append(d2)
    out = dict(data)
    out["devices"] = devs
    return out


def ingest_device_value(p: Dict[str, Any]) -> Dict[str, Any]:
    """边缘桥接脚本/手动上报单点实时值：调云端 agent 本地 get→merge→patch 回写 Device.status.twins。

    对应云端管理台 POST /api/devices/realtime/ingest（demo_simulator 的「回写 twins」能力）。
    agent 端先读取设备当前 twins 合并（避免覆盖其他属性），再全量 patch status.state=online + lastOnlineTime + twins。
    """
    name = str(p.get("device") or "").strip()
    ns = str(p.get("namespace") or "default").strip()
    prop = str(p.get("property") or "").strip()
    value = p.get("value")
    if not name or not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"device 不合法（k8s 对象名：小写字母/数字/中划线/点）：{name}"}
    if not ns or not _K8S_NAME_RE.fullmatch(ns):
        return {"ok": False, "error": f"namespace 不合法：{ns}"}
    if not prop:
        return {"ok": False, "error": "property 不能为空"}
    if value is None:
        return {"ok": False, "error": "value 不能为空"}
    return cloud_agent.ingest(name, ns, prop, value)


def broker_stats() -> Dict[str, Any]:
    """云端 Broker 实时统计（$SYS，真实）。"""
    return mqtt_source.broker_stats()


def recent_messages() -> List[Dict[str, Any]]:
    """实时消息流（真实，来自 MQTT 链路）。"""
    with mqtt_source._LOCK:  # noqa: SLF001
        return list(mqtt_source.MESSAGE_LOG[-100:])


def publish_test(p: Dict[str, Any]) -> Dict[str, Any]:
    """发测试消息（向云端 Broker 发布）。"""
    topic = str(p.get("topic", "")).strip()
    if not topic:
        return {"ok": False, "error": "topic 不能为空"}
    return mqtt_source.publish(topic, p.get("payload", ""))
