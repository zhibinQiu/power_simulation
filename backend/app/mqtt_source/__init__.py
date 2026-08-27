"""mqtt_source 包（门面 Facade）：MQTT 实时数据获取模块。

原 app/mqtt_source.py（1011 行上帝模块）按职责拆分为：
- _shared    ：共享状态收敛点（常量/配置/缓存/锁/paho 探测）；
- parsing    ：消息解析（设备识别/主读数/关联制读数解析/快照）；
- links      ：云端设备 <-> 仿真设备关联表持久化；
- box_state  ：盒子侧状态缓存（state/# 主题）；
- ingest     ：消息摄取核心（_record_message 等）；
- publish    ：Broker 统计 / 测试发布 / 连接状态查询；
- config     ：前端配置化（读取/校验/持久化/热更新）；
- client     ：订阅客户端生命周期（start / 断线重连）。

本门面重新导出全部公开与私有符号，外部 `from . import mqtt_source` /
`from .mqtt_source import X` 用法不变。
"""
from __future__ import annotations

# 状态与基础设施（先初始化 _shared，再导入子模块）
from . import _shared
from ._shared import (BOX_APP_EVENTS, BOX_DEVICES_FILE, BOX_SERVICES,
                      BROKER_STATS, CLOUD_DEVICES, CONFIG_DIR, CONFIG_PATH,
                      DEFAULT_CFG, GC_TTL, LINKS_FILE, MESSAGE_LOG,
                      MESSAGE_LOG_MAX, READINGS, REPLAY_HISTORY,
                      REPLAY_HISTORY_MAX, RUNTIME_CONFIG_PATH, _BOX_KEYS,
                      _BROKER, _CLIENT, _DEVICE_ID_KEYS, _GC_MIN_INTERVAL,
                      _IGNORED_DEVICES, _INVALID_READING_VALUES, _LINKS,
                      _LINKS_FACTOR, _LINKS_REV, _LOCK, _MAIN_PROPS,
                      _MAPPING, _PAHO_OK, _PRIMARY_KEYS, _REV_MAPPING,
                      _STATE, _TOPICS, _config, _last_gc_ts, mqtt)

from .. import cloud_agent  # noqa: E402 兼容旧模块属性（mqtt_source.cloud_agent）

# 解析
from .parsing import (  # noqa: E402
    _box_device_name_of_cloud_id, _crd_twin_reading, _identify_cloud_device,
    _is_invalid_reading, _main_property_of_topic, _primary_value,
    resolve_reading, snapshot_cloud_devices,
)

# 关联表
from .links import (  # noqa: E402
    _load_links, _save_links, get_links, remove_link, set_link,
)

# 盒子状态
from .box_state import (  # noqa: E402
    _record_box_state, box_app_events, box_services, publish_box_cmd,
)

# 消息摄取
from .ingest import (  # noqa: E402
    _gc_expired, _log_msg, _record_message, _record_replay, take_replay,
)

# 发布与查询
from .publish import (  # noqa: E402
    broker_stats, get_status, publish,
)

# 配置化
from .config import (  # noqa: E402
    _save_runtime_config, get_config, update_config,
)

# 订阅客户端
from .client import (  # noqa: E402
    _make_client, _on_connect, _on_disconnect, _on_message, _restart_subscriber,
    start,
)

__all__ = [
    # 基础设施/状态
    "mqtt", "_PAHO_OK", "cloud_agent",
    "CONFIG_DIR", "CONFIG_PATH", "RUNTIME_CONFIG_PATH", "LINKS_FILE", "BOX_DEVICES_FILE",
    "DEFAULT_CFG", "_config", "_BROKER", "_TOPICS", "_MAPPING", "_REV_MAPPING",
    "_IGNORED_DEVICES", "_LOCK", "READINGS", "CLOUD_DEVICES", "REPLAY_HISTORY",
    "REPLAY_HISTORY_MAX", "MESSAGE_LOG", "MESSAGE_LOG_MAX", "GC_TTL", "_GC_MIN_INTERVAL",
    "_last_gc_ts", "BROKER_STATS", "_STATE", "_LINKS", "_LINKS_REV", "_LINKS_FACTOR",
    "_BOX_KEYS", "_DEVICE_ID_KEYS", "_PRIMARY_KEYS", "_MAIN_PROPS",
    "_INVALID_READING_VALUES", "BOX_SERVICES", "BOX_APP_EVENTS", "_CLIENT",
    # 解析
    "_is_invalid_reading", "_main_property_of_topic", "_identify_cloud_device",
    "_primary_value", "_box_device_name_of_cloud_id", "_crd_twin_reading",
    "resolve_reading", "snapshot_cloud_devices",
    # 关联表
    "_load_links", "_save_links", "set_link", "remove_link", "get_links",
    # 盒子状态
    "_record_box_state", "box_services", "box_app_events", "publish_box_cmd",
    # 消息摄取
    "_log_msg", "_record_message", "_record_replay", "take_replay", "_gc_expired",
    # 发布与查询
    "broker_stats", "publish", "get_status",
    # 配置化
    "get_config", "_save_runtime_config", "update_config", "_restart_subscriber",
    # 订阅客户端
    "_make_client", "_on_connect", "_on_disconnect", "_on_message", "start",
]
