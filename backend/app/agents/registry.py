"""智能体注册表：从 AgentStore 动态加载「本析智擎」智能体。

每个智能体有独立的身份与系统提示词，并可配置可用的 Skills 子集。
执行时前端选择智能体 → 注入对应 system prompt + skills 白名单 → LangGraph
图（调度智能体规划/验收 + 子智能体执行）运行。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .store import Agent, get_store

__all__ = ["Agent", "get_agent", "list_agents", "available_skill_names", "get_store"]


def get_agent(agent_id: str) -> Agent:
    """按 id 取智能体，缺省回退通用助手。"""
    store = get_store()
    agent = store.get(agent_id or "general")
    if agent:
        return agent
    general = store.get("general")
    return general or store.get("data_analyst")


def list_agents() -> List[Dict[str, Any]]:
    return get_store().list()


def available_skill_names(agent_id: str) -> Optional[List[str]]:
    """返回智能体可用 skill 名列表；None 表示不限。"""
    return get_agent(agent_id).available_skills


def add_agent(data: Dict[str, Any]) -> Dict[str, Any]:
    return get_store().add(data).to_dict()


def update_agent(agent_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    a = get_store().update(agent_id, data)
    return a.to_dict() if a else None


def delete_agent(agent_id: str) -> bool:
    return get_store().delete(agent_id)
