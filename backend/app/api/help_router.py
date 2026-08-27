"""帮助中心路由：提供独立文档网站（docs-site）的访问地址。

宣传手册 / 使用手册 / 技术文档已从平台前端脱离，作为独立站点由 docs-site
项目承载（构建产物 dist 经静态服务托管，端口见环境变量 DOCS_SITE_PORT，
默认 40183，遵循项目 40000+ 端口规范）。平台帮助菜单通过本接口获取跳转地址。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/help/site")
async def help_site(request: Request):
    """返回独立文档网站的访问地址（宣传手册/使用手册/技术文档）。"""
    docs_port = int(os.getenv("DOCS_SITE_PORT", "40183"))
    host = (request.headers.get("host") or "").split(":")[0] or "127.0.0.1"
    proto = request.headers.get("x-forwarded-proto", "http")
    return {
        "url": f"{proto}://{host}:{docs_port}",
        "port": docs_port,
        "routes": {
            "home": "/#/",
            "promo": "/#/promo",
            "manual": "/#/manual",
            "tech": "/#/tech",
        },
    }
