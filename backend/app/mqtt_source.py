"""MQTT 实时数据获取模块（边缘 box-mapper 实时发布 + 云边断连补传）。

数据链路：
  边缘盒子（能碳一体机）box-mapper（Modbus/OPC-UA 仪表采集）→ 云端自建 MQTT Broker（broker.yaml 配置）
  → 本模块作为订阅端连接 Broker，按主题获取真实设备数据。

实现参照 deploy_pkg/collect_sensor_data.py：
- paho-mqtt，默认 MQTT 5.0（amqtt 0.12 对 MQTT 3.1.1 跨客户端路由有缺陷）；
- 默认订阅 '#'（amqtt 对 'data/#' 前缀通配符路由有缺陷），on_message 过滤 $SYS；
- 唯一 client_id（含 pid），断线自动重连（1s→30s 退避）。

本模块不生成任何模拟读数，且读数同步采用「关联制」：
- 收到消息后解析 JSON payload，识别「云端设备」（能碳一体机盒子下的设备，
  优先取 payload 的 device/deviceId/... 字段，否则按 data/<box>/<device> 主题推断），
  把其数值字段缓存为 CLOUD_DEVICES（含主读数 primary）；
- 云端设备必须与「仿真系统中的设备实例」（如 blast_furnace::belt_scale_0）手动关联，
  关联关系保存在 config/links.json（也可用前端「配置 Broker」弹窗中的静态映射 mapping 预置）；
- 实时遥测（realtime.py）按设备实例 id 经关联表反查云端设备取真实读数；
  未关联的设备一律不返回读数（不同步），直到用户在「能碳一体机管理」视图手动关联。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# paho-mqtt 为可选依赖（pip install paho-mqtt）；未安装时降级为空实现，不影响平台启动
try:
    import paho.mqtt.client as mqtt
    _PAHO_OK = True
except Exception:  # pragma: no cover
    mqtt = None  # type: ignore[assignment]
    _PAHO_OK = False

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "mqtt.yaml")          # 旧版手工配置文件（向后兼容）
RUNTIME_CONFIG_PATH = os.path.join(CONFIG_DIR, "box_config.json")  # 前端配置持久化（运行时产物，无需手工编辑）
LINKS_FILE = os.path.join(CONFIG_DIR, "links.json")   # 云端设备 <-> 仿真设备实例关联持久化
BOX_DEVICES_FILE = os.path.join(CONFIG_DIR, "box_devices.json")  # 盒子设备配置（cloudDevice/name 反查用）

from . import cloud_agent  # noqa: E402 云端 agent 推送（cloud/# 主题）解析，替代 SSH 数据通道

# ------------------------- 配置加载（环境变量优先，回退 mqtt.yaml） -------------------------
DEFAULT_CFG: Dict[str, Any] = {
    "broker": {
        "host": "127.0.0.1",
        "port": 41883,
        "username": "",
        "password": "",
        "client_id": "carbon-sim-collector",
        "keepalive": 60,
        "qos": 0,
    },
    "topics": ["#"],
    "mapping": {},
}


def _load_config() -> Dict[str, Any]:
    """配置来源优先级（高→低）：环境变量 > 前端运行时配置(box_config.json) > mqtt.yaml > 默认值。

    box_config.json 由「能碳一体机管理」视图保存生成（运行时产物，无需手工编辑），
    优先级高于旧版手工配置文件 mqtt.yaml（保留向后兼容）；环境变量仍可覆盖（与 collect_sensor_data.py 一致）。
    """
    cfg = json.loads(json.dumps(DEFAULT_CFG))  # 深拷贝默认值
    try:
        import yaml  # type: ignore

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        for key in ("broker", "topics", "mapping", "ignored_devices"):
            if key in loaded:
                cfg[key] = loaded[key]
    except Exception:
        pass  # 配置缺失/损坏时使用默认值（与参考项目环境变量默认一致）
    try:
        with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f) or {}
        for key in ("broker", "topics", "mapping", "ignored_devices"):
            if key in saved:
                cfg[key] = saved[key]
    except Exception:
        pass
    # 环境变量优先级最高（与 collect_sensor_data.py 一致）
    host = os.environ.get("BROKER_HOST")
    if host:
        cfg["broker"]["host"] = host
    port = os.environ.get("BROKER_PORT")
    if port:
        try:
            cfg["broker"]["port"] = int(port)
        except ValueError:
            pass
    topics = os.environ.get("MQTT_TOPICS")
    if topics:
        cfg["topics"] = [t.strip() for t in topics.split(",") if t.strip()]
    return cfg


_config = _load_config()
_BROKER = _config["broker"]
_TOPICS = _config["topics"] or ["#"]
_MAPPING: Dict[str, str] = _config.get("mapping") or {}   # mqtt 字段 -> 平台设备 id
_REV_MAPPING: Dict[str, str] = {v: k for k, v in _MAPPING.items()}  # 设备 id -> mqtt 字段

# ------------------------- 运行时状态 -------------------------
_LOCK = threading.Lock()
READINGS: Dict[str, Dict[str, float]] = {}      # field -> {"t": epoch, "v": value}
CLOUD_DEVICES: Dict[str, Dict[str, Any]] = {}   # cloud_id -> {"id","box","topic","last_seen","fields","primary"}
# 云边协同：边缘盒子断点续传的历史点（带真实采集时间戳），cloud_id -> field -> [(t, v)]
# 消息 payload 带 ts（epoch 秒/毫秒）时记录，供平台折线图 history 回填断连缺口
REPLAY_HISTORY: Dict[str, Dict[str, List[tuple]]] = {}
REPLAY_HISTORY_MAX = 200000
MESSAGE_LOG: List[Dict[str, Any]] = []          # 最近原始消息（状态面板展示）
MESSAGE_LOG_MAX = 200
# 缓存清理：设备超过该秒数未上报视为下线，清理 CLOUD_DEVICES/READINGS/REPLAY_HISTORY 残留（防内存泄漏）
GC_TTL = 3600
_GC_MIN_INTERVAL = 60
_last_gc_ts = 0.0
BROKER_STATS: Dict[str, Any] = {                # 来自 $SYS/broker/#（实时仪表盘统计，参照 dashboard.py）
    "clients_connected": 0,
    "clients_max": 0,
    "broker_recv": 0,
    "broker_sent": 0,
    "subscriptions": 0,
    "uptime": 0,
    "version": "?",
    "panel_recv": 0,
}
_STATE: Dict[str, Any] = {
    "enabled": False,      # 是否已启用（成功启动连接流程）
    "connected": False,    # 当前是否已连接
    "last_connect_rc": None,
    "last_error": "",
    "last_message_at": None,
    "message_count": 0,
    "client_id": _BROKER.get("client_id", ""),
}

# 关联表：云端设备(cloud_id) <-> 仿真系统设备实例(local_device_id)
# 持久化到 config/links.json；前端「配置 Broker」弹窗中的静态映射 mapping 作为 seed（字段名视为云端设备）
_LINKS: Dict[str, str] = {}      # cloud_id -> local_device_id
_LINKS_REV: Dict[str, str] = {}  # local_device_id -> cloud_id
_LINKS_FACTOR: Dict[str, float] = {}  # cloud_id -> 读数换算系数（传感器原始单位 -> 流程设备单位，如 t/h）

# 云端设备标识字段（payload 优先）与盒子标识字段
_DEVICE_ID_KEYS = ("device", "deviceId", "dev_id", "devid", "device_id",
                   "id", "name", "sensor", "meter", "meterId", "meter_id")
_BOX_KEYS = ("box", "boxId", "box_id", "gateway", "gatewayId", "gateway_id",
             "deviceGroup", "device_group", "node", "nodeId")
_PRIMARY_KEYS = ("weight", "value", "v", "val", "reading", "measure", "measured", "pv", "data")
# KubeEdge Device twins 上报主题（data/<box>/<device>/<instance>/<property>）中的主读数属性名；
# 附属寄存器（writeProtect/zeroReference/...）的消息不得覆盖主读数
_MAIN_PROPS = frozenset(("weight", "value", "pv", "v", "val", "reading", "measure", "measured", "data",
                         "flow", "pressure", "temperature", "power", "level", "current", "voltage", "rate"))

# Modbus 称重仪表常见的「无有效读数」标志码（0xFFFE / 0xFFFF 等）。
# 命中这些值视为传感器无有效信号（前端显示"无有效数据"，不向仿真设备同步真实读数）。
_INVALID_READING_VALUES = frozenset((-65534.0, 65534.0, -65535.0, 65535.0,
                                     -32768.0, 32767.0, -32767.0))


def _is_invalid_reading(v: Any) -> bool:
    """判断是否为仪表无效读数标志码（如称重仪表传感器异常时输出 0xFFFE=-65534）。"""
    if isinstance(v, bool) or v is None:
        return False
    try:
        return float(v) in _INVALID_READING_VALUES
    except (TypeError, ValueError):
        return False


# 需要忽略的云端设备（重复链路/废弃设备，仍发布 MQTT 但不再识别为云端设备）。
# 持久化在 config/box_config.json 的 ignored_devices 字段，可在 update_config 中维护。
_IGNORED_DEVICES: set = set(_config.get("ignored_devices") or [])


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


# ------------------------- 关联表持久化（config/links.json） -------------------------

def _load_links() -> None:
    global _LINKS, _LINKS_REV, _LINKS_FACTOR
    links: Dict[str, str] = {}
    factors: Dict[str, float] = {}
    for field, dev in _MAPPING.items():          # 前端配置的静态映射作为 seed
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
    _LINKS = links
    _LINKS_REV = {l: c for c, l in links.items()}
    _LINKS_FACTOR = factors


def _save_links() -> None:
    try:
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump({"links": _LINKS, "factors": _LINKS_FACTOR}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_link(cloud_id: str, local_id: str, factor: float = 1.0) -> None:
    """建立/更新关联：云端设备 <-> 仿真设备实例（一对一，同一本地设备只能关联一个云端设备）。

    factor: 读数换算系数，云端上报原始读数 × factor = 同步到仿真设备的读数
            （如传感器原始单位为 kg/min，流程设备为 t/h，则 factor=0.06）。"""
    global _LINKS_REV, _LINKS_FACTOR
    cloud_id = (cloud_id or "").strip()
    local_id = (local_id or "").strip()
    if not cloud_id or not local_id:
        raise ValueError("cloud_id 与 local_id 不能为空")
    try:
        factor = float(factor)
    except (TypeError, ValueError):
        factor = 1.0
    with _LOCK:
        for c, l in list(_LINKS.items()):         # 同一本地设备解除旧关联
            if l == local_id and c != cloud_id:
                del _LINKS[c]
                _LINKS_FACTOR.pop(c, None)
        _LINKS[cloud_id] = local_id
        _LINKS_FACTOR[cloud_id] = factor
        _LINKS_REV = {l: c for c, l in _LINKS.items()}
        _save_links()


def remove_link(cloud_id: str) -> None:
    """解除关联：云端设备不再同步任何本地设备。"""
    global _LINKS_REV, _LINKS_FACTOR
    cloud_id = (cloud_id or "").strip()
    with _LOCK:
        _LINKS.pop(cloud_id, None)
        _LINKS_FACTOR.pop(cloud_id, None)
        _LINKS_REV = {l: c for c, l in _LINKS.items()}
        _save_links()


def get_links() -> Dict[str, Any]:
    """关联列表 + 云端识别设备（供前端连接面板渲染关联 UI）。"""
    with _LOCK:
        links = [{"cloud_id": c, "local_id": l, "factor": _LINKS_FACTOR.get(c, 1.0)} for c, l in _LINKS.items()]
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


_load_links()


# 盒子侧状态缓存：box -> 运行服务列表/最近部署结果（盒子卡片展示用）
BOX_SERVICES: Dict[str, Dict[str, Any]] = {}      # box -> {"services": [...], "last_seen": ts}
BOX_APP_EVENTS: Dict[str, List[Dict[str, Any]]] = {}  # box -> 最近部署/启停命令执行结果（最多 20 条）


def _record_box_state(topic: str, data: Dict[str, Any]) -> None:
    """解析盒子 state/# 上报：state/{box}/services（运行服务列表）与 state/{box}/deploy（命令结果）。"""
    box = str(data.get("box") or "").strip()
    if not box:
        parts = [p for p in topic.split("/") if p]
        box = parts[1] if len(parts) > 1 else "未分组"
    now = time.time()
    with _LOCK:
        if topic.endswith("/services"):
            services = data.get("services")
            if isinstance(services, list):
                # 归一化：确保每项有 name 字段，缺省补空串（前端容错）
                norm = []
                for s in services:
                    if isinstance(s, dict):
                        item = dict(s)
                        item.setdefault("name", "")
                        norm.append(item)
                    elif isinstance(s, str):
                        norm.append({"name": s})
                BOX_SERVICES[box] = {"services": norm, "last_seen": now}
        elif topic.endswith("/deploy"):
            ev = {
                "request_id": str(data.get("request_id") or ""),
                "cmd": str(data.get("cmd") or ""),
                "name": str(data.get("name") or ""),
                "ok": bool(data.get("ok")),
                "message": str(data.get("message") or ""),
                "detail": data.get("detail"),
                "ts": now,
            }
            BOX_APP_EVENTS.setdefault(box, []).append(ev)
            if len(BOX_APP_EVENTS[box]) > 20:
                del BOX_APP_EVENTS[box][:-20]


def box_services(box: str) -> List[Dict[str, Any]]:
    """查询盒子当前运行的服务/模型列表（无上报返回空列表）。"""
    with _LOCK:
        info = BOX_SERVICES.get(box or "")
        return list((info or {}).get("services") or [])


def box_app_events(box: str) -> List[Dict[str, Any]]:
    """查询盒子最近的应用部署/启停命令结果。"""
    with _LOCK:
        return list(BOX_APP_EVENTS.get(box or "") or [])


def publish_box_cmd(box: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """向盒子下发应用部署/启停指令（MQTT 命令主题 cmd/{box}/deploy）。

    盒子运行期无直达 IP，云端→盒子方向只能经云端 Broker 的 cmd/# 命令主题：
    盒子 mapper 订阅 cmd/{box}/#，收到后执行部署并回报 state/{box}/deploy。
    """
    topic = "cmd/%s/deploy" % (box or "").strip()
    body = dict(payload or {})
    body.setdefault("box", (box or "").strip())
    res = publish(topic, body)
    if res.get("ok"):
        res["topic"] = topic
    return res


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


def _record_message(msg) -> None:
    """解析一条 MQTT 消息：更新 READINGS（数值字段）、$SYS 统计并记入消息日志。"""
    topic = getattr(msg, "topic", "")
    try:
        payload = msg.payload.decode("utf-8", "replace")
    except Exception:
        payload = repr(getattr(msg, "payload", b""))

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
    if cloud_id and cloud_id in _IGNORED_DEVICES:
        with _LOCK:
            CLOUD_DEVICES.pop(cloud_id, None)
            READINGS.pop(cloud_id, None)
        return
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
    global _last_gc_ts
    now = time.time() if now is None else now
    if now - _last_gc_ts < _GC_MIN_INTERVAL:
        return
    _last_gc_ts = now
    stale = [cid for cid, info in CLOUD_DEVICES.items()
             if now - float(info.get("last_seen") or 0) > GC_TTL]
    for cid in stale:
        CLOUD_DEVICES.pop(cid, None)
        READINGS.pop(cid, None)
        REPLAY_HISTORY.pop(cid, None)
        # fields 前缀字段（如 "weight" / "box.weight"）也一并清理，避免 READINGS 无限增长
        for k in [k for k in READINGS if k in cid or cid in k]:
            READINGS.pop(k, None)


# ------------------------- 对外查询接口 -------------------------

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
        crds = cloud_agent.crds()
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
        cloud_id = _LINKS_REV.get(device_id)
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
        factor = _LINKS_FACTOR.get(cloud_id, 1.0)
        try:
            return float(v) * factor
        except (TypeError, ValueError):
            return None
    return None


def broker_stats() -> Dict[str, Any]:
    """Broker 实时统计（来自 $SYS/broker/#，实时仪表盘数据源）。"""
    with _LOCK:
        return dict(BROKER_STATS)


def publish(topic: str, payload: Any) -> Dict[str, Any]:
    """向云端 Broker 发一条测试消息（参照 dashboard.py 的 /api/publish）。

    使用独立短连接客户端发布，不影响主订阅线程。
    等待连接就绪后再发布，并校验 publish 返回值，避免「假成功」（消息未发出却返回 ok）。
    """
    if not _PAHO_OK:
        return {"ok": False, "error": "未安装 paho-mqtt：pip install paho-mqtt"}
    pc = None
    try:
        # 独立唯一 client_id：与订阅线程区分，避免相同 client_id 将订阅线程踢下线（MQTT 协议约定）
        _cid = f"{_BROKER.get('client_id', 'carbon-sim-collector')}-pub-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        try:
            pc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=_cid, clean_session=True)
        except TypeError:
            pc = mqtt.Client(client_id=_cid, clean_session=True)
        username = _BROKER.get("username", "")
        password = _BROKER.get("password", "")
        if username:
            pc.username_pw_set(username, password or None)

        connected = threading.Event()
        published = threading.Event()
        pub_rc = {"rc": -1}

        def _on_connect(client, userdata, flags, *args):
            connected.set()

        def _on_publish(client, userdata, mid, *args):
            pub_rc["rc"] = 0
            published.set()

        pc.on_connect = _on_connect
        pc.on_publish = _on_publish

        pc.connect(_BROKER.get("host", "127.0.0.1"), int(_BROKER.get("port", 41883)), 60)
        pc.loop_start()
        if not connected.wait(timeout=5):
            return {"ok": False, "error": "连接云端 Broker 超时（5s）"}
        info = pc.publish(topic,
                          payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                          qos=int(_BROKER.get("qos", 0)))
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return {"ok": False, "error": f"发布失败 rc={info.rc}"}
        published.wait(timeout=5)  # 等 on_publish 确认真正发出（qos0 发送后立即回调）
        return {"ok": True, "topic": topic}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        if pc is not None:
            try:
                pc.loop_stop()
                pc.disconnect()
            except Exception:  # noqa: BLE001
                pass


def get_status() -> Dict[str, Any]:
    with _LOCK:
        st = dict(_STATE)
        st["readings_count"] = len(READINGS)
        st["recent_messages"] = list(MESSAGE_LOG[-20:])
        st["topics"] = list(_TOPICS)
        st["broker_host"] = _BROKER.get("host")
        st["broker_port"] = _BROKER.get("port")
        st["mapping"] = dict(_MAPPING)
        st["broker_stats"] = dict(BROKER_STATS)
        st["cloud_devices"] = [
            {
                "id": c,
                "box": d.get("box"),
                "topic": d.get("topic"),
                "last_seen": d.get("last_seen"),
                "primary": d.get("primary"),
                "fields": list(d.get("fields") or {}),
            }
            for c, d in sorted(CLOUD_DEVICES.items(), key=lambda kv: kv[1].get("last_seen") or 0, reverse=True)
        ]
        st["links"] = [{"cloud_id": c, "local_id": l} for c, l in _LINKS.items()]
        st["ignored_devices"] = sorted(_IGNORED_DEVICES)
    return st


# ------------------------- 前端配置化（能碳一体机管理 -> 云端数据链路配置） -------------------------

def get_config() -> Dict[str, Any]:
    """返回当前云端 Broker 配置（前端配置弹窗数据源，password 脱敏）。

    前端「能碳一体机管理」总览 -> 云端数据链路卡片「配置」按钮调用，保存后走 update_config。
    """
    with _LOCK:
        broker = dict(_BROKER)
        broker["password"] = "******" if broker.get("password") else ""
        return {
            "broker": broker,
            "topics": list(_TOPICS),
            "mapping": dict(_MAPPING),
            "ignored_devices": sorted(_IGNORED_DEVICES),
            "runtime_file": os.path.basename(RUNTIME_CONFIG_PATH),
        }


def _save_runtime_config() -> None:
    """把当前配置持久化到 config/box_config.json（运行时产物，重启后自动恢复）。"""
    try:
        cfg = {"broker": dict(_BROKER), "topics": list(_TOPICS), "mapping": dict(_MAPPING),
               "ignored_devices": sorted(_IGNORED_DEVICES)}
        with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def update_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """保存云端 Broker 配置并热更新（前端配置化）。

    - 校验并更新运行时全局配置，持久化到 box_config.json（无需手工编辑配置文件）；
    - 用新 mapping 重建静态关联 seed（links.json 中的运行时关联优先）；
    - 断开当前订阅连接，立即按新配置重启订阅线程。
    """
    global _BROKER, _TOPICS, _MAPPING, _REV_MAPPING, _IGNORED_DEVICES
    broker = dict(_BROKER)
    b = cfg.get("broker") or {}
    if isinstance(b, dict):
        for k in ("host", "port", "username", "password", "client_id", "keepalive", "qos"):
            if k in b:
                broker[k] = b[k]
    host = str(broker.get("host", "127.0.0.1")).strip()
    if not host:
        return {"ok": False, "error": "Broker 地址不能为空"}
    try:
        port = int(broker.get("port", 41883))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Broker 端口必须为数字"}
    if not 1 <= port <= 65535:
        return {"ok": False, "error": "Broker 端口范围应为 1–65535"}
    broker["host"], broker["port"] = host, port
    if broker.get("password") in ("******", "*****", "****"):   # 脱敏占位 -> 保留原密码
        broker["password"] = _BROKER.get("password", "")
    topics = cfg.get("topics") if isinstance(cfg.get("topics"), list) else _TOPICS
    topics = [str(t).strip() for t in topics if str(t).strip()] or ["#"]
    mapping = cfg.get("mapping") if isinstance(cfg.get("mapping"), dict) else dict(_MAPPING)
    ignored = cfg.get("ignored_devices")
    if isinstance(ignored, list):
        ignored_set = {str(i).strip() for i in ignored if str(i).strip()}
    else:
        ignored_set = set(_IGNORED_DEVICES)
    with _LOCK:
        _BROKER, _TOPICS, _MAPPING = broker, topics, dict(mapping)
        _REV_MAPPING = {v: k for k, v in _MAPPING.items()}
        # 更新忽略设备集合，并清除其历史缓存（不再识别/同步）
        _IGNORED_DEVICES = ignored_set
        for cid in list(_IGNORED_DEVICES):
            CLOUD_DEVICES.pop(cid, None)
            READINGS.pop(cid, None)
        _STATE["client_id"] = broker.get("client_id", "")
        _STATE["connected"] = False
        _STATE["last_error"] = "配置已更新，正在按新配置重连..."
        _save_runtime_config()
        _load_links()          # 用新 mapping 重建静态关联 seed（links.json 运行时关联优先）
    _restart_subscriber()
    return {
        "ok": True,
        "broker": {**broker, "password": "******" if broker.get("password") else ""},
        "topics": topics,
        "mapping": dict(_MAPPING),
        "note": "配置已保存并热更新（持久化到 box_config.json，无需手工编辑配置文件）",
    }


# ------------------------- 订阅端实现（参照 collect_sensor_data.py） -------------------------

_CLIENT = None  # 当前订阅客户端引用（供配置热更新时断开重连）


def _restart_subscriber() -> None:
    """断开当前订阅客户端，按最新配置重启（Broker 配置热更新）。"""
    global _CLIENT
    with _LOCK:
        client = _CLIENT
        _CLIENT = None
    if client is not None:
        try:
            client.disconnect()
        except Exception:
            pass
    start()

def _make_client():
    cid = f"{_BROKER.get('client_id', 'carbon-sim-collector')}-{os.getpid()}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=True)
    except TypeError:
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        except TypeError:
            return mqtt.Client(client_id=cid)


def _on_connect(client, userdata, flags, reason_code, *args):
    if isinstance(reason_code, int):
        rc = reason_code
    else:
        rc = reason_code.value if hasattr(reason_code, "value") else reason_code
    with _LOCK:
        _STATE["connected"] = rc == 0
        _STATE["last_connect_rc"] = rc
        _STATE["last_error"] = "" if rc == 0 else f"连接失败 rc={rc}"
    print(f"[mqtt_source] connect rc={rc} broker={_BROKER.get('host')}:{_BROKER.get('port')}", flush=True)
    if rc == 0:
        for t in _TOPICS:
            client.subscribe(t, qos=int(_BROKER.get("qos", 0)))
            print(f"[mqtt_source] subscribe {t}", flush=True)
        # 额外订阅 $SYS/# 收集 Broker 统计（实时仪表盘数据源，参照 dashboard.py）
        client.subscribe("$SYS/#", qos=0)
        print("[mqtt_source] subscribe $SYS/#", flush=True)


def _on_disconnect(client, userdata, flags, reason_code, *args):
    with _LOCK:
        _STATE["connected"] = False
        _STATE["last_error"] = f"连接断开 rc={reason_code}"
    print(f"[mqtt_source] disconnect rc={reason_code}（将自动重连）", flush=True)


def _on_message(client, userdata, msg):
    _record_message(msg)


def start() -> None:
    """后台线程启动 MQTT 订阅（main.py 启动时调用一次）。"""
    if not _PAHO_OK:
        _STATE["last_error"] = "未安装 paho-mqtt：pip install paho-mqtt"
        print(f"[mqtt_source] {_STATE['last_error']}", flush=True)
        return

    def _run():
        global _CLIENT
        with _LOCK:
            _STATE["enabled"] = True
        client = _make_client()
        with _LOCK:
            _CLIENT = client   # 供配置热更新（update_config）断开重连
        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        username = _BROKER.get("username", "")
        password = _BROKER.get("password", "")
        if username:
            client.username_pw_set(username, password or None)
        while True:
            try:
                client.connect(_BROKER.get("host", "127.0.0.1"),
                               int(_BROKER.get("port", 41883)),
                               keepalive=int(_BROKER.get("keepalive", 60)))
                break
            except Exception as e:
                with _LOCK:
                    _STATE["last_error"] = f"连接失败：{e}"
                print(f"[mqtt_source] retry connect -> {e}", flush=True)
                time.sleep(5)
        print(f"[mqtt_source] running topics={_TOPICS}", flush=True)
        try:
            client.loop_forever()
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                _STATE["last_error"] = f"订阅异常：{e}"
            print(f"[mqtt_source] loop error -> {e}", flush=True)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="mqtt-source").start()
