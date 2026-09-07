"""适配器注册表：按 config.type 实例化采集适配器，并支持运行时热插拔。

新增外部数据形态：实现 BaseAdapter 子类后在此注册即可
（平台与标准输出规范无需任何改动）。

热插拔由 registry.AdapterRegistry 驱动：新增/修改/启停/删除都会即时作用到运行中的
适配器并持久化回 config.json（平台经 HTTP 管理 API 调用）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from middleware.adapters.base import BaseAdapter, flatten, numeric  # noqa: F401  复用纯函数
from middleware.adapters.mqtt_source import MqttSourceAdapter

# 适配器类型 → 实现类。
# 模拟数据**不是**内置类型：模拟由独立服务（cloud-deploy/sim-source/）生成并经
# `mqtt` 适配器接入，平台与中间件自身都不产生任何模拟数据。
BUILDERS: Dict[str, type] = {
    "mqtt": MqttSourceAdapter,
}

# 适配器类型元信息（前端表单按此渲染参数区）
TYPE_META: Dict[str, Dict[str, Any]] = {
    "mqtt": {
        "label": "外部 MQTT",
        "desc": "订阅外部 MQTT Broker 的主题，转换为标准 MQTT 后由平台订阅",
        "fields": [
            {"key": "broker.host", "label": "Broker 地址", "type": "text", "required": True,
             "placeholder": "10.0.0.20"},
            {"key": "broker.port", "label": "端口", "type": "number", "default": 1883},
            {"key": "broker.username", "label": "用户名", "type": "text", "required": False},
            {"key": "broker.password", "label": "密码", "type": "password", "required": False},
            {"key": "topics", "label": "订阅主题", "type": "list", "required": True,
             "placeholder": "factory/scale1/#"},
            {"key": "device", "label": "默认设备 id", "type": "text", "required": False,
             "placeholder": "消息无 device 字段时使用"},
            {"key": "fieldMap", "label": "字段改名(JSON)", "type": "json", "required": False,
             "placeholder": '{"gross": "weight"}'},
        ],
    },
}


def build(cfg: Dict[str, Any], bridge: Any, logger: Any = None) -> "Tuple[BaseAdapter | None, list]":
    """实例化单个适配器；返回 (adapter, errors)。"""
    if not isinstance(cfg, dict):
        return None, [f"adapter 配置项不是对象: {cfg}"]
    typ = str(cfg.get("type") or "")
    cls = BUILDERS.get(typ)
    if cls is None:
        return None, [f"adapter[{cfg.get('id')}] 未知 type「{typ}」（可用: {sorted(BUILDERS)}）"]
    try:
        inst = cls(cfg, bridge, logger)
        errs = inst.validate()
        if errs:
            return None, errs
        return inst, []
    except Exception as e:  # noqa: BLE001
        return None, [f"adapter[{cfg.get('id')}] 初始化失败: {e}"]


def build_all(adapters_cfg: List[Dict[str, Any]], bridge: Any,
              logger: Any = None) -> "tuple[list, list]":
    """按配置实例化全部启用的适配器；返回 (adapters, errors)。

    errors 中记录 type 未知/配置校验失败的任务，不因单个任务失败中断整体。
    """
    adapters, errors = [], []
    for cfg in adapters_cfg or []:
        if not isinstance(cfg, dict):
            errors.append(f"adapter 配置项不是对象: {cfg}")
            continue
        if cfg.get("enabled") is False:
            continue
        inst, errs = build(cfg, bridge, logger)
        if errs:
            errors.extend(errs)
            continue
        adapters.append(inst)
    return adapters, errors


def type_catalog() -> List[Dict[str, Any]]:
    """供平台/前端查询的适配器类型清单。"""
    return [{"type": k, **v} for k, v in TYPE_META.items()]
