"""MCP Server —— 向外提供服务。

本系统作为 MCP Server，把 SkillRegistry 中的 skills（内置 + MCP 接入的）
以 MCP 协议对外暴露，供第三方 MCP 客户端（Claude Desktop、Cursor、其它
AI 应用等）调用，实现「向外提供服务」。

运行方式：
  python -m app.skills.mcp_server                 # stdio（默认，供外部客户端子进程接入）
  python -m app.skills.mcp_server --http          # streamable-http，监听 0.0.0.0:42888

主进程（FastAPI）也可在启动时按 backend/config/mcp_server.json 配置在后台
启动 HTTP 服务（见 start_in_background）。
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from .base import SkillRegistry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "mcp_server.json"
DEFAULT_HTTP_PORT = 42888


def build_server(registry: SkillRegistry, name: str = "本析智擎") -> MCPServer:
    """把注册表中的全部 skills 注册为 MCP 工具，返回 MCPServer。"""
    server = MCPServer(
        name=name,
        description=("本析智擎 · 能碳智控平台能力服务：设备实时读数/历史查询、"
                     "工艺仿真、碳市场行情与预测、排放因子；以及碳计算方法学"
                     "（碳排放量核算、市场周期判断、碳价预测、CEA 结转测算、"
                     "履约合规评估、履约策略推荐、企业碳资产台账）等。"),
        version="1.1.0",
    )
    for skill in registry.list(enabled_only=True):
        _register_skill(server, skill)
    return server


def _register_skill(server: MCPServer, skill) -> None:
    """把单个 skill 包装成 MCP 工具。入参以 JSON Schema 文本嵌入描述。"""
    schema_text = json.dumps(skill.input_schema, ensure_ascii=False)
    description = (f"{skill.description}\n\n"
                   f"参数 JSON Schema: {schema_text}")

    async def _tool_impl(args: Optional[dict] = None) -> str:
        return await registry_execute(skill.name, args or {})

    server.add_tool(_tool_impl, name=skill.name, description=description)
    logger.debug("mcp server registered tool: %s", skill.name)


async def registry_execute(name: str, args: Dict[str, Any]) -> str:
    """由模块级注册表执行（兼容闭包写法）。"""
    from .registry import get_registry
    return await get_registry().execute(name, args)


def load_server_config() -> Dict[str, Any]:
    cfg_path = DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("mcp_server.json 解析失败")
        return {}


async def start_http_server(registry: SkillRegistry, host: str = "0.0.0.0",
                            port: int = DEFAULT_HTTP_PORT, path: str = "/mcp") -> None:
    """后台启动 streamable-http 模式 MCP 服务（供主进程集成）。"""
    server = build_server(registry)
    await server.run_streamable_http_async(host=host, port=port, path=path)


def run_forever(transport: str, host: str, port: int, path: str) -> None:
    from .registry import get_registry
    registry = get_registry()
    server = build_server(registry)
    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=host, port=port, path=path)


def main() -> None:
    from .registry import init_registry  # noqa: F401  # 触发初始化

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="本析智擎 MCP Server（向外提供服务）")
    parser.add_argument("--http", action="store_true", help="以 streamable-http 模式运行")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--path", default="/mcp", help="HTTP 路径")
    args = parser.parse_args()

    transport = "streamable-http" if args.http else "stdio"
    run_forever(transport, args.host, args.port, args.path)


if __name__ == "__main__":
    main()
