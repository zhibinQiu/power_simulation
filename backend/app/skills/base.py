"""Skills 基础层。

Skill 是本系统统一的能力单元，兼容 MCP Tool 协议：
- 内置 Skill：纯 Python 函数（查询设备、仿真、碳市场等），以 MCP Tool 的
  JSON Schema 定义入参，可被 LangGraph 智能体调用，也可通过 MCP Server
  对外暴露给第三方 MCP 客户端。
- 远端 Skill：本系统作为 MCP Client 连接第三方 MCP Server，将其 tools
  包装成 Skill 供智能体使用。

handler 统一返回文本（str），供 LLM 观察；可以是同步函数或协程。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# 单个工具执行结果的最大文本长度（防止上下文爆炸）
MAX_TOOL_OUTPUT = 4000


@dataclass
class Skill:
    name: str                      # 唯一标识（MCP tool name 同）
    description: str               # 给 LLM 看的描述
    input_schema: Dict[str, Any]   # JSON Schema（兼容 MCP InputSchema）
    handler: Callable[..., Any]    # fn(args: dict) -> str 或 async fn(args) -> str
    source: str = "builtin"        # builtin | mcp:{server_name}
    tags: List[str] = field(default_factory=list)  # 例如 ["device","simulation","carbon"]
    enabled: bool = True
    timeout: float = 45.0          # 单次执行超时（秒），防止慢/卡死工具拖垮智能体链路
    meta: Dict[str, Any] = field(default_factory=dict)  # 扩展信息（如 MCP 服务器地址）

    def to_public(self) -> Dict[str, Any]:
        """对外（前端/LLM）可见的信息，不暴露 handler。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "source": self.source,
            "tags": self.tags,
            "enabled": self.enabled,
            "meta": self.meta,
        }

    def to_mcp_tool(self) -> Dict[str, Any]:
        """转换为 MCP tools 协议格式（供 MCP Server 对外暴露）。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema or {"type": "object", "properties": {}},
        }

    def to_openai_tool(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 格式（供 LLM tool calling 使用）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


class SkillRegistry:
    """Skills 注册表：统一管理内置与 MCP 动态加载的 skills。"""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}
        self._enabled_state: Dict[str, bool] = {}   # name -> enabled（持久化状态）

    def _on_change(self) -> None:
        """启停状态变化钩子（子类可覆写做持久化）。"""

    def register(self, skill: Skill) -> None:
        # 已有持久化的启停状态时优先应用
        if skill.name in self._enabled_state:
            skill.enabled = self._enabled_state[skill.name]
        self._skills[skill.name] = skill
        logger.info("skill registered: %s (source=%s, enabled=%s)",
                    skill.name, skill.source, skill.enabled)

    def unregister(self, name: str) -> Optional[Skill]:
        return self._skills.pop(name, None)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def set_enabled(self, name: str, enabled: bool) -> Optional[Skill]:
        """启用/停用技能并持久化状态。"""
        skill = self._skills.get(name)
        if skill is None:
            return None
        skill.enabled = bool(enabled)
        self._enabled_state[name] = skill.enabled
        self._on_change()
        logger.info("skill %s -> enabled=%s", name, skill.enabled)
        return skill

    def load_enabled_state(self, state: Dict[str, bool]) -> None:
        """加载持久化的启停状态并应用到已注册技能。"""
        self._enabled_state = dict(state or {})
        for name, flag in self._enabled_state.items():
            skill = self._skills.get(name)
            if skill is not None:
                skill.enabled = bool(flag)

    def enabled_state(self) -> Dict[str, bool]:
        return dict(self._enabled_state)

    def list(self, enabled_only: bool = True) -> List[Skill]:
        skills = list(self._skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return sorted(skills, key=lambda s: (s.source, s.name))

    def list_public(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        return [s.to_public() for s in self.list(enabled_only)]

    def names(self, enabled_only: bool = True) -> List[str]:
        return [s.name for s in self.list(enabled_only)]

    async def execute(self, name: str, args: Dict[str, Any]) -> str:
        """执行 skill 并返回文本结果。异常会转为错误文本返回（不抛出）。"""
        skill = self.get(name)
        if skill is None:
            return f"[skill not found: {name}]"
        if not skill.enabled:
            return f"[skill disabled: {name}]"
        started = time.time()
        try:
            handler = skill.handler
            if asyncio.iscoroutinefunction(handler):
                coro = handler(args)
            else:
                # 内置同步 handler 放到线程池，避免阻塞事件循环
                coro = asyncio.to_thread(handler, args)
            result = await asyncio.wait_for(coro, timeout=skill.timeout)
            text = _stringify(result)
            logger.info("skill %s ok (%.2fs)", name, time.time() - started)
            return _truncate(text, MAX_TOOL_OUTPUT)
        except asyncio.TimeoutError:
            logger.warning("skill %s timeout after %.0fs", name, skill.timeout)
            return f"[skill timeout: {name}] 执行超过 {skill.timeout:.0f}s 未返回"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 工具错误转文本
            logger.exception("skill %s failed", name)
            return f"[skill error: {name}] {exc}"


def _stringify(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(result)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"
