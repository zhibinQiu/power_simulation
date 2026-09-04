"""帮助中心路由：提供独立文档网站（docs-site）的访问地址。

宣传手册 / 使用手册 / 技术文档已从平台前端脱离，作为独立站点由 docs-site
项目承载。平台帮助菜单通过本接口获取跳转地址。

对外访问地址固定使用【公网地址】（环境变量 DOCS_PUBLIC_HOST 可覆盖，默认
36.151.146.71），而非浏览器当前访问的 host——公网用户经
http://36.151.146.71:40184 访问（文档站容器与平台同机直出，compose 映射
40184:40183；环境变量 DOCS_SITE_PORT 默认 40184，遵循项目 40000+ 端口规范），
内网用户同样可达。前端兜底推导地址同理应使用该公网地址。
"""
from __future__ import annotations

import json
import os
import time

from fastapi import APIRouter

router = APIRouter()

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config")
_DEVICES_PATH = os.path.join(_CONFIG_DIR, "box_devices.json")
_BROKER_CFG_PATH = os.path.join(_CONFIG_DIR, "box_config.json")
_DEFAULT_CLOUD_HOST = "36.151.146.71"
# 文档站公网入口（36.151.146.71:40184，与平台同机直出；原 frp 隧道方案已下线），
# 可经环境变量 DOCS_PUBLIC_HOST 覆盖（如切换公网地址时）。
_DEFAULT_PUBLIC_HOST = os.getenv("DOCS_PUBLIC_HOST", "").strip() or "36.151.146.71"


# 文档站对外地址缓存（60s TTL）：地址不常变，避免每次请求重复读盘解析。
_cloud_host_cache = ""
_cloud_host_ts = 0.0
_HOST_TTL = 60.0


def cloud_host() -> str:
    """返回文档站对外访问地址（TTL 缓存）。

    文档站公网入口与平台同机（36.151.146.71:40184），跳转链接固定使用公网地址
    （DOCS_PUBLIC_HOST 优先，默认 36.151.146.71），不再使用云端内网 IP。
    """
    global _cloud_host_cache, _cloud_host_ts
    now = time.monotonic()
    if _cloud_host_cache and now - _cloud_host_ts < _HOST_TTL:
        return _cloud_host_cache
    _cloud_host_cache = _resolve_cloud_host()
    _cloud_host_ts = now
    return _cloud_host_cache


def _resolve_cloud_host() -> str:
    public = os.getenv("DOCS_PUBLIC_HOST", "").strip() or _DEFAULT_PUBLIC_HOST
    if public:
        return public
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
    docs_port = int(os.getenv("DOCS_SITE_PORT", "40184"))
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
