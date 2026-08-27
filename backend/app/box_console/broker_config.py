"""云端 Broker 配置（前端配置化）：读/存 broker 连接与认证配置，委托 mqtt_source 统一热更新。

依赖方向：本模块仅依赖 mqtt_source（基础设施层），被门面统一导出，无反向依赖。
"""
from __future__ import annotations

from typing import Any, Dict

from .. import mqtt_source


def get_config() -> Dict[str, Any]:
    """返回云端 Broker 配置（「能碳一体机管理」配置弹窗数据源，password 脱敏）。

    配置默认值来自参考项目 yunduan1（broker.yaml，TCP 41883 / WS 41083）。
    """
    return mqtt_source.get_config()


def update_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """保存云端 Broker 配置并热更新（前端配置化，运行时持久化到 box_config.json）。"""
    return mqtt_source.update_config(cfg)
