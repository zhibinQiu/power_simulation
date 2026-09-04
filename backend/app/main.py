"""FastAPI 主程序（组合根）：装配各业务域路由 + 静态托管前端。

业务域划分（各路由模块见 backend/app/api/，职责单一、可独立迁移）：
- simulation_router：核心仿真 REST（/api/health、预置模型/解析/仿真/策略 CRUD/扫描/审计/聊天/AI 优化）
- box_router：能碳一体机管理（/api/box/*、/api/realtime/*，含 MQTT 实时数据源）
- carbon_assets_router：碳资产管理（/api/carbon-market/*、/api/market-news、/api/report*、
  /api/carbon-assistant/*）与报告分享页 /report/{rid}

本文件只做组合装配（组合根 / Composition Root），不含业务实现：
- 注册 CORS 与各域路由
- 挂载实时遥测（WebSocket，见 realtime.py）
- 托管前端构建产物（SPA 回退）
- lifespan 内启动实时数据源（MQTT 订阅）与设备历史预填

迁移某业务域时，只需整体搬走对应 api/*_router.py 及其依赖模块，无需改动本文件。
"""
from __future__ import annotations

import os
import sys

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import mqtt_source
from . import presets
from . import realtime
from .api.box_router import router as box_router
from .api.carbon_assets_router import (router as carbon_assets_router,
                                       share_router as report_share_router)
from .api.ai_admin_router import router as ai_admin_router
from .api.chat_session_router import router as chat_session_router
from .api.help_router import router as help_router
from .api.knowledge_router import router as knowledge_router
from .api.license_router import router as license_router
from .api.simulation_router import router as simulation_router
from .api.settings_router import router as settings_router


async def _lifespan(app):
    """应用生命周期：后台初始化 Skills（内置 + MCP）+ 启动 MQTT 实时数据源 + 设备历史预填。

    启动副作用统一收敛于此：import 模块不再产生任何副作用（组合根纯装配），
    便于测试与工具脚本安全导入。
    """
    from .skills.registry import init_registry

    init_registry(connect_mcp=True)
    # 启动实时数据源（MQTT 订阅，参照参考项目 yunduan1 数据链路）：
    # 后台线程连接云端 MQTT Broker 订阅主题（Broker 配置前端化：能碳一体机管理 -> 总览 -> 配置 Broker，
    # 保存后热更新重连并持久化到 box_config.json），设备读数一律来自该真实数据源。
    mqtt_source.start()
    # 启动时为默认流程按 MQTT 真实读数预填设备历史（未上报的设备保持为空，不生成模拟数据）
    try:
        realtime.seed_history(presets.default_model())
    except Exception as _e:  # pragma: no cover
        # 预填失败不打印到命令行，改为前端弹窗通知（前端连接后可见）
        realtime.manager.notify("warn", "设备历史预填未完成", f"启动时按 MQTT 实时读数预填设备历史失败：{_e}")
    yield

app = FastAPI(title="工业能碳智控平台", version="2.0.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# 业务域路由（保持原有 /api 路径兼容）
app.include_router(simulation_router)          # 核心仿真（预置/解析/仿真/策略/扫描/审计/聊天/AI 优化）
app.include_router(ai_admin_router)            # AI 管理（智能体/技能/本体）
app.include_router(chat_session_router)        # 聊天会话（历史对话/继续对话）
app.include_router(box_router)                 # 能碳一体机管理
app.include_router(carbon_assets_router)       # 碳资产管理（含 /api/carbon-assistant/*）
app.include_router(help_router)                # 帮助中心（独立文档网站地址）
app.include_router(knowledge_router)           # 知识库（LLM-WIKI 式多级文件夹 + 文档解析，无需权限）
app.include_router(license_router)             # 平台激活（激活码校验 / 激活状态）
app.include_router(settings_router)            # 系统设置（LLM 配置等）
app.include_router(report_share_router)        # 报告分享页 /report/{rid}


def _frontend_dist_dir() -> str:
    """前端构建产物目录。

    PyInstaller 打包后数据文件位于 sys._MEIPASS/frontend/dist（单文件模式为解包临时目录，
    单目录模式为 _internal 目录）；开发环境回退到仓库内相对路径。
    """
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    return os.path.join(base, "frontend", "dist")


FRONTEND_DIST = _frontend_dist_dir()


# ------------------------- 文档站反向代理（宣传手册/使用手册/技术文档） -------------------------
# 文档站（docs-site，独立 vite 站点）并入平台【同源】访问：浏览器只访问平台端口
# （如 40014），平台后端把 /docs/* 原样转发（保留前缀）到独立文档站服务，
# 页面与静态资源一律经平台出口，不再要求文档站端口（40184）对外开放（云安全组免配）。
# 目标地址用环境变量 DOCS_PROXY_TARGET 覆盖：
#   - 71 生产（steel-twin 容器）：http://docs-site:40183（compose 同网络服务名，见
#     platform/bs-deploy/docker-compose.yml）
#   - 本地开发（默认）：http://127.0.0.1:5174（docs-site vite dev server）
_DOCS_PROXY_TARGET = os.getenv("DOCS_PROXY_TARGET", "http://127.0.0.1:5174").rstrip("/")
_docs_client: httpx.AsyncClient | None = None


def _docs_client_get() -> httpx.AsyncClient:
    """惰性创建转发客户端（上游仅 GET/HEAD 静态服务，复用连接）。"""
    global _docs_client
    if _docs_client is None:
        _docs_client = httpx.AsyncClient(base_url=_DOCS_PROXY_TARGET, timeout=15.0, follow_redirects=False)
    return _docs_client


# 必须声明在下方 SPA catch-all（/{full_path:path}）之前，否则 /docs/* 会被吞进前端回退
@app.api_route("/docs", methods=["GET", "HEAD"])
@app.api_route("/docs/{doc_path:path}", methods=["GET", "HEAD"])
async def docs_site_proxy(doc_path: str = ""):
    """把 /docs/{doc_path} 请求转发到独立文档站，作为平台同源入口。

    上游（docs-site dev server / 容器）以 /docs/ 为 base，路径必须带尾斜杠，
    故 /docs 与 /docs/ 统一转发为 /docs/（首页），子路径为 /docs/{sub}。
    """
    upstream_path = "/docs/" if not doc_path else "/docs/" + doc_path.lstrip("/")
    try:
        upstream = await _docs_client_get().get(upstream_path)
    except httpx.HTTPError:
        return Response(content='{"detail": "docs site unreachable"}', status_code=502, media_type="application/json")
    headers = {k: v for k, v in upstream.headers.items()
               if k.lower() not in ("content-length", "transfer-encoding", "connection", "keep-alive")}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


# ------------------------- 实时遥测（WebSocket + 设备历史） -------------------------
realtime.register_realtime(app)


# ------------------------- 静态托管前端 -------------------------
# assets 子目录可能未构建（如仅 index.html 存在），逐个按存在性挂载，避免后端启动崩溃
_assets_dir = os.path.join(FRONTEND_DIST, "assets")
if os.path.isdir(_assets_dir):
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

# base=/sim/ 双入口兼容：门户域名反代（www.nengyousuan.com/sim/，nginx 剥离 /sim 前缀后
# 走上面的 /assets 或根路径）与 IP:40014 直连（浏览器资源引用为 /sim/*）均需可用。
# 直连时后端须能按 /sim 前缀命中同一份 dist，故此处把 /sim 也挂载到 dist 根目录
# （html=True：/sim/ 返回 index.html，/sim/assets/* 落盘命中）。注册在 SPA catch-all 之前。
if os.path.isdir(FRONTEND_DIST):
    app.mount("/sim", StaticFiles(directory=FRONTEND_DIST, html=True), name="sim-frontend")

if os.path.isdir(FRONTEND_DIST):
    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # 若存在真实静态文件（模型/解码器等），直接返回，避免全部回退 index.html
        candidate = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            # index.html 禁止缓存：每次构建产物 hash 都会变化，缓存旧入口会导致刷新看不到新前端
            return FileResponse(index, headers={"Cache-Control": "no-store"})
        return {"detail": "frontend not built"}


# 启动实时数据源（MQTT 订阅）与设备历史预填已移入 _lifespan，
# import 本模块不再产生启动副作用，保证组合根纯装配。

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010, access_log=False)
