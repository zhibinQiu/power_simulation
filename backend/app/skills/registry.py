"""Skills 全局注册表：内置 skills + MCP 动态加载 + 启停持久化。

模块级单例 get_registry()，主进程启动时调用 init_registry() 完成：
1. 注册全部内置 skills
2. 读取 config/mcp_servers.json 连接第三方 MCP server，把其 tools 注册为 skills
3. 应用 backend/data/skills.json 中保存的启停状态
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

from .base import SkillRegistry
from .builtin import register_builtin_skills

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
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
_mcp_manager: Optional[object] = None
# 保存 MCP 连接的后台任务引用，防止被 asyncio 回收导致连接中断
_mcp_connect_task: Optional[asyncio.Task] = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = _PersistentSkillRegistry()
        register_builtin_skills(_registry)
        _apply_state_file(_registry)
    return _registry


def _apply_state_file(registry: SkillRegistry) -> None:
    try:
        if SKILLS_STATE_FILE.exists():
            data = json.loads(SKILLS_STATE_FILE.read_text("utf-8"))
            registry.load_enabled_state(data.get("skills") or {})
    except Exception as e:  # noqa: BLE001
        logger.warning("load skills state failed: %s", e)


def get_mcp_manager():
    """返回 MCP Client 管理器（惰性创建）。"""
    global _mcp_manager
    if _mcp_manager is None:
        from .mcp_client import McpClientManager
        _mcp_manager = McpClientManager()
    return _mcp_manager


def set_skill_enabled(name: str, enabled: bool) -> Optional[Dict]:
    """启用/停用技能（含持久化）。返回更新后的 public 信息。"""
    registry = get_registry()
    skill = registry.set_enabled(name, bool(enabled))
    return skill.to_public() if skill else None


def list_skills(enabled_only: bool = False) -> list:
    """返回技能列表（默认含禁用项，供管理界面使用）。"""
    return get_registry().list_public(enabled_only=enabled_only)


def init_registry(connect_mcp: bool = True) -> SkillRegistry:
    """初始化全局注册表；connect_mcp=True 时连接已配置的第三方 MCP server。"""
    global _mcp_connect_task
    registry = get_registry()
    if connect_mcp:
        manager = get_mcp_manager()
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            _mcp_connect_task = asyncio.create_task(manager.connect_all(registry))
        else:
            asyncio.run(manager.connect_all(registry))
    return registry
