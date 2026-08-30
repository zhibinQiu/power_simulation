"""LLM 服务配置：模型 / API Key / 服务地址。

配置持久化于 backend/config/llm_cfg.json，优先级：运行时配置 > 环境变量 > 默认值。
读写 / 内存缓存 / 环境变量同步由 core.json_cfg.JsonCfgStore 统一承载，本模块只声明
字段映射与业务语义（base_url 去尾斜杠），保持高内聚低耦合。
"""
from __future__ import annotations

import os
from typing import Dict, Optional

from .core.json_cfg import JsonCfgStore

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config", "llm_cfg.json"
)

ENV_MAP = {
    "base_url": "LLM_BASE_URL",
    "api_key": "LLM_API_KEY",
    "model": "LLM_MODEL",
}
DEFAULTS = {
    "base_url": "https://vip.oaiproxy.co/v1",
    "api_key": "sk-None",
    "model": "gpt-4o-mini",
}

_store = JsonCfgStore(CONFIG_PATH, ENV_MAP, DEFAULTS)


def get_llm_cfg() -> Dict[str, str]:
    """当前生效的 LLM 配置（动态配置 > 环境变量 > 默认值）。"""
    cfg = _store.get()
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


def save_llm_cfg(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, str]:
    """保存 LLM 配置：None / 空串保留当前值，返回合并后的生效配置。"""
    base = base_url.strip().rstrip("/") if base_url else None
    return _store.save({"base_url": base, "api_key": api_key, "model": model})


def reset_llm_cfg() -> Dict[str, str]:
    """恢复默认配置并清理持久化文件。"""
    return _store.reset()


def mask_key(key: Optional[str]) -> str:
    """脱敏展示 API Key：仅保留前 4 位与后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"
