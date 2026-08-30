# -*- coding: utf-8 -*-
"""知识库路径配置动态管理与持久化。

配置优先级（从高到低）：
  1. 运行时动态配置（backend/config/kb.json + 内存缓存，设置弹窗「知识库」页保存）
  2. 环境变量 / config/.env（KB_ROOT）
  3. 内置默认值（backend/knowledge/）

保存后**立即生效**：同时更新内存缓存、落盘 kb.json、并写入进程 os.environ["KB_ROOT"]
（knowledge_service.kb_root() 每次读取时按此优先级取值，无需重启）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional

# 持久化文件：backend/config/kb.json
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "kb.json"

# 环境变量名
ENV_ROOT = "KB_ROOT"

# 内置默认知识库路径：backend/knowledge/
DEFAULT_KB_PATH = str(Path(__file__).resolve().parent.parent / "knowledge")

_lock = threading.Lock()
# 运行时动态配置（内存缓存，save 时同步）
_DYNAMIC: Dict[str, str] = {}
# 本次进程内由动态配置覆盖过的环境变量名（reset 时恢复）
_OVERWRITTEN: set = set()


def _load_from_disk() -> Dict[str, str]:
    """从 kb.json 读取已保存的动态配置（失败返回空）。"""
    try:
        if CONFIG_PATH.is_file():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and str(data.get("root_path", "")).strip():
                return {"root_path": str(data["root_path"]).strip()}
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


def get_kb_cfg() -> Dict[str, str]:
    """返回生效中的知识库配置（动态配置 > 环境变量 > 默认）。"""
    with _lock:
        dynamic = dict(_DYNAMIC)
    if not dynamic:
        dynamic = _load_from_disk()
        if dynamic:
            with _lock:
                _DYNAMIC.update(dynamic)
    root = os.getenv(ENV_ROOT, "").strip()
    if dynamic.get("root_path"):
        root = dynamic["root_path"]
    return {
        "root_path": root or DEFAULT_KB_PATH,
        "default_path": DEFAULT_KB_PATH,
        "configured": bool(dynamic.get("root_path")),
    }


def save_kb_cfg(root_path: str) -> Dict[str, str]:
    """保存知识库根目录：更新内存 + 落盘 + 写环境变量，立即生效。

    传入空字符串表示恢复内置默认路径。路径会尝试创建目录以校验可写性。"""
    path = (root_path or "").strip()
    if path:
        # 展开 ~ 与相对路径（相对 backend 目录）
        expanded = os.path.expanduser(path)
        if not os.path.isabs(expanded):
            expanded = str(Path(__file__).resolve().parent.parent / expanded)
        try:
            os.makedirs(expanded, exist_ok=True)
        except Exception as e:
            raise ValueError(f"知识库路径不可用：{e}")
        path = expanded
    else:
        path = DEFAULT_KB_PATH

    with _lock:
        _DYNAMIC.clear()
        _DYNAMIC["root_path"] = path
        _write_to_disk()
        if os.getenv(ENV_ROOT) != path:
            os.environ[ENV_ROOT] = path
            _OVERWRITTEN.add(ENV_ROOT)
    return get_kb_cfg()


def reset_kb_cfg() -> Dict[str, str]:
    """恢复默认：清空动态配置（删除 kb.json + 内存），并移除本次覆盖的环境变量。"""
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
    return get_kb_cfg()
