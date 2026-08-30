"""MCP Client 管理器 —— 使用第三方 Skill。

本系统作为 MCP Client 连接外部 MCP Server（stdio 子进程或 streamable-http
端点），把对方暴露的 tools 动态包装成本系统 Skill，供 LangGraph 智能体调用，
实现「使用第三方的 skill」。

外部 server 配置存放在 backend/config/mcp_servers.json，可在运行期通过
API 增删改并重连，单个 server 连接失败不影响主服务。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import httpx2, streamable_http_client

from .base import Skill

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "mcp_servers.json"

# 外部 tool 包装成 skill 名前缀分隔符
_SKILL_SEP = "__"


@dataclass
class McpServerConfig:
    name: str
    transport: str = "stdio"              # stdio | http
    command: str = ""                     # stdio: 启动命令（如 python3、npx）
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""                         # http: streamable-http 端点
    headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def validate(self) -> str:
        if self.transport == "stdio" and not self.command:
            return "stdio transport 必须提供 command"
        if self.transport == "http" and not self.url:
            return "http transport 必须提供 url"
        return ""

    def to_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "url": self.url,
            "command": self.command,
            "enabled": self.enabled,
            "status": "idle",
            "error": "",
            "tools_count": 0,
            "tools": [],
        }


def skill_name(server: str, tool: str) -> str:
    return f"mcp{_SKILL_SEP}{server}{_SKILL_SEP}{tool}"


class McpConnection:
    """单个外部 MCP server 的活动连接。"""

    def __init__(self, cfg: McpServerConfig) -> None:
        self.cfg = cfg
        self.status = "idle"               # idle | connecting | connected | error
        self.error: str = ""
        self.tools: List[Dict[str, Any]] = []
        self._stream_cm = None
        self._streams = None
        self._session: Optional[ClientSession] = None
        self._http_client = None

    @property
    def name(self) -> str:
        return self.cfg.name

    async def connect(self) -> None:
        self.status = "connecting"
        self.error = ""
        try:
            if self.cfg.transport == "http":
                self._http_client = (httpx2.AsyncClient(headers=self.cfg.headers)
                                     if self.cfg.headers else None)
                cm = streamable_http_client(self.cfg.url, http_client=self._http_client)
                self._stream_cm = cm
                self._streams = await cm.__aenter__()
            else:
                env = None
                if self.cfg.env:
                    env = {**os.environ, **self.cfg.env}
                params = StdioServerParameters(
                    command=self.cfg.command,
                    args=self.cfg.args,
                    env=env,
                    cwd=self.cfg.cwd or None,
                )
                cm = stdio_client(params)
                self._stream_cm = cm
                self._streams = await cm.__aenter__()

            read, write = self._streams
            session = ClientSession(read, write)
            self._session = await session.__aenter__()
            await self._session.initialize()

            result = await self._session.list_tools()
            self.tools = [t.to_mcp_tool() if hasattr(t, "to_mcp_tool") else _tool_to_dict(t)
                          for t in result.tools]
            self.status = "connected"
            logger.info("MCP server %s connected, %d tools",
                        self.name, len(self.tools))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.status = "error"
            self.error = str(exc)[:500]
            logger.exception("MCP server %s connect failed", self.name)
            await self.close()

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if self._session is None:
            return f"[mcp {self.name}: not connected]"
        result = await self._session.call_tool(name, arguments or {})
        return _call_result_to_text(result)

    async def close(self) -> None:
        for obj in (self._session, self._stream_cm):
            if obj is None:
                continue
            try:
                await obj.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        self._session = None
        self._stream_cm = None
        self._streams = None
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http_client = None
        self.status = "idle"

    def to_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.cfg.transport,
            "url": self.cfg.url,
            "command": self.cfg.command,
            "enabled": self.cfg.enabled,
            "status": self.status,
            "error": self.error,
            "tools_count": len(self.tools),
            "tools": [t["name"] for t in self.tools],
        }


def _tool_to_dict(tool: Any) -> Dict[str, Any]:
    """兼容 mcp 2.x Tool 对象 → MCP tools dict。"""
    try:
        schema = tool.inputSchema
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump(exclude_none=True)
        elif isinstance(schema, dict):
            schema = dict(schema)
        else:
            schema = {"type": "object", "properties": {}}
        return {"name": tool.name, "description": tool.description or "", "inputSchema": schema}
    except Exception:  # noqa: BLE001
        return {"name": getattr(tool, "name", "?"), "description": "",
                "inputSchema": {"type": "object", "properties": {}}}


def _call_result_to_text(result: Any) -> str:
    """把 MCP CallToolResult 的 content blocks 转成文本。"""
    parts: List[str] = []
    content = getattr(result, "content", None) or []
    for item in content:
        if getattr(item, "type", "") == "text":
            parts.append(getattr(item, "text", "") or "")
        elif getattr(item, "type", "") == "image":
            parts.append(f"[image data: {len(getattr(item, 'data', b''))} bytes]")
        else:
            try:
                parts.append(json.dumps(item, ensure_ascii=False, default=str))
            except Exception:  # noqa: BLE001
                parts.append(str(item))
    if getattr(result, "isError", False):
        parts.append(f"[mcp tool error: {getattr(result, 'error', '') or 'unknown'}]")
    return "\n".join(parts) if parts else "(empty result)"


class McpClientManager:
    """管理所有第三方 MCP server 连接，并把其 tools 注册进 SkillRegistry。"""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._connections: Dict[str, McpConnection] = {}
        self._lock = asyncio.Lock()

    # ---------------- 配置 ----------------
    def load_config(self) -> List[McpServerConfig]:
        if not self._config_path.exists():
            return []
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("mcp_servers.json 解析失败: %s", self._config_path)
            return []
        servers = raw.get("servers", []) if isinstance(raw, dict) else raw
        out: List[McpServerConfig] = []
        for item in servers:
            try:
                out.append(McpServerConfig(**item))
            except TypeError:
                logger.warning("忽略非法 MCP server 配置: %s", item)
        return out

    def save_config(self, servers: List[McpServerConfig]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps({"servers": [asdict(s) for s in servers]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    # ---------------- 生命周期 ----------------
    async def connect_all(self, registry) -> int:
        """连接所有 enabled 的 server，注册其 tools 为 skills。返回成功连接数。"""
        ok = 0
        for cfg in self.load_config():
            if cfg.enabled:
                try:
                    await self.connect(cfg.name, registry)
                    ok += 1
                except Exception:  # noqa: BLE001
                    logger.exception("connect_all: %s failed", cfg.name)
        return ok

    async def connect(self, name: str, registry) -> McpConnection:
        """连接指定 server 并注册其 tools 为 skills。连接失败不抛出。"""
        async with self._lock:
            cfg = next((c for c in self.load_config() if c.name == name), None)
            if cfg is None:
                raise KeyError(f"MCP server {name} 未配置")
            err = cfg.validate()
            if err:
                raise ValueError(err)
            await self.disconnect(name)
            conn = McpConnection(cfg)
            self._connections[name] = conn
            await conn.connect()
            self._sync_skills(conn, registry)
            return conn

    async def disconnect(self, name: str) -> None:
        conn = self._connections.pop(name, None)
        if conn is not None:
            await conn.close()

    async def reconnect(self, name: str, registry) -> McpConnection:
        return await self.connect(name, registry)

    async def shutdown(self) -> None:
        for name in list(self._connections.keys()):
            await self.disconnect(name)

    # ---------------- skills 同步 ----------------
    def _sync_skills(self, conn: McpConnection, registry) -> None:
        # 先移除该 server 旧的 skills（若注册表里有）
        prefix = f"mcp{_SKILL_SEP}{conn.name}{_SKILL_SEP}"
        for sk in list(registry.list(enabled_only=False)):
            if sk.name.startswith(prefix):
                registry.unregister(sk.name)
        # 注册新 tools
        for tool in conn.tools:
            full = skill_name(conn.name, tool["name"])
            registry.register(Skill(
                name=full,
                description=tool.get("description") or f"第三方 MCP 工具 {tool['name']}",
                input_schema=tool.get("inputSchema") or {"type": "object", "properties": {}},
                handler=self._make_handler(conn, tool["name"]),
                source=f"mcp:{conn.name}",
                tags=["mcp", conn.name],
                meta={"mcp_server": conn.name, "mcp_tool": tool["name"]},
            ))

    def _make_handler(self, conn: McpConnection, tool_name: str):
        async def _handler(args: Dict[str, Any]) -> str:
            return await conn.call_tool(tool_name, args)
        return _handler

    # ---------------- 查询 ----------------
    def list_status(self) -> List[Dict[str, Any]]:
        statuses = [c.to_status() for c in self._connections.values()]
        seen = {s["name"] for s in statuses}
        for cfg in self.load_config():
            if cfg.name not in seen:
                statuses.append(cfg.to_status())
        statuses.sort(key=lambda s: s["name"])
        return statuses

    def get(self, name: str) -> Optional[McpConnection]:
        return self._connections.get(name)
