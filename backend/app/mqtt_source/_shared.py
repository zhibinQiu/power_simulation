"""mqtt_source 包：模块级共享状态收敛点。

拆分自 app/mqtt_source.py（原 1011 行上帝模块）。本模块只承载：
- 路径常量、默认配置、配置加载（_load_config）；
- 全部模块级可变状态（_BROKER/_TOPICS/_MAPPING/_LINKS/... 及 CLOUD_DEVICES/READINGS 等缓存）；
- paho-mqtt 可选依赖探测（mqtt/_PAHO_OK）。

访问约定：
- 常量与「原地修改」的状态（dict/list，如 _LOCK/READINGS/CLOUD_DEVICES/MESSAGE_LOG/BROKER_STATS）
  可 `from ._shared import X` 直接绑定；
- 「被整体重新赋值」的状态（_BROKER/_TOPICS/_MAPPING/_REV_MAPPING/_IGNORED_DEVICES/
  _LINKS/_LINKS_REV/_LINKS_FACTOR/_CLIENT/_last_gc_ts）必须经 `_shared.X` 属性读写，
  否则子模块间会产生名字分裂（如 config 热更新后 client 仍读旧值）。
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

# paho-mqtt 为可选依赖（pip install paho-mqtt）；未安装时降级为空实现，不影响平台启动
try:
    import paho.mqtt.client as mqtt
    _PAHO_OK = True
except Exception:  # pragma: no cover
    mqtt = None  # type: ignore[assignment]
    _PAHO_OK = False

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "mqtt.yaml")          # 旧版手工配置文件（向后兼容）
RUNTIME_CONFIG_PATH = os.path.join(CONFIG_DIR, "box_config.json")  # 前端配置持久化（运行时产物，无需手工编辑）
LINKS_FILE = os.path.join(CONFIG_DIR, "links.json")   # 云端设备 <-> 仿真设备实例关联持久化
BOX_DEVICES_FILE = os.path.join(CONFIG_DIR, "box_devices.json")  # 盒子设备配置（cloudDevice/name 反查用）

from .. import cloud_agent  # noqa: F401 —— re-export：子模块经 _shared.cloud_agent 访问  # noqa: E402 云端 agent 推送（cloud/# 主题）解析，替代 SSH 数据通道

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

# 需要忽略的云端设备（重复链路/废弃设备，仍发布 MQTT 但不再识别为云端设备）。
# 持久化在 config/box_config.json 的 ignored_devices 字段，可在 update_config 中维护。
_IGNORED_DEVICES: set = set(_config.get("ignored_devices") or [])

# 盒子侧状态缓存：box -> 运行服务列表/最近部署结果（盒子卡片展示用）
BOX_SERVICES: Dict[str, Dict[str, Any]] = {}      # box -> {"services": [...], "last_seen": ts}
BOX_APP_EVENTS: Dict[str, List[Dict[str, Any]]] = {}  # box -> 最近部署/启停命令执行结果（最多 20 条）

# 外部数据源摄取统计：box 前缀 -> {received, last_at, last_topic, last_msg}
# （外部源为登记制，无平台进程内线程；此处统计供 external 条目状态展示「最近读数」，
#   由 mqtt_source.ingest 在归类 external 消息时原地更新，_LOCK 保护）
_EXT_STATS: Dict[str, Dict[str, Any]] = {}

# 当前订阅客户端引用（供配置热更新时断开重连）。多 Broker 场景下此处保存
# **云端（一体机）** 的客户端，中间件 Broker 的客户端见 _EP_CLIENTS。
_CLIENT = None

# ------------------------- 多 Broker 订阅端点 -------------------------
# 平台订阅两类数据入口（消息归属按前缀+src 自动区分，与入口无关）：
#   cloud      云端 Broker（默认 41883）：能碳一体机盒子/云端 agent 推送（cloud/#、
#              state/#、$SYS/#、data/#）——原有数据与统计来源；
#              external 形态下外部数据源/模拟数据也直发本 Broker（data/ext-*/...）；
#   middleware 中间件独立数据端口（仅 local 形态，默认 41884 可经 middleware.json
#              subscribe=false 停用）：外部数据源（含独立模拟源），仅收数据主题
#              （不订阅 $SYS，避免与云端 Broker 的统计互相污染）。
# 两端共享同一条摄取管道（ingest._record_message），按 source 区分统计口径。
_ENDPOINTS: Dict[str, Dict[str, Any]] = {}
_EP_STATE: Dict[str, Dict[str, Any]] = {}
_EP_CLIENTS: Dict[str, Any] = {}

# 中间件端点只订阅数据主题（中间件只发布 data/{box}/... ，不产生 cloud/state/$SYS）
MW_TOPICS = ["data/#"]


def _init_endpoints() -> None:
    """初始化订阅端点（云端取自 Broker 配置，中间件取自 middleware_client 配置）。"""
    _ENDPOINTS["cloud"] = {
        "key": "cloud",
        "label": "云端 Broker（能碳一体机）",
        "broker": dict(_BROKER),
        "topics": list(_TOPICS),
        "sys": True,          # 采集 $SYS/broker/# 统计
        "enabled": True,      # 云端是主数据源，始终订阅
    }
    _ENDPOINTS["middleware"] = {
        "key": "middleware",
        "label": "数据中间件（外部数据源）",
        "broker": {"host": "127.0.0.1", "port": 41884, "username": "", "password": "",
                   "client_id": "carbon-sim-mw", "keepalive": 60, "qos": 0},
        "topics": list(MW_TOPICS),
        "sys": False,
        "enabled": True,
    }
    for key in ("cloud", "middleware"):
        _EP_STATE.setdefault(key, {
            "connected": False, "last_connect_rc": None, "last_error": "",
            "enabled": True, "message_count": 0, "last_message_at": None,
        })


_init_endpoints()


def sync_endpoints() -> None:
    """把最新配置同步到订阅端点（云端 Broker 配置/中间件配置热更新后调用）。"""
    cloud = _ENDPOINTS.get("cloud")
    if cloud is not None:
        cloud["broker"] = dict(_BROKER)
        cloud["topics"] = list(_TOPICS)
    mw = _ENDPOINTS.get("middleware")
    if mw is not None:
        try:
            from .. import middleware_client as _mwc
            cfg = _mwc.load_config()
            bkr = dict(cfg.get("broker") or {})
            mw["broker"] = {
                "host": str(bkr.get("host") or "127.0.0.1"),
                "port": int(bkr.get("port") or 41884),
                "username": str(bkr.get("username") or ""),
                "password": str(bkr.get("password") or ""),
                "client_id": "carbon-sim-mw", "keepalive": 60, "qos": 0,
            }
            # 端点订阅开关：subscribe=false（external 形态）时不再单独订阅中间件端口，
            # 外部数据已直发云端 Broker，平台经云端端点（41883）统一取数
            mw["enabled"] = bool(cfg.get("subscribe", True)) and bool(cfg.get("enabled", True))
        except Exception:  # noqa: BLE001
            pass


def endpoint_states() -> Dict[str, Dict[str, Any]]:
    """各订阅端点的连接状态快照（前端展示「同时订阅两个 Broker」的连通情况）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for key, ep in _ENDPOINTS.items():
        st = dict(_EP_STATE.get(key) or {})
        st["label"] = ep.get("label")
        st["host"] = (ep.get("broker") or {}).get("host")
        st["port"] = (ep.get("broker") or {}).get("port")
        st["topics"] = list(ep.get("topics") or [])
        out[key] = st
    return out
