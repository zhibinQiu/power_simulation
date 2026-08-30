# -*- coding: utf-8 -*-
"""LLM 配置动态管理与持久化。

配置优先级（从高到低）：
  1. 运行时动态配置（backend/config/llm.json + 内存缓存，设置弹窗保存）
  2. 环境变量 / config/.env（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）
  3. 内置默认值

保存后**立即生效**：同时更新内存缓存、落盘 llm.json、并写入进程 os.environ
（llm_strategy._llm_cfg / deepseek_client.is_configured 等按环境变量读取的模块
无需重启即可拿到新配置）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional

# 持久化文件：backend/config/llm.json
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm.json"

# 环境变量名 <-> 配置字段名
ENV_MAP = {
    "base_url": "LLM_BASE_URL",
    "api_key": "LLM_API_KEY",
    "model": "LLM_MODEL",
}

DEFAULTS = {
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
}

_lock = threading.Lock()
# 运行时动态配置（内存缓存，save 时同步）
_DYNAMIC: Dict[str, str] = {}
# 本次进程内由动态配置覆盖过的环境变量名（reset 时恢复）
_OVERWRITTEN: set = set()


def _load_from_disk() -> Dict[str, str]:
    """从 llm.json 读取已保存的动态配置（失败返回空）。"""
    try:
        if CONFIG_PATH.is_file():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: str(v).strip() for k, v in data.items() if k in ENV_MAP and str(v).strip()}
    except Exception:
        pass
    return {}


def _write_to_disk() -> None:
    """把内存动态配置落盘（原子写）。"""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_DYNAMIC, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
    except Exception:
        pass


def get_llm_cfg() -> Dict[str, str]:
    """返回生效中的 LLM 配置（动态配置 > 环境变量 > 默认值）。"""
    with _lock:
        dynamic = dict(_DYNAMIC)
    if not dynamic:
        dynamic = _load_from_disk()
        if dynamic:
            with _lock:
                _DYNAMIC.update(dynamic)
    cfg = dict(DEFAULTS)
    for field, env in ENV_MAP.items():
        env_val = os.getenv(env, "").strip()
        if env_val:
            cfg[field] = env_val
        if dynamic.get(field):
            cfg[field] = dynamic[field]
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


def save_llm_cfg(base_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None) -> Dict[str, str]:
    """保存 LLM 配置：更新内存 + 落盘 + 写环境变量，立即生效。

    传入为 None 的字段保持当前生效值（合并保存）；api_key 传空字符串表示保留原 Key。
    """
    current = get_llm_cfg()
    merged = dict(current)
    if base_url is not None and base_url.strip():
        merged["base_url"] = base_url.strip().rstrip("/")
    if api_key is not None and api_key.strip():
        merged["api_key"] = api_key.strip()
    if model is not None and model.strip():
        merged["model"] = model.strip()

    with _lock:
        _DYNAMIC.clear()
        _DYNAMIC.update(merged)
        _write_to_disk()
        for field, env in ENV_MAP.items():
            val = merged.get(field, "")
            if os.getenv(env) != val:
                os.environ[env] = val
                _OVERWRITTEN.add(env)
    return dict(merged)


def reset_llm_cfg() -> Dict[str, str]:
    """恢复默认：清空动态配置（删除 llm.json + 内存），并移除本次覆盖的环境变量。

    返回恢复后的配置（环境变量/默认值）。"""
    with _lock:
        _DYNAMIC.clear()
        for env in _OVERWRITTEN:
            os.environ.pop(env, None)
        _OVERWRITTEN.clear()
    try:
        if CONFIG_PATH.is_file():
            CONFIG_PATH.unlink()
    except Exception:
        pass
    return get_llm_cfg()


def mask_key(api_key: str) -> str:
    """API Key 脱敏：仅保留前 4 位与后 4 位（空则返回空串）。"""
    key = (api_key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****" + key[-2:]
    return key[:4] + "****" + key[-4:]
