# -*- coding: utf-8 -*-
"""运行环境网络信息推导（不在任何配置里写死局域网/本地地址）。

平台有两处「访问宿主上的服务」，都需要一个兜底地址：
- cloud_agent：平台 ⇄ 云端 cloud-agent（HTTP 42083）
- middleware_client：平台 ⇄ 数据中间件（HTTP 42084）

生产形态下平台跑在容器里、服务跑在同一台宿主上，容器访问宿主必须走 docker 网关
（172.17.0.1 / 172.18.0.1 …随 docker 网络而变，写死则在别的机器/网络必错）；
而开发机（mac 本地起后端）根本没有这个网关。

因此这里不把地址放进配置文件，而是**运行时推导**：
1. 环境变量 BROKER_HOST（部署编排显式指定时优先，与 mqtt_source 口径一致）；
2. Linux /proc/net/route 的默认路由网关（容器内即 docker 网关）；
3. 推导不到返回空串，调用方跳过该候选（配置文件里的公网地址才是主候选）。
"""
from __future__ import annotations

import os


def gateway_host() -> str:
    """宿主网关地址（推导不到返回空串）。"""
    env = os.environ.get("BROKER_HOST", "").strip()
    if env:
        return env
    try:
        with open("/proc/net/route", "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                # Destination=00000000 即默认路由；Gateway 为小端十六进制
                if len(parts) > 2 and parts[1] == "00000000":
                    gw = int(parts[2], 16)
                    if gw:
                        return ".".join(str((gw >> (8 * i)) & 0xFF) for i in range(4))
    except Exception:  # noqa: BLE001
        return ""
    return ""
