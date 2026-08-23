"""MQTT 实时数据获取模块（参照参考项目 yunduan1 的数据获取方式）。

数据链路（与参考项目一致）：
  边缘盒子（能碳一体机，eKuiper 采集 Modbus 传感器）→ 云端自建 MQTT Broker（broker.yaml 配置）
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
        for key in ("broker", "topics", "mapping"):
            if key in loaded:
                cfg[key] = loaded[key]
    except Exception:
        pass  # 配置缺失/损坏时使用默认值（与参考项目环境变量默认一致）
    try:
        with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f) or {}
        for key in ("broker", "topics", "mapping"):
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
MESSAGE_LOG: List[Dict[str, Any]] = []          # 最近原始消息（状态面板展示）
MESSAGE_LOG_MAX = 200
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

# 云端设备标识字段（payload 优先）与盒子标识字段
_DEVICE_ID_KEYS = ("device", "deviceId", "dev_id", "devid", "device_id",
                   "id", "name", "sensor", "meter", "meterId", "meter_id")
_BOX_KEYS = ("box", "boxId", "box_id", "gateway", "gatewayId", "gateway_id",
             "deviceGroup", "device_group", "node", "nodeId")
_PRIMARY_KEYS = ("value", "v", "val", "reading", "measure", "measured", "pv", "data")


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
    if not dev:
        parts = [p for p in topic.split("/") if p]
        if parts and parts[0] == "data":
            rest = parts[1:]
            if len(rest) >= 2:
                box = rest[0]
                dev = rest[1]
            elif len(rest) == 1:
                dev = rest[0]
    if not dev:
        dev = topic
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
    global _LINKS, _LINKS_REV
    links: Dict[str, str] = {}
    for field, dev in _MAPPING.items():          # 前端配置的静态映射作为 seed
        if field and dev:
            links[field] = dev
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f) or {}
        for c, l in (saved.get("links") or {}).items():   # 运行时关联覆盖/补充
            if c and l:
                links[c] = l
    except Exception:
        pass
    _LINKS = links
    _LINKS_REV = {l: c for c, l in links.items()}


def _save_links() -> None:
    try:
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump({"links": _LINKS}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_link(cloud_id: str, local_id: str) -> None:
    """建立/更新关联：云端设备 <-> 仿真设备实例（一对一，同一本地设备只能关联一个云端设备）。"""
    global _LINKS_REV
    cloud_id = (cloud_id or "").strip()
    local_id = (local_id or "").strip()
    if not cloud_id or not local_id:
        raise ValueError("cloud_id 与 local_id 不能为空")
    with _LOCK:
        for c, l in list(_LINKS.items()):         # 同一本地设备解除旧关联
            if l == local_id and c != cloud_id:
                del _LINKS[c]
        _LINKS[cloud_id] = local_id
        _LINKS_REV = {l: c for c, l in _LINKS.items()}
        _save_links()


def remove_link(cloud_id: str) -> None:
    """解除关联：云端设备不再同步任何本地设备。"""
    global _LINKS_REV
    cloud_id = (cloud_id or "").strip()
    with _LOCK:
        _LINKS.pop(cloud_id, None)
        _LINKS_REV = {l: c for c, l in _LINKS.items()}
        _save_links()


def get_links() -> Dict[str, Any]:
    """关联列表 + 云端识别设备（供前端连接面板渲染关联 UI）。"""
    with _LOCK:
        links = [{"cloud_id": c, "local_id": l} for c, l in _LINKS.items()]
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
            elif key == "subscriptions/count":
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
    primary = _primary_value(flat)
    with _LOCK:
        for field, value in flat.items():
            READINGS[field] = {"t": now, "v": value}
        if cloud_id:
            CLOUD_DEVICES[cloud_id] = {
                "id": cloud_id,
                "box": box,
                "topic": topic,
                "last_seen": now,
                "fields": dict(flat),
                "primary": primary,
            }
            # 兼容静态 mapping 直读：把主读数同时登记到 READINGS[cloud_id]
            if primary is not None:
                READINGS[cloud_id] = {"t": now, "v": primary}


# ------------------------- 对外查询接口 -------------------------

def get_readings() -> Dict[str, Dict[str, float]]:
    with _LOCK:
        return dict(READINGS)


def resolve_reading(device_id: str) -> Optional[float]:
    """按仿真设备实例 id 取真实读数 —— 采用「关联制」。

    只有该设备实例已与某个云端设备（能碳一体机盒子下的设备）建立关联时，
    才返回云端上报的主读数；未关联的设备一律返回 None（不同步）。

    关联来源：
    1. 用户在「能碳一体机管理」视图手动建立（config/links.json，cloud_id -> local_device_id）；
    2. 前端「配置 Broker」弹窗中的静态映射 mapping（静态配置，字段名视为云端设备）。

    返回 None 时调用方（realtime.py）不得回退到模拟数据。
    """
    with _LOCK:
        cloud_id = _LINKS_REV.get(device_id)
        if not cloud_id:
            return None
        cd = CLOUD_DEVICES.get(cloud_id)
        if cd and cd.get("primary") is not None:
            return cd["primary"]
        r = READINGS.get(cloud_id)          # 兼容静态 mapping 字段名直读
        if r is not None:
            return r["v"]
    return None


def broker_stats() -> Dict[str, Any]:
    """Broker 实时统计（来自 $SYS/broker/#，实时仪表盘数据源）。"""
    with _LOCK:
        return dict(BROKER_STATS)


def publish(topic: str, payload: Any) -> Dict[str, Any]:
    """向云端 Broker 发一条测试消息（参照 dashboard.py 的 /api/publish）。

    使用独立短连接客户端发布，不影响主订阅线程。
    """
    if not _PAHO_OK:
        return {"ok": False, "error": "未安装 paho-mqtt：pip install paho-mqtt"}
    try:
        pc = _make_client()
        username = _BROKER.get("username", "")
        password = _BROKER.get("password", "")
        if username:
            pc.username_pw_set(username, password or None)
        pc.connect(_BROKER.get("host", "127.0.0.1"), int(_BROKER.get("port", 41883)), 60)
        pc.loop_start()
        time.sleep(0.3)
        pc.publish(topic, payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                   qos=int(_BROKER.get("qos", 0)))
        time.sleep(0.3)
        pc.loop_stop()
        pc.disconnect()
        return {"ok": True, "topic": topic}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


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
            "runtime_file": os.path.basename(RUNTIME_CONFIG_PATH),
        }


def _save_runtime_config() -> None:
    """把当前配置持久化到 config/box_config.json（运行时产物，重启后自动恢复）。"""
    try:
        cfg = {"broker": dict(_BROKER), "topics": list(_TOPICS), "mapping": dict(_MAPPING)}
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
    global _BROKER, _TOPICS, _MAPPING, _REV_MAPPING
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
    with _LOCK:
        _BROKER, _TOPICS, _MAPPING = broker, topics, dict(mapping)
        _REV_MAPPING = {v: k for k, v in _MAPPING.items()}
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
