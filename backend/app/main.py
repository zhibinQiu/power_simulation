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
- 启动实时数据源（MQTT 订阅）与设备历史预填

迁移某业务域时，只需整体搬走对应 api/*_router.py 及其依赖模块，无需改动本文件。
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import mqtt_source
from . import presets
from . import realtime
from .api.box_router import router as box_router
from .api.carbon_assets_router import router as carbon_assets_router
from .api.carbon_assets_router import share_router as report_share_router
from .api.help_router import router as help_router
from .api.license_router import router as license_router
from .api.simulation_router import router as simulation_router

app = FastAPI(title="工业能碳智控平台", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# 业务域路由（保持原有 /api 路径兼容）
app.include_router(simulation_router)          # 核心仿真（预置/解析/仿真/策略/扫描/审计/聊天/AI 优化）
app.include_router(box_router)                 # 能碳一体机管理
app.include_router(carbon_assets_router)       # 碳资产管理（含 /api/carbon-assistant/*）
app.include_router(help_router)                # 帮助中心（独立文档网站地址）
app.include_router(license_router)             # 平台激活（激活码校验 / 激活状态）
app.include_router(report_share_router)        # 报告分享页 /report/{rid}


def _frontend_dist_dir() -> str:
    """前端构建产物目录。

    PyInstaller 打包后数据文件位于 sys._MEIPASS/frontend/dist（单文件模式为解包临时目录，
    单目录模式为 _internal 目录）；开发环境回退到仓库内相对路径。
    """
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    return os.path.join(base, "frontend", "dist")


FRONTEND_DIST = _frontend_dist_dir()


# ------------------------- 实时遥测（WebSocket + 设备历史） -------------------------
realtime.register_realtime(app)


# ------------------------- 静态托管前端 -------------------------
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010, access_log=False)
