"""能碳一体机 · 云端 MQTT Broker (nengtan-cloud-broker)。

基于 amqtt 0.12（hbmqtt 改名后的社区维护版），同时监听：
    - TCP 41883 : 平台/边缘盒子采集程序连接（数据面主通道）
    - WS  41083 : WebSocket 通道

数据链路: 边缘盒子 box-mapper/采集程序 → 本 Broker(41883) → 平台订阅 data/#
  同步读数; 同时 collector.py 订阅 # 落盘。

与 box-deploy（边缘盒子本地 mosquitto 1883）相互独立，端口按全局规范使用 40000+。

systemd: nengtan-cloud-broker.service
"""
from __future__ import annotations

import asyncio
import logging
import os

import amqtt  # noqa: F401  确保依赖存在，报错清晰

# amqtt 日志默认较吵，只保留 broker 关键日志
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

BIND_TCP = os.getenv("BIND_TCP", "0.0.0.0:41883")   # TCP 主通道
BIND_WS = os.getenv("BIND_WS", "0.0.0.0:41083")     # WebSocket 通道
MAX_CONNS = int(os.getenv("MAX_CONNS", "1000"))


async def main() -> None:
    from amqtt.broker import Broker

    config = {
        "listeners": {
            "tcp": {
                "type": "tcp",
                "bind": BIND_TCP,
                "max_connections": MAX_CONNS,
            },
            "ws": {
                "type": "ws",
                "bind": BIND_WS,
                "max_connections": MAX_CONNS,
            },
        },
        "sys_interval": 10,
        # 允许匿名连接（与参考项目一致；如需鉴权改为 password-file 见 amqtt 文档）
        "auth": {"allow-anonymous": True},
        "plugins": [
            "amqtt.plugins.authentication.AnonymousAuthPlugin",
            "amqtt.plugins.logging.PacketLogger",
        ],
    }
    broker = Broker(config)
    await broker.start()
    print(f"[broker] amqtt Broker 已启动: TCP {BIND_TCP} / WS {BIND_WS}", flush=True)
    try:
        # 常驻（Broker.start 内部已有循环，这里仅防主协程退出）
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
