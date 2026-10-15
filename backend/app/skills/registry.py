"""Skills 全局注册表：内置 skills + 启停持久化。

模块级单例 get_registry()，主进程启动时调用 init_registry() 完成：
1. 注册全部内置 skills
2. 应用 backend/data/skills.json 中保存的启停状态
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from .base import SkillRegistry
from .builtin import register_builtin_skills
from .methodology import register_methodology_skills
from app.core.config import data_path

logger = logging.getLogger(__name__)

DATA_DIR = Path(data_path())
SKILLS_STATE_FILE = DATA_DIR / "skills.json"
_state_lock = threading.Lock()


class _PersistentSkillRegistry(SkillRegistry):
    """带启停状态持久化的注册表。"""

    def _on_change(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with _state_lock:
                SKILLS_STATE_FILE.write_text(
                    json.dumps({"skills": self.enabled_state()}, ensure_ascii=False, indent=2),
                    "utf-8",
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("persist skills state failed: %s", e)


_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = _PersistentSkillRegistry()
        register_builtin_skills(_registry)
        register_methodology_skills(_registry)
        _apply_state_file(_registry)
    return _registry


def _apply_state_file(registry: SkillRegistry) -> None:
    try:
        if SKILLS_STATE_FILE.exists():
            data = json.loads(SKILLS_STATE_FILE.read_text("utf-8"))
            registry.load_enabled_state(data.get("skills") or {})
    except Exception as e:  # noqa: BLE001
        logger.warning("load skills state failed: %s", e)


def set_skill_enabled(name: str, enabled: bool) -> Optional[Dict]:
    """启用/停用技能（含持久化）。返回更新后的 public 信息。"""
    registry = get_registry()
    skill = registry.set_enabled(name, bool(enabled))
    return skill.to_public() if skill else None


def list_skills(enabled_only: bool = False) -> list:
    """返回技能列表（默认含禁用项，供管理界面使用）。"""
    return get_registry().list_public(enabled_only=enabled_only)


def init_registry() -> SkillRegistry:
    """初始化全局注册表（注册内置 skills 并应用持久化的启停状态）。"""
    return get_registry()
