"""设备 CRUD：DeviceModel/Device 增删改查 + YAML 生成 + 云端删除联动。

生成（工厂模式，实现位于 domain/box/device_yaml.py）：modbus / opcua / bluetooth
三协议 YAML 渲染器注册于 DeviceYamlFactory，新增协议无需改动本层。
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .. import cloud_agent
from .. import mqtt_source
from ..domain.box import DeviceYamlFactory
from ._shared import _load_devices, _save_devices, data_fresh, last_data_ts
from .cloud_ops import _auto_sync_cloud, _cloud_delete_crds, apply_devices_to_cloud


def generate_device_yaml(p: Dict[str, Any]) -> Dict[str, str]:
    """生成 DeviceModel + Device 两份 YAML（v1beta1 结构，参照 kubeedge-console-ops.md §5.2）。

    支持协议: modbus / opcua / bluetooth（渲染器注册于 DeviceYamlFactory，新增协议无需改动本层）。
    """
    return DeviceYamlFactory.get(p.get("protocol", "modbus")).render(p)


def _match_cloud_device(d: Dict[str, Any], cloud: Dict[str, Dict[str, Any]]) -> "Optional[Dict[str, Any]]":
    """匹配设备对应的云端设备：优先「绑定云端设备」(cloudDevice)，其次按设备名匹配。"""
    bound = (d.get("cloudDevice") or "").strip()
    if bound:
        cd = cloud.get(bound)
        if cd:
            return cd
    return cloud.get(d.get("name"))


def _device_fingerprint(d: Dict[str, Any]) -> str:
    """设备配置指纹：模型 + 协议 + 采集周期 + 节点 + 通信参数 + 有序点位。

    相同指纹的设备视为「相同配置」→ 共享同一云端数据源（显示相同数据）。
    点位取 name/address/type 参与指纹，保证改点位后不误共享。
    """
    props = [{
        "n": (pr.get("name") or "").lower(),
        "a": str(pr.get("address") or ""),
        "t": pr.get("dataType") or pr.get("type") or "",
    } for pr in d.get("properties", [])]
    parts = [
        d.get("model"), d.get("protocol"), d.get("collectCycle"), d.get("node"),
        json.dumps(d.get("comm") or {}, sort_keys=True),
        json.dumps(d.get("opcua") or {}, sort_keys=True),
        json.dumps(d.get("bluetooth") or {}, sort_keys=True),
        json.dumps(d.get("lora") or {}, sort_keys=True),
        json.dumps(d.get("cellular") or {}, sort_keys=True),
        json.dumps(props),
    ]
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def list_devices() -> Dict[str, Any]:
    data = _load_devices()
    # 附加实时状态：优先按绑定云端设备(cloudDevice)匹配，其次按设备名（真实读数，未匹配显示未上报）
    with mqtt_source._LOCK:  # noqa: SLF001
        cloud = {k: dict(v) for k, v in mqtt_source.CLOUD_DEVICES.items()}
    raw = data.get("devices", [])
    # 第一轮：cloudDevice → 设备名匹配
    matched = {d.get("name"): _match_cloud_device(d, cloud) for d in raw}
    # 第二轮：配置指纹共享——相同配置的设备即使未直接匹配到云端设备，
    # 也共享同配置设备的云端数据源（两个设备配置完全相同 => 显示相同数据）
    fp2cd: Dict[str, Dict[str, Any]] = {}
    for d in raw:
        cd = matched.get(d.get("name"))
        if cd:
            fp2cd.setdefault(_device_fingerprint(d), cd)
    # 云端 CRD twins（双通道之一）：name/cloudDevice → twins 列表（读平台缓存，零网络）
    twins_map: Dict[str, List[Dict[str, Any]]] = {}
    try:
        crds = cloud_agent.crds()
        if crds.get("ok"):
            for d in crds.get("devices", []):
                twins_map[d.get("name")] = d.get("twins", [])
    except Exception:  # noqa: BLE001
        twins_map = {}

    def _twins_of(d: Dict[str, Any]) -> List[Dict[str, Any]]:
        return (twins_map.get((d.get("cloudDevice") or "").strip())
                or twins_map.get(d.get("name")) or [])

    fp2ctw: Dict[str, List[Dict[str, Any]]] = {}
    for d in raw:
        t = _twins_of(d)
        if t:
            fp2ctw.setdefault(_device_fingerprint(d), t)
    devices = []
    for d in raw:
        fp = _device_fingerprint(d)
        cd = matched.get(d.get("name")) or fp2cd.get(fp)
        twins = _twins_of(d) or fp2ctw.get(fp, [])
        d2 = dict(d)
        # mqtt_matched = 该设备已被 MQTT 识别（盒子正上报真实读数）——用于实时读数展示，
        # 注意：不等于「已下发云端 CRD」！下发状态请以 /box/devices/cloud 的云端 CRD 为准。
        d2["mqtt_matched"] = bool(cd)
        d2["cloud_matched"] = bool(cd)   # 兼容旧字段（语义同 mqtt_matched）
        d2["last_seen"] = cd.get("last_seen") if cd else None
        d2["primary"] = cd.get("primary") if cd else None
        # 在线 = 有实时数据推送（CRD twins 或 MQTT 双通道，窗口 DATA_FRESH_SECONDS 内）；
        # data_ts = 最后数据时间 = 最后在线时间（epoch 秒）。读不到数据即离线。
        fresh, last = data_fresh(twins, cd)
        d2["data_online"] = fresh
        d2["data_ts"] = last
        devices.append(d2)
    return {"models": data.get("models", []), "devices": devices, "cloud_devices": cloud}


def _regenerate_devices_for_model(data: Dict[str, List[Dict[str, Any]]], model_name: str,
                                  properties: List[Dict[str, Any]], protocol: str = "modbus") -> List[str]:
    """模型点位变更后，重新生成所有引用该模型的设备的 YAML（对同一模型的所有设备同时生效）。

    设备 YAML 的 modbus visitor 来自模型属性点位，因此模型点位更新后必须重刷每个引用设备的
    device YAML，否则下发时其他设备仍是旧点位。各设备自身字段（节点/通信参数/采集周期等）保持不变。
    返回发生变更的设备名列表。
    """
    changed = []
    devices = data.get("devices", [])
    for d in devices:
        if d.get("model") != model_name:
            continue
        sample = {
            "modelName": model_name,
            "deviceName": d.get("name"),
            "namespace": d.get("namespace", "default"),
            "nodeName": d.get("node", "edge-node"),
            "collectCycle": int(d.get("collectCycle", 1000)),
            "protocol": d.get("protocol") or protocol,
            "properties": properties,
            "comm": d.get("comm") or {},
            "opcua": d.get("opcua") or {},
            "bluetooth": d.get("bluetooth") or {},
            "lora": d.get("lora") or {},
            "cellular": d.get("cellular") or {},
            "cloudDevice": d.get("cloudDevice") or "",
        }
        new_yaml = generate_device_yaml(sample)["device"]
        if d.get("yaml") != new_yaml:
            d["yaml"] = new_yaml
            d["properties"] = [dict(x) for x in properties]
            changed.append(d.get("name"))
    return changed


def create_device(p: Dict[str, Any]) -> Dict[str, Any]:
    """创建设备/模型。mode=dryRun 仅返回 YAML 预览；mode=apply 保存到本地配置 box_devices.json（可一键下发云端 K3s）。

    模型点位变更对同一模型的所有设备同时生效：编辑设备（含属性点位变更）时会同步更新同名模型，
    并重刷所有引用该模型的设备的 YAML（各设备通信参数/节点不变，仅点位随模型变化）。
    """
    mode = p.get("mode", "apply")
    yamls = generate_device_yaml(p)
    if mode == "dryRun":
        return {"ok": True, "mode": "dryRun", "yamls": yamls}

    data = _load_devices()
    model_name = p.get("modelName")
    # 模型 upsert：编辑设备（含属性点位变更）时同步更新同名模型配置
    model_rec = {
        "name": model_name, "namespace": p.get("namespace", "default"),
        "protocol": p.get("protocol", "modbus"),
        "properties": p.get("properties", []),
        "yaml": yamls["model"], "created_at": int(time.time()),
    }
    models = data.get("models", [])
    existed = any(m.get("name") == model_name for m in models)
    if existed:
        models = [model_rec if m.get("name") == model_name else m for m in models]
    else:
        models.append(model_rec)
    data["models"] = models
    # 模型点位变更 -> 同步重刷所有引用该模型的设备 YAML（对同模型所有设备同时生效）
    synced = _regenerate_devices_for_model(data, model_name, p.get("properties", []), p.get("protocol", "modbus"))
    # 设备
    devices = data.get("devices", [])
    dev = {
        "name": p.get("deviceName"), "namespace": p.get("namespace", "default"),
        "model": p.get("modelName"), "node": p.get("nodeName", "edge-node"),
        "protocol": p.get("protocol", "modbus"),
        "collectCycle": int(p.get("collectCycle", 1000)),
        "cloudDevice": (p.get("cloudDevice") or "").strip(),   # 可选：绑定云端识别设备 id（实时匹配优先）
        # 保存协议通信参数（供编辑回填），避免编辑时丢失串口/slaveID 等配置
        "comm": p.get("comm") or {},
        "opcua": p.get("opcua") or {},
        "bluetooth": p.get("bluetooth") or {},
        "lora": p.get("lora") or {},
        "cellular": p.get("cellular") or {},
        "properties": p.get("properties", []),
        "yaml": yamls["device"], "created_at": int(time.time()),
        "status": "reporting",
    }
    # 改名场景：编辑设备时若携带原设备名 origName 且与原设备名不同，先移除旧记录，
    # 避免「对现有设备改名后残留旧设备、同时新增新设备」的问题
    renamed_from = ""
    orig = (p.get("origName") or "").strip()
    if orig and orig != dev["name"]:
        renamed_from = orig
        # 云端绑定标识跟随改名：若 cloudDevice 恰为原设备名（同名绑定），一并更新为新名，
        # 保证本地绑定与云端新 CRD 一致（旧 CRD 由云端下发侧删除）
        if dev.get("cloudDevice") == orig:
            dev["cloudDevice"] = dev["name"]
        devices = [x for x in devices if x.get("name") != orig]
    devices = [x for x in devices if x.get("name") != dev["name"]]
    devices.append(dev)
    data["devices"] = devices
    _save_devices(data)
    result = {"ok": True, "mode": "apply", "yamls": yamls, "device": dev, "synced_devices": synced}
    if renamed_from:
        result["renamed_from"] = renamed_from
    # 自动同步云端：本地保存配置后云端及时同步（下发新设备，改名联动删除云端旧 CRD）
    result["cloud_sync"] = _auto_sync_cloud(dev["name"], dev.get("namespace", "default"), renamed_from)
    return result


def update_model(p: Dict[str, Any]) -> Dict[str, Any]:
    """更新模型点位（properties）并下发：对引用该模型的所有设备同时生效。

    mode=dryRun 仅返回模型 YAML 预览；mode=apply 更新模型配置，并同步重刷所有引用该模型的
    设备的 YAML（各设备自身通信参数/节点不变），返回受影响设备列表供前端提示。
    """
    mode = p.get("mode", "apply")
    name = p.get("modelName") or ""
    if not name:
        raise ValueError("模型名不能为空")
    namespace = p.get("namespace", "default")
    protocol = p.get("protocol", "modbus")
    props = p.get("properties", [])
    yamls = generate_device_yaml({
        "modelName": name, "deviceName": name + "-model-preview", "namespace": namespace,
        "nodeName": "edge-node", "collectCycle": 1000, "protocol": protocol,
        "properties": props, "comm": {}, "opcua": {}, "bluetooth": {},
        "lora": {}, "cellular": {},
    })
    if mode == "dryRun":
        return {"ok": True, "mode": "dryRun", "yamls": {"model": yamls["model"]}}

    data = _load_devices()
    model_rec = {
        "name": name, "namespace": namespace, "protocol": protocol,
        "properties": props, "yaml": yamls["model"], "created_at": int(time.time()),
    }
    models = data.get("models", [])
    existed = any(m.get("name") == name for m in models)
    models = [model_rec if m.get("name") == name else m for m in models]
    if not existed:
        models.append(model_rec)
    data["models"] = models
    synced = _regenerate_devices_for_model(data, name, props, protocol)
    _save_devices(data)
    result: Dict[str, Any] = {"ok": True, "mode": "apply", "model": name,
                              "synced_devices": synced, "yamls": {"model": yamls["model"]}}
    # 自动同步云端：模型点位变更后下发该模型 + 所有引用设备，云端及时同步
    try:
        mr = apply_devices_to_cloud(model_name=name)
        if mr.get("ok"):
            result["cloud_sync"] = {"ok": True, "applied": mr.get("applied", [])}
        else:
            result["cloud_sync"] = {
                "ok": False,
                "error": (mr.get("error") or mr.get("stderr") or mr.get("stdout") or "云端同步失败").strip(),
            }
    except Exception as e:  # noqa: BLE001
        result["cloud_sync"] = {"ok": False, "error": f"云端同步异常：{e}"}
    return result


def delete_device(kind: str, name: str, namespace: str = "default",
                  cloud: bool = False, local: bool = True) -> Dict[str, Any]:
    """删除设备（kind=device 删除 Device；kind=model 删除 DeviceModel，同时移除引用它的设备）。

    cloud=True 时同时调云端 agent 本地 kubectl delete 真实 CRD（对应云端管理台 /api/devices/delete）；
    local=True（默认）同时移除本地 box_devices.json 配置。local=False 且 cloud=True 时仅删云端 CRD。
    """
    result: Dict[str, Any] = {}
    if local:
        data = _load_devices()
        removed = {"models": [], "devices": []}
        if kind in ("model", "both"):
            before = [m.get("name") for m in data.get("models", [])]
            data["models"] = [m for m in data.get("models", []) if m.get("name") != name]
            removed["models"] = [n for n in before if n not in [m.get("name") for m in data["models"]]]
            # 移除引用该模型的设备
            before_d = [d.get("name") for d in data.get("devices", [])]
            data["devices"] = [d for d in data.get("devices", []) if d.get("model") != name]
            removed["devices"] = [n for n in before_d if n not in [d.get("name") for d in data["devices"]]]
        if kind in ("device", "both"):
            before = [d.get("name") for d in data.get("devices", [])]
            data["devices"] = [d for d in data.get("devices", []) if d.get("name") != name]
            removed["devices"] = [n for n in before if n not in [d.get("name") for d in data["devices"]]]
        _save_devices(data)
        result["removed"] = removed
    if cloud:
        result["cloud"] = _cloud_delete_crds(kind, name, namespace)
    result["ok"] = True
    return result
