"""能碳一体机管理台后端（参照参考项目 yunduan1 的 console 管理台 + dashboard 实时仪表盘）。

将 yunduan1 的全部能力集成到「能碳一体机管理」视图：
1. 概览：云端 MQTT Broker 实时统计（$SYS，真实）+ cloudcore/节点/端口/证书/token 状态（仿真演示）；
2. 设备管理：DeviceModel/Device CRUD（Modbus/OPC-UA/Bluetooth 三协议 YAML 生成，本地 JSON 模拟集群）；
3. 盒子接入：edgecore.yaml 模板渲染 + 共享 token + caHash + 部署命令；
4. 实时数据：Device.status.twins 实时上报值（真实 MQTT 数据链路）+ 实时消息流 + 发测试消息；
5. 接入指引：数据链路说明（eKuiper 转发规则、盒子侧采集、部署包、诊断工具）。

架构一致性（与 yunduan1 相同）：管理台只做「配置」与「读取展示」，
传感器读数一律经 MQTT 链路获取（本平台不生成模拟读数）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import mqtt_source

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEVICES_FILE = CONFIG_DIR / "box_devices.json"
EDGECORE_TEMPLATE = CONFIG_DIR / "edgecore.template.yaml"

_LOCK = threading.Lock()
# 设备 twins 趋势历史：dev_id -> [(epoch, value)]
_TWIN_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
_TWIN_HISTORY_MAX = 120

# ------------------------- 三协议属性类型 / 寄存器类型（移植自 yunduan1 console） -------------------------
MODEL_TYPE = {
    "int": "int", "float": "float", "double": "double",
    "string": "string", "boolean": "boolean", "bool": "boolean",
}
REG_TYPE = {
    "holdingRegister": "holdingRegister", "inputRegister": "inputRegister",
    "coil": "coil", "discreteInput": "discreteInput",
}
ACCESS_MODE = {"r": "ReadOnly", "rw": "ReadWrite"}


def _load_devices() -> Dict[str, List[Dict[str, Any]]]:
    with _LOCK:
        if DEVICES_FILE.exists():
            try:
                return json.loads(DEVICES_FILE.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                pass
        return {"models": [], "devices": []}


def _save_devices(data: Dict[str, List[Dict[str, Any]]]) -> None:
    with _LOCK:
        DEVICES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ------------------------- 设备 YAML 生成（移植自 yunduan1 console/server.py） -------------------------
def _yaml_esc(v: Any) -> str:
    """安全转义用户输入为 YAML 标量（防特殊字符破坏模板结构）。"""
    s = str(v if v is not None else "")
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _prop_yaml(p: Dict[str, Any], protocol: str, collect_cycle: int = 1000) -> str:
    """渲染一个属性点的 DeviceModel properties 片段。"""
    ptype = MODEL_TYPE.get(str(p.get("type", "float")).lower(), "float")
    access = ACCESS_MODE.get(str(p.get("accessMode", "r")).lower(), "ReadOnly")
    lines = [
        f"        - name: {_yaml_esc(p.get('name', 'prop'))}",
        f"          description: {_yaml_esc(p.get('desc', ''))}",
        "          type: {",
        f"            {ptype}: {{}}",
        "          }",
        f"          accessMode: {access}",
    ]
    if protocol == "modbus":
        reg = REG_TYPE.get(str(p.get("registerType", "holdingRegister")), "holdingRegister")
        lines += [
            "          protocolCommonConfig: {",
            f"            collectCycle: {int(collect_cycle)}",
            "          }",
            f"          registerType: {reg}",
            f"          register: {int(p.get('register', 0))}",
            f"          limit: {p.get('limit', '')}",
            f"          scale: {p.get('scale', 1.0)}",
            f"          isSwap: {p.get('isSwap', False)}",
            f"          isRegisterSwap: {p.get('isRegisterSwap', False)}",
            f"          unit: {_yaml_esc(p.get('unit', ''))}",
        ]
    elif protocol == "opcua":
        lines += [
            f"          nodeID: \"{_yaml_esc(p.get('nodeID', ''))}\"",
            f"          unit: {_yaml_esc(p.get('unit', ''))}",
        ]
    elif protocol == "bluetooth":
        lines += [
            f"          characteristicUUID: \"{_yaml_esc(p.get('characteristicUUID', ''))}\"",
            f"          unit: {_yaml_esc(p.get('unit', ''))}",
        ]
    return "\n".join(lines)


def generate_device_yaml(p: Dict[str, Any]) -> Dict[str, str]:
    """生成 DeviceModel + Device 两份 YAML（与 yunduan1 console 一致）。

    支持协议: modbus / opcua / bluetooth
    """
    protocol = str(p.get("protocol", "modbus")).lower()
    model_name = _yaml_esc(p.get("modelName", "box-metric-model"))
    device_name = _yaml_esc(p.get("deviceName", "box-device"))
    namespace = _yaml_esc(p.get("namespace", "default"))
    node_name = _yaml_esc(p.get("nodeName", "edge-node"))
    collect_cycle = int(p.get("collectCycle", 1000))
    props: List[Dict[str, Any]] = p.get("properties", [])
    first_prop = _yaml_esc(props[0]["name"]) if props else "value"

    props_txt = "\n".join([_prop_yaml(x, protocol, collect_cycle) for x in props])

    model_yaml = f"""apiVersion: devices.kubeedge.io/v1alpha2
kind: DeviceModel
metadata:
  name: {model_name}
  namespace: {namespace}
spec:
  properties:
{props_txt}
"""

    if protocol == "modbus":
        comm = p.get("comm", {})
        comm_type = str(comm.get("commType", "serial")).lower()
        if comm_type == "tcp":
            protocol_cfg = f"""      modbus:
        tcp:
          ip: {comm.get('tcpIP', '192.168.1.10')}
          port: {int(comm.get('tcpPort', 502))}
"""
        else:
            protocol_cfg = f"""      modbus:
        rtu:
          serialPort: {comm.get('serialPort', '/dev/ttyS0')}
          baudRate: {int(comm.get('baudRate', 9600))}
          dataBits: {int(comm.get('dataBits', 8))}
          parity: {comm.get('parity', 'none')}
          stopBits: {int(comm.get('stopBits', 1))}
"""
        slave_id = comm.get("slaveID", 1)
        device_extra = f"""        slaveID: {int(slave_id)}
"""
    elif protocol == "opcua":
        opcua = p.get("opcua", {})
        protocol_cfg = f"""      opcua:
        url: {opcua.get('url', 'opc.tcp://127.0.0.1:4840')}
        userName: {opcua.get('userName', '')}
        password: {opcua.get('password', '')}
        securityMode: {opcua.get('securityMode', 'None')}
        securityPolicy: {opcua.get('securityPolicy', 'None')}
        certificate: {opcua.get('certificate', '')}
        privateKey: {opcua.get('privateKey', '')}
        remoteCertificate: {opcua.get('remoteCertificate', '')}
"""
        device_extra = ""
    else:  # bluetooth
        bt = p.get("bluetooth", {})
        protocol_cfg = f"""      bluetooth:
        macAddress: {bt.get('macAddress', 'AA:BB:CC:DD:EE:FF')}
"""
        device_extra = ""

    device_yaml = f"""apiVersion: devices.kubeedge.io/v1alpha2
kind: Device
metadata:
  name: {device_name}
  namespace: {namespace}
  labels:
    description: '{_yaml_esc(p.get('desc', ''))}'
spec:
  deviceModelRef:
    name: {model_name}
  nodeName: {node_name}
  protocol:
{protocol_cfg}{device_extra}  properties:
    - name: {first_prop}
      collectCycle: {collect_cycle}
      reportCycle: {collect_cycle}
  data:
    dataProperties:
      - propertyName: {first_prop}
        pushCycle: {collect_cycle}
        pullCycle: {collect_cycle}
"""
    return {"model": model_yaml, "device": device_yaml}


# ------------------------- 概览（cloudcore / 节点 / 端口 / 证书 / token） -------------------------
def box_overview() -> Dict[str, Any]:
    """管理台概览。

    真实部分：云端 MQTT Broker 统计（$SYS）、识别到的边缘盒子节点。
    演示部分：cloudcore 状态、CloudHub 端口监听、证书/token 有效期
    （本平台不运行真实 K3s 集群，这些字段为仿真演示数据，字段名与 yunduan1 console 保持一致）。
    """
    now = time.time()
    # 识别到的盒子（真实）：来自 MQTT 云端设备的分组
    boxes: Dict[str, Dict[str, Any]] = {}
    with mqtt_source._LOCK:  # noqa: SLF001
        for cid, info in mqtt_source.CLOUD_DEVICES.items():
            b = info.get("box") or "unknown-box"
            boxes.setdefault(b, {"box": b, "devices": 0, "last_seen": 0})
            boxes[b]["devices"] += 1
            boxes[b]["last_seen"] = max(boxes[b]["last_seen"], float(info.get("last_seen") or 0))

    edge_nodes = []
    for b, info in sorted(boxes.items()):
        last = info["last_seen"]
        edge_nodes.append({
            "name": b, "ready": last and (now - last) < 30,
            "roles": "edge", "version": "v1.12.2",
            "age": datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "未上报",
            "devices": info["devices"], "source": "mqtt" if last else "idle",
        })
    if not edge_nodes:
        edge_nodes.append({
            "name": "box-001", "ready": False, "roles": "edge", "version": "v1.12.2",
            "age": "未上报", "devices": 0, "source": "mqtt",
        })

    # 证书 / token 有效期（仿真演示，有效期基于当前时间生成）
    def _cert(end_days: int, cn: str) -> Dict[str, str]:
        exp = datetime.now() + timedelta(days=end_days)
        remain = max(0, end_days)
        return {
            "cn": cn, "expires": exp.strftime("%Y-%m-%d"),
            "remain_days": str(remain),
            "demo": True,
        }

    stats = mqtt_source.broker_stats()
    status = mqtt_source.get_status()
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "broker": {
            "host": status.get("broker_host"), "port": status.get("broker_port"),
            "connected": status.get("connected", False),
            "stats": stats,   # $SYS 真实统计
        },
        "cloudcore": {
            "name": "cloudcore-7d6f8b9c5-abcde", "phase": "Running",
            "restarts": 0, "node": "master-01", "podIP": "10.244.0.5",
            "demo": True,
        },
        "nodes": edge_nodes,
        "ports": [
            {"port": "10001", "proto": "UDP", "svc": "cloudhub", "listening": "no", "demo": True},
            {"port": "10002", "proto": "TCP", "svc": "cloudhub-grpc", "listening": "no", "demo": True},
            {"port": "10003", "proto": "TCP", "svc": "cloudhub-quic", "listening": "no", "demo": True},
            {"port": "10004", "proto": "TCP", "svc": "cloudhub-websocket", "listening": "no", "demo": True},
        ],
        "certs": [
            _cert(3650, "rootCA.crt"), _cert(730, "cloudcore.crt"), _cert(365, "stream.crt"),
        ],
        "token": {
            "expires": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
            "remain_days": "365", "demo": True,
        },
        "demo_note": "cloudcore/端口/证书/token 为仿真演示数据（本平台不运行真实 K3s 集群）；"
                     "Broker 统计与边缘节点来自真实 MQTT 链路。",
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


def list_devices() -> Dict[str, Any]:
    data = _load_devices()
    # 附加实时状态：优先按绑定云端设备(cloudDevice)匹配，其次按设备名（真实读数，未匹配显示未上报）
    with mqtt_source._LOCK:  # noqa: SLF001
        cloud = {k: dict(v) for k, v in mqtt_source.CLOUD_DEVICES.items()}
    devices = []
    for d in data.get("devices", []):
        cd = _match_cloud_device(d, cloud)
        d2 = dict(d)
        d2["cloud_matched"] = bool(cd)
        d2["last_seen"] = cd.get("last_seen") if cd else None
        d2["primary"] = cd.get("primary") if cd else None
        devices.append(d2)
    return {"models": data.get("models", []), "devices": devices, "cloud_devices": cloud}


def create_device(p: Dict[str, Any]) -> Dict[str, Any]:
    """创建设备/模型。mode=dryRun 仅返回 YAML 预览；mode=apply 保存到模拟集群（本地 JSON）。"""
    mode = p.get("mode", "apply")
    yamls = generate_device_yaml(p)
    if mode == "dryRun":
        return {"ok": True, "mode": "dryRun", "yamls": yamls}

    data = _load_devices()
    # 模型去重
    models = data.get("models", [])
    model_names = [m.get("name") for m in models]
    if p.get("modelName") not in model_names:
        models.append({
            "name": p.get("modelName"), "namespace": p.get("namespace", "default"),
            "protocol": p.get("protocol", "modbus"),
            "properties": p.get("properties", []),
            "yaml": yamls["model"], "created_at": int(time.time()),
        })
    data["models"] = models
    # 设备
    devices = data.get("devices", [])
    dev = {
        "name": p.get("deviceName"), "namespace": p.get("namespace", "default"),
        "model": p.get("modelName"), "node": p.get("nodeName", "edge-node"),
        "protocol": p.get("protocol", "modbus"),
        "collectCycle": int(p.get("collectCycle", 1000)),
        "cloudDevice": (p.get("cloudDevice") or "").strip(),   # 可选：绑定云端识别设备 id（实时匹配优先）
        "properties": p.get("properties", []),
        "yaml": yamls["device"], "created_at": int(time.time()),
        "status": "reporting",
    }
    devices = [x for x in devices if x.get("name") != dev["name"]]
    devices.append(dev)
    data["devices"] = devices
    _save_devices(data)
    return {"ok": True, "mode": "apply", "yamls": yamls, "device": dev}


def delete_device(kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
    """删除设备（kind=device 删除 Device；kind=model 删除 DeviceModel，同时移除引用它的设备）。"""
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
    return {"ok": True, "removed": removed}


# ------------------------- 实时数据（twins + 趋势） -------------------------
def realtime_devices() -> Dict[str, Any]:
    """逐设备返回 Device.status.twins 实时上报值（读数一律来自 MQTT 链路）+ 趋势历史。"""
    with mqtt_source._LOCK:  # noqa: SLF001
        cloud = {k: dict(v) for k, v in mqtt_source.CLOUD_DEVICES.items()}
    data = _load_devices()
    now = time.time()
    out = []
    for d in data.get("devices", []):
        name = d.get("name")
        cd = _match_cloud_device(d, cloud)
        fields = (cd.get("fields") or {}) if cd else {}
        twins = []
        for prop in d.get("properties", []):
            pname = prop.get("name")
            val = fields.get(pname)
            if val is None and cd:
                val = fields.get(prop.get("mapping") or "")
            twins.append({
                "propertyName": pname,
                "reported": val,
                "observedDesired": None,
                "timestamp": cd.get("last_seen") if cd else None,
                "unit": prop.get("unit", ""),
            })
            # 趋势历史
            if val is not None:
                key = f"{name}::{pname}"
                hist = _TWIN_HISTORY.setdefault(key, [])
                hist.append({"t": now, "v": val})
                if len(hist) > _TWIN_HISTORY_MAX:
                    del hist[: len(hist) - _TWIN_HISTORY_MAX]
        out.append({
            "name": name, "model": d.get("model"), "node": d.get("node"),
            "state": "reporting" if cd else "pending",
            "lastOnlineTime": cd.get("last_seen") if cd else None,
            "twins": twins,
            "history": {t["propertyName"]: _TWIN_HISTORY.get(f"{name}::{t['propertyName']}", [])
                        for t in twins},
        })
    return {"devices": out, "time": now}


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
def _demo_token() -> str:
    """生成仿真演示用的共享 token（四段式，与真实 cloudcore 签发的格式一致）。

    真实环境由云端 cloudcore 用 CA 签发，本平台为仿真演示生成。
    """
    ca_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    header = hmac.new(secrets.token_bytes(16), b"header", hashlib.sha256).hexdigest()
    payload = hmac.new(secrets.token_bytes(16), b"payload", hashlib.sha256).hexdigest()
    signature = hmac.new(secrets.token_bytes(16), b"signature", hashlib.sha256).hexdigest()
    return f"{ca_hash}.{header}.{payload}.{signature}"


def onboard_node(p: Dict[str, Any]) -> Dict[str, Any]:
    """盒子接入：生成 edgecore.yaml（模板渲染）+ 共享 token + caHash + 部署命令。"""
    hostname = str(p.get("hostname", "edge-box")).strip() or "edge-box"
    cloud_ip = str(p.get("cloudIP", "")).strip()
    box_ip = str(p.get("boxIP", "")).strip()
    if not cloud_ip:
        return {"ok": False, "error": "cloudIP（云端 CloudCore 地址）不能为空"}
    token = _demo_token()
    ca_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    tpl = EDGECORE_TEMPLATE.read_text("utf-8") if EDGECORE_TEMPLATE.exists() else ""
    edgecore_yaml = (
        tpl.replace("{{HOSTNAME}}", hostname)
        .replace("{{TOKEN}}", token)
        .replace("{{CLOUDIP}}", cloud_ip)
    )
    cmds = [
        "mkdir -p /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config",
        f"scp -r root@{cloud_ip}:/etc/kubeedge/ca/* /etc/kubeedge/ca/ && scp -r root@{cloud_ip}:/etc/kubeedge/certs/* /etc/kubeedge/certs/",
        f"cat > /etc/kubeedge/config/edgecore.yaml << 'EOF'\n{edgecore_yaml}\nEOF",
        "systemctl restart edgecore && systemctl status edgecore",
    ]
    return {
        "ok": True,
        "edgecore": edgecore_yaml,
        "token": token,
        "caHash": ca_hash,
        "hostname": hostname,
        "cloudIP": cloud_ip,
        "boxIP": box_ip,
        "commands": cmds,
        "demo_note": "token/caHash 为仿真演示生成；真实环境由云端 cloudcore 与 CA 签发，部署命令可直接复用。",
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
