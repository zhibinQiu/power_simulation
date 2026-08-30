"""box_console 包：能碳一体机管理域（高内聚拆包后的兼容门面）。

原 app/box_console.py（1297 行上帝模块）按职责拆分为以下内聚子模块，
本门面重新导出全部公开符号（含历史私有符号 _fetch_cloud_k8s/_pack_box_deploy 等），
保证外部 `from . import box_console; box_console.xxx(...)` 调用方式完全不变：

- overview:        概览（云端 K8s 状态 / 盒子识别 / 节点合并 / box_overview）
- devices:         设备 CRUD + YAML 生成（工厂模式，渲染器见 domain/box/device_yaml.py）
- cloud_ops:       云端一键下发 / 重启 / CRD 删除（agent HTTP API，替代 SSH）
- edge:            盒子连接配置（IP/SSH 凭据）与云端部署指令（MQTT 命令主题）
- realtime_data:   实时数据（twins 趋势 / 云端 CRD / 日志 / 消息流 / 测试发布）
- onboard:         盒子接入（一键自解压脚本生成 / 下载 / 远程执行）

依赖方向：devices → cloud_ops → edge；realtime_data → devices/cloud_ops；
onboard → overview；均单向，无循环导入。
"""
from __future__ import annotations

# 共享内部状态（锁 / twins 趋势缓冲 / 统一仓储 / 路径常量）
from ._shared import (BOX_DEPLOY_DIR, CONFIG_DIR, DEVICES_FILE, EDGECORE_TEMPLATE,
                      GENERATED_DIR, ONBOARD_SCRIPT_PATH, _LOCK, _TWIN_HISTORY,
                      _TWIN_HISTORY_MAX, _load_devices, _save_devices)

# 概览
from .overview import _fetch_cloud_k8s, _merge_nodes, _mqtt_boxes, box_overview

# 设备 CRUD + YAML 生成
from .devices import (_device_fingerprint, _match_cloud_device,
                      _regenerate_devices_for_model, create_device, delete_device,
                      generate_device_yaml, list_devices, update_model)

# 云端下发 / 重启 / CRD 删除
from .cloud_ops import (_EDGE_UNIT_ALLOW, _K8S_NAME_RE, _SYSTEMD_ALLOW,
                        _auto_sync_cloud, _cloud_delete_crds, apply_devices_to_cloud,
                        cloud_config, restart_cloud_workload, update_cloud_config)

# 盒子连接配置与云端部署指令
from .edge import (_resolve_box_id, box_app_cmd, box_app_list, check_edge_reachable,
                   edge_config, update_edge_config)

# 实时数据
from .realtime_data import (_cloud_twins_map, _parse_crd_ts, broker_stats, cloud_crds,
                            cloud_logs, ingest_device_value, publish_test,
                            realtime_devices, recent_messages)

# 盒子接入
from .onboard import (_generate_onboard, _pack_box_deploy, _render_onboard_script,
                      box_onboard_remote, onboard_node, onboard_script_download)

# 外部依赖模块引用（tests 等通过 box_console.cloud_agent / mqtt_source 访问）
from .. import cloud_agent, mqtt_source  # noqa: F401,E402

# Broker 配置（读/存，由 mqtt_source 统一热更新；直接 re-export 避免多余透传层）
from ..mqtt_source import get_config, update_config  # noqa: E402

__all__ = [
    # 共享状态
    "BOX_DEPLOY_DIR", "CONFIG_DIR", "DEVICES_FILE", "EDGECORE_TEMPLATE",
    "GENERATED_DIR", "ONBOARD_SCRIPT_PATH", "_LOCK", "_TWIN_HISTORY",
    "_TWIN_HISTORY_MAX", "_load_devices", "_save_devices",
    # 概览
    "_fetch_cloud_k8s", "_merge_nodes", "_mqtt_boxes", "box_overview",
    # 设备 CRUD
    "_device_fingerprint", "_match_cloud_device", "_regenerate_devices_for_model",
    "create_device", "delete_device", "generate_device_yaml", "list_devices", "update_model",
    # 云端下发
    "_EDGE_UNIT_ALLOW", "_K8S_NAME_RE", "_SYSTEMD_ALLOW", "_auto_sync_cloud",
    "_cloud_delete_crds", "apply_devices_to_cloud", "cloud_config",
    "restart_cloud_workload", "update_cloud_config",
    # 盒子连接
    "_resolve_box_id", "box_app_cmd", "box_app_list", "check_edge_reachable",
    "edge_config", "update_edge_config",
    # 实时数据
    "_cloud_twins_map", "_parse_crd_ts", "broker_stats", "cloud_crds", "cloud_logs",
    "ingest_device_value", "publish_test", "realtime_devices", "recent_messages",
    # 盒子接入
    "_generate_onboard", "_pack_box_deploy", "_render_onboard_script",
    "box_onboard_remote", "onboard_node", "onboard_script_download",
    # Broker 配置
    "get_config", "update_config",
    # 外部依赖模块
    "cloud_agent", "mqtt_source",
]
