"""mqtt_source 包：前端配置化（Broker 配置读取 / 校验 / 持久化 / 热更新重启订阅）。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from . import _shared
from ._shared import (CLOUD_DEVICES, READINGS, RUNTIME_CONFIG_PATH, _LOCK,
                      _STATE)
from .client import _restart_subscriber
from .links import _load_links


def get_config() -> Dict[str, Any]:
    """返回当前云端 Broker 配置（前端配置弹窗数据源，password 脱敏）。

    前端「能碳一体机管理」总览 -> 云端数据链路卡片「配置」按钮调用，保存后走 update_config。
    """
    with _LOCK:
        broker = dict(_shared._BROKER)
        broker["password"] = "******" if broker.get("password") else ""
        return {
            "broker": broker,
            "topics": list(_shared._TOPICS),
            "mapping": dict(_shared._MAPPING),
            "ignored_devices": sorted(_shared._IGNORED_DEVICES),
            "runtime_file": os.path.basename(RUNTIME_CONFIG_PATH),
        }


def _save_runtime_config() -> None:
    """把当前配置持久化到 config/box_config.json（运行时产物，重启后自动恢复）。"""
    try:
        cfg = {"broker": dict(_shared._BROKER), "topics": list(_shared._TOPICS),
               "mapping": dict(_shared._MAPPING),
               "ignored_devices": sorted(_shared._IGNORED_DEVICES)}
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
    broker = dict(_shared._BROKER)
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
        broker["password"] = _shared._BROKER.get("password", "")
    topics = cfg.get("topics") if isinstance(cfg.get("topics"), list) else _shared._TOPICS
    topics = [str(t).strip() for t in topics if str(t).strip()] or ["#"]
    mapping = cfg.get("mapping") if isinstance(cfg.get("mapping"), dict) else dict(_shared._MAPPING)
    ignored = cfg.get("ignored_devices")
    if isinstance(ignored, list):
        ignored_set = {str(i).strip() for i in ignored if str(i).strip()}
    else:
        ignored_set = set(_shared._IGNORED_DEVICES)
    with _LOCK:
        _shared._BROKER, _shared._TOPICS, _shared._MAPPING = broker, topics, dict(mapping)
        _shared._REV_MAPPING = {v: k for k, v in _shared._MAPPING.items()}
        # 更新忽略设备集合，并清除其历史缓存（不再识别/同步）
        _shared._IGNORED_DEVICES = ignored_set
        for cid in list(_shared._IGNORED_DEVICES):
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
        "mapping": dict(_shared._MAPPING),
        "note": "配置已保存并热更新（持久化到 box_config.json，无需手工编辑配置文件）",
    }
