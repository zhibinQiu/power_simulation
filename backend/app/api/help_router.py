"""帮助中心路由：提供独立文档网站（docs-site）的访问地址。

宣传手册 / 使用手册 / 技术文档已从平台前端脱离，作为独立站点由 docs-site
项目承载（构建产物 dist 经静态服务托管，端口见环境变量 DOCS_SITE_PORT，
默认 40183，遵循项目 40000+ 端口规范）。平台帮助菜单通过本接口获取跳转地址。

文档站与平台同部署在云端服务器，访问地址固定使用【云端服务 IP】（即云端
Broker/Agent 的 host，配置于 box_devices.json 顶层 cloud.host，回退 broker host），
而非浏览器当前访问的 host（前端可能经本机域名/内网 IP 访问，文档站实际只监听
云端对外 IP）。前端兜底推导地址同理应使用该云端 IP。
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter

router = APIRouter()

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config")
_DEVICES_PATH = os.path.join(_CONFIG_DIR, "box_devices.json")
_BROKER_CFG_PATH = os.path.join(_CONFIG_DIR, "box_config.json")
_DEFAULT_CLOUD_HOST = "172.19.134.45"


def cloud_host() -> str:
    """返回云端服务 IP（文档站实际监听的对外地址）。

    优先 box_devices.json 顶层 cloud.host，回退 broker 配置 host，最后默认云端 IP。
    """
    for path, keys in (
        (_DEVICES_PATH, ("cloud", "host")),
        (_BROKER_CFG_PATH, ("broker", "host")),
    ):
        try:
            with open(path, "r", encoding="utf-8") as f:
                c = json.load(f) or {}
            for k in keys:
                c = c.get(k) or {}
            h = str(c).strip()
            if h:
                return h
        except Exception:  # noqa: BLE001
            pass
    return _DEFAULT_CLOUD_HOST


@router.get("/api/help/site")
async def help_site():
    """返回独立文档网站的访问地址（宣传手册/使用手册/技术文档）。"""
    docs_port = int(os.getenv("DOCS_SITE_PORT", "40183"))
    host = cloud_host()
    return {
        "url": f"http://{host}:{docs_port}",
        "host": host,
        "port": docs_port,
        "routes": {
            "home": "/#/",
            "promo": "/#/promo",
            "manual": "/#/manual",
            "tech": "/#/tech",
        },
    }
