"""能碳一体机管理台后端（参照参考项目 yunduan1 的 console 管理台 + dashboard 实时仪表盘）。

将 yunduan1 的全部能力集成到「能碳一体机管理」视图：
1. 概览：云端 MQTT Broker 实时统计（$SYS，真实）+ cloudcore/节点/端口/证书/token（云端 cloud-agent 采集经 MQTT 推送，不可达即报错，不造假）；
2. 设备管理：DeviceModel/Device CRUD（Modbus/OPC-UA/Bluetooth 三协议 YAML 生成，本地保存配置，一键下发云端 K3s）；
3. 盒子接入：edgecore.yaml 模板渲染 + 共享 token + caHash + 部署命令；
4. 实时数据：Device.status.twins 实时上报值（云端 K3s CRD 主链路 + MQTT 兜底）+ 实时消息流 + 发测试消息；
5. 接入指引：数据链路说明（box-mapper 采集链路、盒子侧采集、部署包、诊断工具）。

架构一致性（与 yunduan1 相同）：管理台只做「配置」与「读取展示」，
传感器读数来自边缘真实上报（云端 K3s CRD twins 主链路，MQTT data/# 兜底；本平台不生成模拟读数）。
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import cloud_agent
from . import mqtt_source
from .core.storage import JsonRepository
from .domain.box import DeviceYamlFactory

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEVICES_FILE = CONFIG_DIR / "box_devices.json"
EDGECORE_TEMPLATE = CONFIG_DIR / "edgecore.template.yaml"

_LOCK = threading.Lock()
# 设备 twins 趋势历史：dev_id -> [(epoch, value)]
_TWIN_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
_TWIN_HISTORY_MAX = 120

# 设备/模型/云端配置统一仓储（原子写盘 + 内存缓存，替代手工 json 读写）
_devices_repo = JsonRepository(str(DEVICES_FILE), default={"models": [], "devices": []})


def _load_devices() -> Dict[str, List[Dict[str, Any]]]:
    return _devices_repo.read()


def _save_devices(data: Dict[str, List[Dict[str, Any]]]) -> None:
    _devices_repo.write(data)


# ------------------------- 设备 YAML 生成（工厂模式，实现位于 domain/box/device_yaml.py） -------------------------
def generate_device_yaml(p: Dict[str, Any]) -> Dict[str, str]:
    """生成 DeviceModel + Device 两份 YAML（v1beta1 结构，参照 kubeedge-console-ops.md §5.2）。

    支持协议: modbus / opcua / bluetooth（渲染器注册于 DeviceYamlFactory，新增协议无需改动本层）。
    """
    return DeviceYamlFactory.get(p.get("protocol", "modbus")).render(p)


# ------------------------- 云端 K3s/KubeEdge 状态采集（云端 agent MQTT 推送 + HTTP，替代 SSH） -------------------------
def _fetch_cloud_k8s(force: bool = False) -> Dict[str, Any]:
    """云端 K3s/KubeEdge 状态（cloudcore / 节点 / 端口 / 证书 / token）。

    数据通道（替代 SSH）：云端 cloud-agent 定时采集（kubectl/openssl/ss）后经 MQTT
    长连接推送到 cloud/state 主题，本平台订阅线程实时更新缓存，请求路径只读缓存
    （毫秒级）；force=True 时 HTTP GET agent 实时拉取（盒子接入取最新 token 用）。
    云端不可达时返回 ok=False + 具体错误。
    """
    return cloud_agent.state(force=force)


# ------------------------- 概览（cloudcore / 节点 / 端口 / 证书 / token，云端 agent MQTT 推送） -------------------------
def _mqtt_boxes() -> List[Dict[str, Any]]:
    """从 MQTT 云端设备分组识别盒子列表（box_overview 共用）。

    盒子侧版本未知时不虚构 version；age 取最近上报时间。
    """
    now = time.time()
    boxes: Dict[str, Dict[str, Any]] = {}
    with mqtt_source._LOCK:  # noqa: SLF001
        for cid, info in mqtt_source.CLOUD_DEVICES.items():
            b = info.get("box") or "unknown-box"
            boxes.setdefault(b, {"box": b, "devices": 0, "last_seen": 0})
            boxes[b]["devices"] += 1
            boxes[b]["last_seen"] = max(boxes[b]["last_seen"], float(info.get("last_seen") or 0))

    mqtt_nodes: List[Dict[str, Any]] = []
    for b, info in sorted(boxes.items()):
        last = info["last_seen"]
        mqtt_nodes.append({
            "name": b, "ready": bool(last and (now - last) < 30),
            "roles": "edge", "version": "—",
            "age": datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "未上报",
            "devices": info["devices"], "source": "mqtt", "is_edge": True,
        })
    return mqtt_nodes


def _merge_nodes(cloud: Dict[str, Any], mqtt_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并 K8s edge 节点（SSH 真实）+ MQTT 识别盒子（按 name 去重）；无节点时返回空数组（不虚构 box-001）。

    去重按「归一化名称」比对：K8s 节点名（Device nodeName，如 nt001）与盒子 MQTT boxId
    （config.json mqtt.boxId，如 box-nt001）可能带/不带 box- 前缀，归一化后视为同一盒子，
    避免同一盒子在卡片上重复显示（保留 K8s 条目，其 name 为节点真实名）。
    """
    k8s_nodes = [n for n in cloud.get("nodes", []) if n.get("is_edge")]
    def _norm(name: str) -> str:
        s = str(name or "")
        return s[4:] if s.startswith("box-") else s
    seen = {_norm(n["name"]) for n in k8s_nodes}
    merged = list(k8s_nodes)
    for n in mqtt_nodes:
        key = _norm(n["name"])
        if key not in seen:
            seen.add(key)
            merged.append(n)
    return merged


def box_overview() -> Dict[str, Any]:
    """管理台概览：Broker 统计（$SYS，真实）+ cloudcore/节点/端口/证书/token（云端 cloud-agent 采集经 MQTT 推送）。

    云端不可达时明确返回 cloud_source=unreachable + 错误原因，不再返回任何仿真数据。
    """
    # 识别到的盒子（真实）：来自 MQTT 云端设备的分组
    mqtt_nodes = _mqtt_boxes()

    cloud = _fetch_cloud_k8s()
    # 缓存新鲜度：agent 推送中断（云端 broker/agent 离线）时旧缓存不得冒充实时状态
    cached_stale = bool(cloud.get("_cached")) and not cloud.get("_cache_fresh", True)
    live = bool(cloud.get("ok")) and not cached_stale
    nodes = _merge_nodes(cloud, mqtt_nodes)
    # 盒子卡片展示：附加盒子当前运行的服务/模型列表（来自盒子 state/{box}/services 周期上报）
    for n in nodes:
        nm = str(n.get("name") or "")
        svcs = mqtt_source.box_services(nm) or []
        if not svcs and nm and not nm.startswith("box-"):
            svcs = mqtt_source.box_services("box-" + nm) or []
        if not svcs and nm.startswith("box-") and len(nm) > 4:
            svcs = mqtt_source.box_services(nm[4:]) or []
        n["services"] = svcs
    # 云端推送中断：K8s 节点状态为过期缓存，标记「状态未知」而非误显示就绪/未就绪
    if cached_stale:
        for n in nodes:
            if n.get("is_edge") and n.get("ready") is not None:
                n["ready"] = None
                n["stale"] = True

    stats = mqtt_source.broker_stats()
    status = mqtt_source.get_status()
    cc = cloud.get("cloudcore")
    cc_ok = bool(cc and cc.get("phase") == "Running")
    if not cc:
        cc = {"name": "—", "phase": "未运行/未找到", "restarts": "—", "node": "—", "podIP": "—",
              "available": False,
              "error": cloud.get("error", "") or "云端未解析到 cloudcore Pod（kubectl get pod 无结果）"}
    else:
        cc["available"] = cc.get("phase") == "Running"
    # cloud_source 四态：live=agent 推送实时且 cloudcore 运行；stale=推送中断、展示的是过期缓存；
    # degraded=实时但组件异常；unreachable=云端完全不可达
    if not live and cached_stale:
        cloud_source = "stale"
    elif not live:
        cloud_source = "unreachable"
    elif cc_ok:
        cloud_source = "live"
    else:
        cloud_source = "degraded"
    if cloud_source == "live":
        cloud_error = ""
    elif cloud_source == "stale":
        age = cloud.get("_cache_age", 0)
        cloud_error = (f"云端推送已中断（缓存数据 {age}s 前更新，超过 120s 即视为过期）："
                       f"云端 MQTT Broker / cloud-agent 可能离线，或平台与云端 {status.get('broker_host')}:{status.get('broker_port')} 连接断开。"
                       f"当前节点/CloudCore 状态为过期缓存，请检查云端服务后重启平台后端恢复订阅。")
    else:
        cloud_error = cloud.get("error", "") or cc.get("error", "")
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "broker": {
            "host": status.get("broker_host"), "port": status.get("broker_port"),
            "connected": status.get("connected", False),
            "stats": stats,   # $SYS 真实统计
        },
        "cloudcore": cc,
        "nodes": nodes,
        "ports": cloud.get("ports", []),
        "certs": cloud.get("certs", []),
        "token": cloud.get("token"),
        "cloud_source": cloud_source,
        "cloud_error": cloud_error,
        "demo_note": "" if cloud_source == "live" else (
            f"云端推送中断（数据 {cloud.get('_cache_age', 0)}s 前更新）：云端 MQTT Broker / cloud-agent 可能离线。"
            f"以下 CloudCore/端口/证书/token 为过期缓存（不伪造数据）。"
            if cloud_source == "stale" else
            f"云端数据通道不可达：{cloud.get('error', '')}。"
            f"以上 CloudCore/端口/证书/token 为空或不完整（不伪造数据），"
            f"请检查云端 MQTT Broker / cloud-agent 服务后重试。"
            if cloud_source == "unreachable" else
            f"云端 agent 实时可达，但 CloudCore 未运行或未解析到 Pod（{cloud_error}）。请检查云端 cloudcore 状态。"
        ),
    }


# ------------------------- 设备 CRUD -------------------------
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
    devices = []
    for d in raw:
        cd = matched.get(d.get("name")) or fp2cd.get(_device_fingerprint(d))
        d2 = dict(d)
        # mqtt_matched = 该设备已被 MQTT 识别（盒子正上报真实读数）——用于实时读数展示，
        # 注意：不等于「已下发云端 CRD」！下发状态请以 /box/devices/cloud 的云端 CRD 为准。
        d2["mqtt_matched"] = bool(cd)
        d2["cloud_matched"] = bool(cd)   # 兼容旧字段（语义同 mqtt_matched）
        d2["last_seen"] = cd.get("last_seen") if cd else None
        d2["primary"] = cd.get("primary") if cd else None
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


_K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")


def _cloud_delete_crds(kind: str, name: str, namespace: str) -> Dict[str, Any]:
    """调云端 agent 删除真实 CRD（agent 本地 kubectl delete device|devicemodel，HTTP POST /api/delete）。

    --ignore-not-found 保证幂等（云端对象不存在不报错）；对象名按 k8s 命名规则校验防注入。
    """
    if not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"云端对象名不合法：{name}"}
    if namespace and not _K8S_NAME_RE.fullmatch(namespace):
        return {"ok": False, "error": f"命名空间不合法：{namespace}"}
    if kind not in ("device", "model", "both"):
        return {"ok": False, "error": f"kind 不合法：{kind}"}
    return cloud_agent.delete(kind, name, namespace)


# systemd 服务重启白名单（云端，经 agent systemctl restart）
_SYSTEMD_ALLOW = {"cloud-agent", "nengtan-cloud-broker", "nengtan-collector", "nengtan-cloud-dashboard"}

# 边缘盒子服务重启白名单（经 agent SSH 到边缘盒子 systemctl restart）
_EDGE_UNIT_ALLOW = {"box-mapper", "edgecore", "box-collector"}


def restart_cloud_workload(kind: str = "deployment", name: str = "cloudcore",
                           namespace: str = "kubeedge") -> Dict[str, Any]:
    """重启云端/边缘服务（默认 cloudcore）：调云端 agent 本地执行（HTTP POST /api/restart）。

    - kind=deployment（默认，cloudcore）：kubectl rollout restart deployment（滚动重启不中断）；
    - kind=pod：kubectl delete pod（Deployment 自动重建）；
    - kind=systemd：systemctl restart 云端服务（白名单：cloud-agent / nengtan-cloud-broker
      / nengtan-collector / nengtan-cloud-dashboard），namespace 忽略；
    - kind=edge：SSH 到边缘盒子 systemctl restart 边缘服务（白名单：box-mapper / edgecore
      / box-collector），namespace 忽略。

    用于 CloudCore 崩溃/边缘 Mapper 掉线时快速恢复。名称按 k8s 命名规则校验防注入。
    """
    if not name or not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"云端对象名不合法：{name}"}
    if kind in ("deployment", "deploy", "pod"):
        if namespace and not _K8S_NAME_RE.fullmatch(namespace):
            return {"ok": False, "error": f"命名空间不合法：{namespace}"}
        return cloud_agent.restart(kind, name, namespace)
    if kind == "systemd":
        if name not in _SYSTEMD_ALLOW:
            return {"ok": False, "error": f"systemd 服务不在白名单：{name}（仅支持 {'/'.join(sorted(_SYSTEMD_ALLOW))}）"}
        return cloud_agent.restart("systemd", name, "")
    if kind == "edge":
        if name not in _EDGE_UNIT_ALLOW:
            return {"ok": False, "error": f"边缘服务不在白名单：{name}（仅支持 {'/'.join(sorted(_EDGE_UNIT_ALLOW))}）"}
        # 盒子运行期无直达 IP：重启 Mapper 必须配置可达地址（现场内网/跳板机/frp），
        # IP 为空或 SSH 探测不通时拒绝重启，避免无意义下发
        edge_cfg = edge_config().get("edge") or {}
        host = str(edge_cfg.get("host") or "").strip()
        if not host:
            return {"ok": False, "error": "未配置盒子 IP（在盒子卡片上填写现场可达地址后重试），拒绝重启 %s" % name}
        check = check_edge_reachable(host=host, port=int(edge_cfg.get("port") or 22))
        if not check.get("reachable"):
            return {"ok": False, "error": "盒子 IP 不通（%s），拒绝重启 %s：%s"
                    % (host, name, check.get("error", "SSH 不可达"))}
        return cloud_agent.restart("edge", name, "", edge=edge_cfg)
    return {"ok": False, "error": f"kind 不合法：{kind}（仅支持 deployment / pod / systemd / edge）"}


# ------------------------- 盒子连接配置（IP/SSH 凭据）与云端部署指令 -------------------------
def edge_config() -> Dict[str, Any]:
    """读取盒子连接配置：本地 box_devices.json 顶层 edge（优先）→ 云端 agent 已存配置。

    edge 结构：{"host": 现场可达地址, "port": 22, "user": "root", "password": "", "key": ""}。
    """
    data = _load_devices()
    local = data.get("edge") if isinstance(data.get("edge"), dict) else {}
    if not local:
        remote = cloud_agent.get_edge_config()
        if remote.get("ok") and isinstance(remote.get("edge"), dict):
            local = {k: remote["edge"].get(k) for k in ("host", "port", "user", "password", "key")}
    return {"ok": True, "edge": local or {}}


def update_edge_config(p: Dict[str, Any]) -> Dict[str, Any]:
    """保存盒子连接配置到本地 box_devices.json + 云端 agent，并立即探测连通性。

    平台侧保存后 agent 侧 config.json 同步更新，重启 Mapper 等 SSH 操作使用新地址。
    """
    with _LOCK:
        data = _load_devices()
        edge = dict(data.get("edge") or {})
        for k in ("host", "port", "user", "password", "key"):
            if k in p and p[k] is not None:
                if k == "port":
                    try:
                        edge[k] = int(p[k] or 22)
                    except (TypeError, ValueError):
                        return {"ok": False, "error": "port 必须是整数：%r" % (p[k],)}
                else:
                    edge[k] = str(p[k]).strip()
        if not edge:
            return {"ok": False, "error": "缺少配置字段（host/port/user/password/key）"}
        data["edge"] = edge
        _save_devices(data)
    # 同步到云端 agent（保存成功后立即探测）；agent 未部署/不可达时不阻断本地保存，
    # 仅在返回中提示（重启 Mapper 等 SSH 操作仍需要 agent 在线且盒子可达）
    result = cloud_agent.update_edge_config(edge)
    if not result.get("ok"):
        return {"ok": True, "edge": edge, "check": None,
                "warning": "本地已保存；同步到云端 agent 失败（%s），盒子 IP 生效前需先部署/恢复 agent" % result.get("error", "")}
    return {"ok": True, "edge": edge, "check": result.get("check")}


def check_edge_reachable(host: str = "", port: int = 22) -> Dict[str, Any]:
    """探测盒子 SSH 可达性（经云端 agent TCP 探测，不实际登录）。"""
    host = (host or "").strip()
    if not host:
        cfg = edge_config().get("edge") or {}
        host = str(cfg.get("host") or "").strip()
        port = int(cfg.get("port") or 22)
    if not host:
        return {"ok": False, "reachable": False, "host": "", "port": port,
                "error": "IP 为空（未配置盒子 IP，无法 SSH 直达）"}
    return cloud_agent.check_edge(host=host, port=port)


def _resolve_box_id(box: str) -> str:
    """盒子名 -> MQTT boxId：优先精确匹配，其次尝试 box- 前缀（兼容 K8s 节点名 vs MQTT boxId 不一致）。"""
    box = (box or "").strip()
    if not box:
        return box
    with mqtt_source._LOCK:  # noqa: SLF001
        known = {str(i.get("box")) for i in mqtt_source.CLOUD_DEVICES.values() if i.get("box")}
    if box in known:
        return box
    if box.startswith("box-"):
        return box
    if ("box-" + box) in known:
        return "box-" + box
    return box


def box_app_cmd(box: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """向盒子下发应用部署/启停指令（MQTT 命令主题 cmd/{box}/deploy）。

    盒子运行期无直达 IP，云端→盒子方向只能经云端 Broker 命令主题：
    盒子 mapper 订阅 cmd/{box}/# 收到指令后执行，并回报 state/{box}/deploy。
    """
    box = _resolve_box_id(box)
    if not box:
        return {"ok": False, "error": "box 名为空"}
    if not isinstance(payload, dict) or not str(payload.get("cmd") or "").strip():
        return {"ok": False, "error": "指令需包含 cmd 字段（deploy/start/stop/restart/remove/list）"}
    return mqtt_source.publish_box_cmd(box, payload)


def box_app_list(box: str) -> Dict[str, Any]:
    """查询盒子当前运行的服务/模型列表（来自盒子 state/{box}/services 周期上报）。"""
    box = _resolve_box_id(box)
    services = mqtt_source.box_services(box)
    events = mqtt_source.box_app_events(box)
    return {"ok": True, "box": box, "services": services, "events": events}


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


# ------------------------- 云端一键下发（云端 agent HTTP API，替代 SSH） -------------------------
def cloud_config() -> Dict[str, Any]:
    """云端部署配置：agent 主机/端口/token + 命名空间（数据通道替代 SSH）。

    主机地址默认复用云端 Broker 配置中的 host（broker 即部署于云端，无需再单独配置 IP），
    仅在 box_devices.json 顶层 cloud.host 显式设置时优先使用该值。
    """
    data = _load_devices()
    c = data.get("cloud") or {}
    broker_host = mqtt_source.get_config().get("broker", {}).get("host", "") if mqtt_source else ""
    return {
        "host": (c.get("host") or "").strip() or broker_host or "172.19.134.45",
        "agent_port": int(c.get("agent_port", 42083)),
        "agent_token": c.get("agent_token", ""),
        "namespace": c.get("namespace", "default"),
    }


def update_cloud_config(p: Dict[str, Any]) -> Dict[str, Any]:
    """保存云端 agent 连接配置（agent_port/agent_token/namespace）到 box_devices.json 顶层 cloud。"""
    data = _load_devices()
    c = data.get("cloud") or {}
    if p.get("host"):
        c["host"] = str(p.get("host") or "").strip()
    if p.get("agent_port"):
        try:
            c["agent_port"] = int(p["agent_port"])
        except (TypeError, ValueError):
            raise ValueError(f"agent 端口不合法：{p.get('agent_port')}")
    if "agent_token" in p:
        c["agent_token"] = str(p.get("agent_token") or "").strip()
    if p.get("namespace"):
        c["namespace"] = str(p.get("namespace") or "default").strip()
    data["cloud"] = c
    _save_devices(data)
    return {"ok": True, "cloud": cloud_config()}


def apply_devices_to_cloud(device_name: Optional[str] = None, dry_run: bool = False,
                           model_name: Optional[str] = None) -> Dict[str, Any]:
    """一键下发：调云端 agent 本地执行 kubectl apply -f -（HTTP POST /api/apply）。

    支持三种粒度：
    - model_name：下发该模型 + 引用它的所有设备（模型点位修改后对同模型所有设备同时生效）
    - device_name：单设备
    - 都为空：下发全部设备（每个设备带上其模型文档，模型在前保证依赖顺序）
    dry_run=True 时不执行下发，仅返回即将下发的 YAML 内容（前端预览）。
    """
    cfg = cloud_config()
    host = cfg["host"]
    data = _load_devices()
    models = {m.get("name"): m for m in data.get("models", []) if m.get("yaml")}
    devices = data.get("devices", [])
    if model_name:
        devices = [d for d in devices if d.get("model") == model_name]
    elif device_name:
        devices = [d for d in devices if d.get("name") == device_name]

    docs, applied, missing = [], [], []
    for d in devices:
        name, model = d.get("name"), d.get("model")
        if model in models and d.get("yaml"):
            docs.append(models[model]["yaml"].rstrip("\n") + "\n---\n" + d["yaml"].rstrip("\n"))
            applied.append(f"{model} + {name}")
        else:
            missing.append(name)
    if not docs:
        return {"ok": False, "error": "没有可下发的设备（缺模型或本地 YAML）：" + ",".join(missing)}

    payload = "\n---\n".join(docs) + "\n"
    if dry_run:
        return {"ok": True, "dry_run": True, "payload": payload,
                "applied": applied, "missing": missing,
                "target": f"cloud-agent@{host}:{cfg['agent_port']}  kubectl apply -f -"}

    res = cloud_agent.apply(payload)
    return {
        "ok": bool(res.get("ok")),
        "rc": res.get("rc", 1),
        "stdout": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
        "payload": payload,
        "applied": applied,
        "missing": missing,
    }


def _auto_sync_cloud(device_name: str, namespace: str = "default", renamed_from: str = "") -> Dict[str, Any]:
    """本地保存配置后自动同步云端（保存即下发，云端及时同步）。

    - 下发该设备（含其模型文档）到云端 K3s（kubectl apply）
    - 改名场景（renamed_from 非空且 != device_name）：联动删除云端旧名 CRD，避免残留旧设备
    云端不可达/下发失败时本地配置不受影响，仅返回失败信息供前端提示。
    """
    try:
        res = apply_devices_to_cloud(device_name=device_name)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"云端同步异常：{e}"}
    if not res.get("ok"):
        return {
            "ok": False,
            "error": (res.get("error") or res.get("stderr") or res.get("stdout") or "云端同步失败").strip(),
        }
    sync: Dict[str, Any] = {"ok": True, "applied": res.get("applied", [])}
    if renamed_from and renamed_from != device_name:
        del_r = _cloud_delete_crds("device", renamed_from, namespace)
        sync["old_crd_removed"] = bool(del_r.get("ok"))
        if not del_r.get("ok"):
            sync["old_crd_error"] = del_r.get("error") or del_r.get("stderr") or "旧 CRD 删除失败"
    return sync


# ------------------------- 实时数据（twins + 趋势） -------------------------
# 云端 CRD twins 由云端 agent 每 5s 经 MQTT cloud/crds 推送（cloud_agent 缓存），
# 请求路径只读缓存（毫秒级）；CloudCore 日志由 agent 每 3s 经 MQTT cloud/logs 推送。
# 全程无 SSH、无平台侧轮询线程（数据经平台已常连的 MQTT 长连接实时到达）。


def _parse_crd_ts(ts: Any) -> Optional[float]:
    """解析云端 CRD twins 的 timestamp 为 epoch 秒，失败返回 None。

    实测云端 Device.status.twins 的 timestamp 是「毫秒 epoch 字符串」（如 "1787643075724"），
    同时兼容 ISO 字符串（2026-08-25T07:14:43Z / +08:00）与秒级 epoch。
    """
    if not ts:
        return None
    s = str(ts).strip()
    # 数字：毫秒(13 位)/秒(10 位) epoch
    if s.isdigit():
        try:
            n = int(s)
            return n / 1000.0 if len(s) >= 12 else float(n)
        except Exception:  # noqa: BLE001
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except Exception:  # noqa: BLE001
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


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


# ------------------------- 云端实时日志（agent 每 3s MQTT cloud/logs 推送，环形缓冲 300 行） -------------------------

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
        out.append({
            "name": name, "model": d.get("model"), "node": d.get("node"),
            "box_ip": d.get("box_ip"),
            "state": "reporting" if (ctw or cd) else "pending",
            "lastOnlineTime": (_parse_crd_ts((ctw or {}).get("lastOnlineTime", ""))
                               or (cd.get("last_seen") if cd else None)),
            "twins": twins,
            "history": {t["propertyName"]: _TWIN_HISTORY.get(f"{name}::{t['propertyName']}", [])
                        for t in twins},
        })
    # 防内存泄漏：清理已删除设备/属性的历史 key（保留当前设备仍在用的）
    active_keys = {f"{d.get('name')}::{p.get('name')}" for d in raw_devs for p in (d.get("properties") or [])}
    for k in [k for k in _TWIN_HISTORY if k not in active_keys]:
        _TWIN_HISTORY.pop(k, None)
    return {"devices": out, "time": now}


# ------------------------- 云端真实 CRD（云端 agent 每 5s 采集经 MQTT cloud/crds 推送，对应云端管理台 GET /api/devices） -------------------------

def cloud_crds(force: bool = False) -> Dict[str, Any]:
    """读取云端真实 DeviceModel / Device CRD（agent 采集推送缓存；force=True 时 HTTP 实时拉取）。

    对应云端管理台 GET /api/devices：返回模型列表（属性清单）+ 设备列表（twins 摘要）。
    云端不可达/未部署 CRD 时返回 ok=False + 具体错误（不返回仿真数据）。
    """
    return cloud_agent.crds(force=force)


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


# ------------------------- 盒子接入（onboard） -------------------------
def onboard_node(p: Dict[str, Any]) -> Dict[str, Any]:
    """盒子接入：SSH 从云端取真实共享 token（优先 1 年重签，见 §5.4）+ caHash，生成 edgecore.yaml + 部署命令（§5.5）。"""
    hostname = str(p.get("hostname", "edge-box")).strip() or "edge-box"
    cloud_ip = str(p.get("cloudIP", "")).strip()
    box_ip = str(p.get("boxIP", "")).strip()
    if not cloud_ip:
        return {"ok": False, "error": "cloudIP（云端 CloudCore 地址）不能为空"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", hostname):
        return {"ok": False, "error": f"盒子主机名不合法：{hostname}（仅允许字母/数字/点/短横线/下划线）"}
    cloud = _fetch_cloud_k8s(force=True)
    tok_data = cloud.get("token") or {}
    tok = (tok_data.get("value") or "").strip()
    if not tok:
        return {"ok": False,
                "error": f"无法从云端获取真实共享 token（{cloud.get('error') or tok_data.get('expires')}）。"
                         f"请先确认一键下发配置条中的云端 SSH 配置已保存且云端可达。"}
    token = tok
    # KubeEdge 共享 token 为四段式：caHash.header.payload.signature
    ca_hash = token.split(".")[0]
    tpl = EDGECORE_TEMPLATE.read_text("utf-8") if EDGECORE_TEMPLATE.exists() else ""
    edgecore_yaml = (
        tpl.replace("{{HOSTNAME}}", hostname)
        .replace("{{TOKEN}}", token)
        .replace("{{CLOUDIP}}", cloud_ip)
    )
    # box-deploy 采集部署包（本仓库 platform/box-deploy，含 mapper/mosquitto/wheels/deploy_box.sh）
    # 注意：盒子 IP 仅用于 ④ 部署阶段在盒子现场局域网内上传部署包（运行期平台无需盒子 IP——
    # 实际部署中盒子常处于现场内网、无直达 IP，数据由盒子主动上报到云端 Broker，与盒子有无 IP 无关）。
    box_deploy_src = str(Path(__file__).resolve().parents[2] / "platform" / "box-deploy")
    box_conn = f"root@{box_ip}" if box_ip else "root@<盒子IP>"
    cmds = [
        "# 架构：盒子仅安装 EdgeCore，不部署 k3s-server（边缘无本地 K8s 控制平面，控制平面全在云端 K3s + CloudCore）",
        "# 边缘运行时：edged 拉起 Pod + mosquitto（本地 MQTT）+ mapper（DMI 采集，云边协同断点续传）",
        "# 以下命令默认在盒子上执行；④ 的上传步骤在部署现场（盒子局域网内）执行，运行期平台不需要盒子 IP。",
        "",
        "# ═══ ① EdgeCore 基础接入（全新盒子首次：下载 edgecore 二进制 + 本地生成边缘证书 + systemd）═══",
        f"keadm join --cloudcore-ipport={cloud_ip}:10000 --token={token} --kubeedge-version=v1.20.0 --with-edge-core",
        "",
        "# ═══ ② 配置下发（从云端拉 rootCA.crt；边缘证书由 keadm 在盒子本地生成，不拷贝云端 certs）═══",
        "mkdir -p /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config",
        f"scp root@{cloud_ip}:/etc/kubeedge/ca/rootCA.crt /etc/kubeedge/ca/rootCA.crt",
        f"cat > /etc/kubeedge/config/edgecore.yaml << 'EOF'\n{edgecore_yaml}\nEOF",
        "systemctl daemon-reload && systemctl restart edgecore.service",
        f"ssh root@{cloud_ip} \"kubectl get nodes | grep -w {hostname}\"",
        "",
        "# ═══ ③ 云端创建设备（平台「能碳一体机管理 → 设备管理」一键下发；或命令行 kubectl apply，YAML 见 backend/config/kubeedge/）═══",
        f"#  ssh root@{cloud_ip} \"kubectl apply -f <deviceName>.yaml\"",
        "",
        "# ═══ ④ box-deploy 采集部署包（mapper 仪表采集 + mosquitto + 云边协同断点续传）═══",
        "# 4.1 【平台本机】上传部署包到盒子：",
        f"scp -r {box_deploy_src} {box_conn}:/opt/weight-bridge/box-deploy",
        "# 4.2 【盒子】一键部署（幂等，可重复执行；依赖优先离线 wheels/ 安装）：",
        f"ssh {box_conn} \"cd /opt/weight-bridge/box-deploy && ./deploy_box.sh\"",
        "# 4.3 【盒子】按现场定制 /opt/weight-bridge/config.json（改完 systemctl restart box-mapper 生效）：",
        "#     deviceName/property 与云端 Device 一致；serial.port 串口设备；modbus 寄存器按仪表手册；mqtt.boxId 建议用盒子主机名",
        f"ssh {box_conn} \"vi /opt/weight-bridge/config.json\"",
        "# 4.4 【盒子】链路自检（只读，验证 edgecore/dmi.sock/依赖/缓存目录）：",
        f"ssh {box_conn} \"cd /opt/weight-bridge/box-deploy && ./deploy_box.sh --check\"",
        "",
        "# ═══ ⑤ 触发路由 + 验证链路（云端）═══",
        f"ssh root@{cloud_ip} \"kubectl annotate device <deviceName> -n default sync=$(date +%s) --overwrite\"",
        f"ssh root@{cloud_ip} \"kubectl get device <deviceName> -o json | grep reported\"",
    ]
    return {
        "ok": True,
        "edgecore": edgecore_yaml,
        "token": token,
        "token_source": tok_data.get("source", "cloud"),
        "token_expires": tok_data.get("expires", ""),
        "caHash": ca_hash,
        "hostname": hostname,
        "cloudIP": cloud_ip,
        "boxIP": box_ip,
        "commands": cmds,
        "source": "cloud",   # token/caHash 均来自云端真实环境
    }


# ------------------------- 云端 Broker 配置（前端配置化） -------------------------
def get_config() -> Dict[str, Any]:
    """返回云端 Broker 配置（「能碳一体机管理」配置弹窗数据源，password 脱敏）。

    配置默认值来自参考项目 yunduan1（broker.yaml，TCP 41883 / WS 41083）。
    """
    return mqtt_source.get_config()


def update_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """保存云端 Broker 配置并热更新（前端配置化，运行时持久化到 box_config.json）。"""
    return mqtt_source.update_config(cfg)
