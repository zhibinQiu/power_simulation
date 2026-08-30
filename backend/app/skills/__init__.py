"""Skills 体系：内置能力 + MCP 协议双向接入。

- base.py        Skill 数据类与注册表
- builtin.py     内置 skills（查询设备/仿真/碳市场/排放因子）
- mcp_client.py  作为 MCP Client 使用第三方 Skill
- mcp_server.py  作为 MCP Server 向外提供服务
- registry.py    全局注册表单例
"""
from .base import Skill, SkillRegistry
from .registry import get_registry, get_mcp_manager, init_registry

__all__ = ["Skill", "SkillRegistry", "get_registry", "get_mcp_manager", "init_registry"]
