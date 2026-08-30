"""知识库根目录配置。

持久化于 backend/config/kb_cfg.json，优先级：运行时配置 > 环境变量（KB_ROOT）。
读写逻辑由 core.json_cfg.JsonCfgStore 统一承载，本模块只保留目录校验等业务语义。
"""
from __future__ import annotations

import os
from typing import Dict

from .core.json_cfg import JsonCfgStore

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config", "kb_cfg.json"
)
ENV_MAP = {"root_path": "KB_ROOT"}
DEFAULT_KB_PATH = "storage/kb"

_store = JsonCfgStore(CONFIG_PATH, ENV_MAP)


def get_kb_cfg() -> Dict[str, str]:
    """当前生效的知识库根目录配置。"""
    root = _store.get().get("root_path", "")
    return {
        "root_path": root or DEFAULT_KB_PATH,
        "default_path": DEFAULT_KB_PATH,
        "configured": _store.has_dynamic("root_path"),
    }


def save_kb_cfg(path: str) -> Dict[str, str]:
    """保存知识库根目录：空串恢复默认；目录不存在则自动创建（失败抛 ValueError）。"""
    path = (path or "").strip() or DEFAULT_KB_PATH
    path = os.path.expanduser(path)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise ValueError(f"无法创建知识库目录：{path}（{e}）") from e
    if not os.path.isdir(path):
        raise ValueError(f"知识库目录不可用：{path}")
    _store.save({"root_path": path})
    return get_kb_cfg()


def reset_kb_cfg() -> Dict[str, str]:
    """恢复默认根目录并清理持久化文件。"""
    _store.reset()
    return get_kb_cfg()
