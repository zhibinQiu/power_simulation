"""采集设备 CRUD：DeviceModel/Device 的增删改 + YAML 渲染 + 变更自动下发。

职责边界：本模块是「平台侧设备定义的唯一真值源 + 变更入口」。设备的新增/改名/删除
在此完成后，由各自的实现分别把结果推给云端 CRD 与盒子 mapper（盒子侧见 lora_dtu），
调用方不感知链路细节，也不需要额外的「同步」动作。

YAML 渲染按协议分派给 domain/box/device_yaml.py 的渲染器（工厂注册，新增协议不改本层）。
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional

from ..integrations import cloud_agent
from .. import mqtt_source
from ..domain.box import DeviceYamlFactory
from ..domain.box.hwid import backfill_hwids, ensure_hwid, hwid_of
from ._shared import _load_devices, _save_devices, data_fresh, last_data_ts
from .lora_dtu import push_lora_config
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


def _device_yaml_kwargs(d: Dict[str, Any]) -> Dict[str, Any]:
    """把一条设备配置记录还原成 generate_device_yaml 所需的请求参数。

    注意 hwId 必须带上：device_yaml 只在 hwId 非空时输出 nengtan.io/hwid label，
    漏传会让重刷出来的 YAML 丢掉标签，云端 CRD 与本地记录就此不一致。
    """
    return {
        "modelName": d.get("model") or "",
        "deviceName": d.get("name"),
        "namespace": d.get("namespace", "default"),
        "nodeName": d.get("node", "edge-node"),
        "collectCycle": int(d.get("collectCycle", 1000)),
        "protocol": d.get("protocol") or "modbus",
        "properties": [dict(x) for x in (d.get("properties") or [])],
        "comm": d.get("comm") or {},
        "opcua": d.get("opcua") or {},
        "bluetooth": d.get("bluetooth") or {},
        "lora": d.get("lora") or {},
        "cellular": d.get("cellular") or {},
        "cloudDevice": d.get("cloudDevice") or "",
        "hwId": d.get("hwId") or "",
    }


def _resync_stale_device_yamls(data: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """补齐存量设备的 YAML，保证「本地记录」与「下发到云端的 YAML」一致。

    典型场景：hwId 是后加的能力，老设备记录里补齐了 hwId，YAML 却还是旧模板（没有
    nengtan.io/hwid label），下发到云端后 CRD 与本地记录不一致（时序库/盒子按 hwId 认设备时
    表现为同一台硬件在两个环境里是两种身份）。保存任意设备时顺带把这类存量 YAML 补齐，
    并返回受影响设备名，便于一并发到云端真正落到 CRD 上。

    点位为空的设备跳过：那会命中 device_yaml 的空点位兜底（value），反而制造不一致。
    """
    changed = []
    for d in data.get("devices", []) or []:
        if not isinstance(d, dict) or not d.get("properties"):
            continue
        new_yaml = generate_device_yaml(_device_yaml_kwargs(d))["device"]
        if d.get("yaml") != new_yaml:
            d["yaml"] = new_yaml
            changed.append(d.get("name"))
    return changed


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
        sample = _device_yaml_kwargs(d)
        # 点位与协议以本次传入的为准（模型可能刚变更），其余字段保持设备自身配置
        sample.update({"modelName": model_name, "properties": properties,
                       "protocol": d.get("protocol") or protocol})
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
    p = dict(p)
    if mode == "dryRun":
        # 预览：按硬件特征派生候选 hwId 一并展示（不落盘、不占用）
        p["hwId"] = hwid_of(p) or ""
        return {"ok": True, "mode": "dryRun", "yamls": generate_device_yaml(p)}

    data = _load_devices()
    devices_all = data.get("devices", []) or []
    # 存量迁移：尚无 hwId 的设备一次性补齐（此后 hwId 终身不变）
    backfill_hwids(devices_all)
    # 顺带把存量设备的 YAML 补齐（缺 nengtan.io/hwid label 等）：保证本地记录与下发到
    # 云端的 YAML 同源，这些设备会随本次保存一并发到云端（见下方 extra_devices）。
    stale_yamls = _resync_stale_device_yamls(data)
    orig = (p.get("origName") or "").strip()
    old = next((x for x in devices_all if x.get("name") == orig), None) if orig else None
    taken = {str(x.get("hwId") or "") for x in devices_all
             if str(x.get("hwId") or "") and x.get("name") not in (orig, p.get("deviceName"))}
    # 改名继承原设备的 hwId → 云端 CRD / 盒子配置 / 时序库都视为同一台硬件，历史不断链
    p["hwId"] = ensure_hwid(p, inherit=(old or {}).get("hwId", ""), taken=taken)
    yamls = generate_device_yaml(p)
    model_name = (p.get("modelName") or "").strip()
    props_in = [dict(x) for x in (p.get("properties") or []) if isinstance(x, dict)]
    models = data.get("models", [])
    existed_model = next((m for m in models if m.get("name") == model_name), None)
    # 模型 upsert：编辑设备（含属性点位变更）时同步更新同名模型配置。
    # 守卫：请求未携带点位时**不得**改写已存在的共享模型——否则保存/改名一台设备会把共享模型
    # 点位清空，并级联清空同模型所有设备的采集点位（设备随即无数据）。
    if props_in or existed_model is None:
        model_rec = {
            "name": model_name, "namespace": p.get("namespace", "default"),
            "protocol": p.get("protocol", "modbus"),
            "properties": props_in,
            "yaml": yamls["model"], "created_at": int(time.time()),
        }
        if existed_model is not None:
            models = [model_rec if m.get("name") == model_name else m for m in models]
        else:
            models.append(model_rec)
        data["models"] = models
    # 重刷/下发所用的点位：请求带点位用请求的，未带则沿用模型现有点位（不退化为空）
    props_for_sync = props_in or [dict(x) for x in (existed_model or {}).get("properties") or []]
    # 设备 YAML 必须按「最终点位」重新生成：请求未带点位（沿用绑定模型的点位）时，上面那次
    # generate_device_yaml(p) 拿到的是空列表，device_yaml 会渲染成兜底的点位 "value"
    # （collectCycle 也退回 1000）。若直接落盘并下发，表现为本地配置/设备详情显示 temperature、
    # 云端 CRD 却是 value —— 即「本地与云端不一致」，且盒子按 value 取数导致设备无数据。
    # 因此点位确定后必须重生成设备 YAML，再写盘/下发。
    yamls["device"] = generate_device_yaml(dict(p, properties=props_for_sync))["device"]
    # 模型点位变更 -> 同步重刷所有引用该模型的设备 YAML（对同模型所有设备同时生效）
    synced = _regenerate_devices_for_model(data, model_name, props_for_sync, p.get("protocol", "modbus"))
    # 设备
    devices = data.get("devices", [])
    dev = {
        "name": p.get("deviceName"), "namespace": p.get("namespace", "default"),
        "hwId": p["hwId"],   # 硬件唯一 ID：绑定硬件特征，改名不变（显示名 name 可变）
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
        "properties": props_for_sync,
        "yaml": yamls["device"], "created_at": int(time.time()),
        "status": "reporting",
    }
    # 改名场景：编辑设备时若携带原设备名 origName 且与原设备名不同，先移除旧记录，
    # 避免「对现有设备改名后残留旧设备、同时新增新设备」的问题
    renamed_from = ""
    orig = (p.get("origName") or "").strip()
    if orig and orig != dev["name"]:
        # 改名目标名不得与本地其它设备重名：否则本地记录被静默覆盖、云端 CRD 也会被顶替，
        # 表现为「改名后某台设备连同实时数据一起消失」
        clash = [x.get("name") for x in data.get("devices", [])
                 if x.get("name") == dev["name"] and x.get("name") != orig]
        if clash:
            raise ValueError(
                f"设备名「{dev['name']}」已被其它设备占用，改名会覆盖该设备（其云端设备也会被顶替）。"
                "请先删除或改名该设备后再试。")
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
    # 连带下发：① 本次被重刷 YAML 的同模型其它设备；② 本次被补齐 YAML 的存量设备
    # ——只写本地不发云端的话，本地与云端又会不一致（正是本次要根治的问题）。
    extra = [x for x in list(synced) + list(stale_yamls)
             if x and x not in (dev["name"], renamed_from)]
    result["cloud_sync"] = _auto_sync_cloud(
        dev["name"], dev.get("namespace", "default"), renamed_from, extra_devices=extra,
    )
    # 盒子侧的取数配置随之生效：每台设备按自己的参数（含 LoRa 从站号拼出的那条问帧）
    # 独立取数；改名后平台上已没有的旧名在盒子上停采，避免旧任务继续上报幽灵数据。
    # 没有单独的「同步问帧」步骤 —— 保存设备就是下发。盒子不可达不影响本次保存。
    try:
        result["box_sync"] = push_lora_config(dev.get("node", ""))
    except Exception as e:  # noqa: BLE001 - 盒子侧向失败不阻断平台保存
        result["box_sync"] = {"ok": False, "error": str(e)}
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


def _stop_stale_polls(nodes: "Iterable[str]") -> Dict[str, Any]:
    """删除后向受影响的盒子重推取数配置：平台上已不存在的条目从盒子配置里删除。

    盒子 mapper 的配置是平台侧设备定义的映射，删除设备必须落到盒子执行，
    否则 mapper 继续按旧配置轮询并按旧名上报，平台上会出现幽灵数据。
    注意是「删除」不是「停采」：采集设备没有停用态，留一条 enabled=false 的条目
    在平台上仍表现为「有这台设备却没数据」。
    """
    out: Dict[str, Any] = {}
    for n in sorted({x for x in nodes if str(x or "").strip()}):
        try:
            out[str(n)] = push_lora_config(str(n))
        except Exception as e:  # noqa: BLE001 - 盒子侧向失败不阻断本地删除
            out[str(n)] = {"ok": False, "error": str(e)}
    return out


def delete_device(kind: str, name: str, namespace: str = "default",
                  cloud: bool = True, local: bool = True) -> Dict[str, Any]:
    """删除设备（kind=device 删除 Device；kind=model 删除 DeviceModel，同时移除引用它的设备）。

    删除是一处改动多处生效：本地配置、云端 CRD（cloud=True，默认）、盒子 mapper 取数配置
    三者同步，调用方无需再单独触发任何下发动作。
    local=True（默认）移除本地 box_devices.json 配置；local=False 且 cloud=True 时仅删云端 CRD。
    """
    result: Dict[str, Any] = {}
    nodes: set = set()
    if local:
        data = _load_devices()
        removed = {"models": [], "devices": []}
        # 记录受影响的盒子：删除跟着落到这些盒子的 mapper 配置上
        nodes = {str(d.get("node") or "").strip() for d in (data.get("devices") or [])}
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
    result["box_sync"] = _stop_stale_polls(nodes)
    result["ok"] = True
    return result
