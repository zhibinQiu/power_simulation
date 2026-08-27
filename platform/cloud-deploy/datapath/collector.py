"""能碳一体机 · 云端传感器数据落盘接收器 (nengtan-collector)。

订阅云端 MQTT Broker(41883) 的 '#'，把收到的 payload 按日写入 collected/ 目录。
实现与 backend/app/mqtt_source.py 同源（参照参考项目 deploy_pkg/collect_sensor_data.py）：
    - paho-mqtt，默认 MQTT 5.0（amqtt 0.12 对 MQTT 3.1.1 跨客户端路由有缺陷）
    - 默认订阅 '#'（amqtt 对 'data/#' 前缀通配符路由有缺陷），on_message 过滤 $SYS
    - 唯一 client_id（含 pid），断线自动重连（1s→30s 退避）

systemd: nengtan-collector.service
"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("BROKER_PORT", "41883"))
BROKER_USER = os.getenv("BROKER_USER", "")
BROKER_PASS = os.getenv("BROKER_PASS", "")
TOPICS = os.getenv("MQTT_TOPICS", "#")
OUT_DIR = Path(os.getenv("OUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "collected")))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("collector")


def _today_file() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"


def _record(topic: str, payload: bytes) -> None:
    ts = datetime.now().isoformat(timespec="milliseconds")
    text = payload.decode("utf-8", errors="replace")
    line = json.dumps({"ts": ts, "topic": topic, "payload": text}, ensure_ascii=False)
    try:
        with _today_file().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:  # 落盘失败不影响订阅主循环
        log.warning("写盘失败: %s", e)


def on_connect(client: mqtt.Client, userdata, flags, rc, properties=None) -> None:
    if rc == 0:
        log.info("已连接 %s:%s (MQTT5=%s), 订阅 %s", BROKER_HOST, BROKER_PORT, mqtt.MQTTv5, TOPICS)
        client.subscribe(TOPICS, qos=0)
    else:
        log.warning("连接失败 rc=%s, 将重试", rc)


def on_disconnect(client: mqtt.Client, userdata, rc, properties=None) -> None:
    if rc != 0:
        log.warning("意外断开 (rc=%s), 自动重连", rc)


def on_message(client: mqtt.Client, userdata, msg) -> None:
    if msg.topic.startswith("$SYS"):  # 过滤系统主题
        return
    _record(msg.topic, msg.payload)
    log.debug("[%s] %s %s", msg.topic, len(msg.payload), msg.payload[:120])


def main() -> None:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"nengtan-cloud-collector-{os.getpid()}-{random.randint(1000, 9999)}",
        protocol=mqtt.MQTTv5,
        clean_session=True,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    if BROKER_USER:
        client.username_pw_set(BROKER_USER, BROKER_PASS)
    client.reconnect_delay_set(min_delay=1, max_delay=30)  # 1s→30s 退避

    log.info("启动 collector: %s:%s topics=%s out=%s", BROKER_HOST, BROKER_PORT, TOPICS, OUT_DIR)
    while True:
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:  # noqa: BLE001 重连兜底
            log.warning("连接异常 %s, 5s 后重试", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
