"""能碳一体机 · 云端传感器数据接收器 (nengtan-collector)。

订阅云端 MQTT Broker(41883) 的 '#'，双通道处理：
    - 落盘：全部主题 payload 按日写入 collected/ 目录（JSON lines，原始数据全量保留）
    - 时序库：解析 data/{box}/{device}/{instance}/{property} 设备读数，批量写入
      云端 TDengine（nengtan.readings 超表，见 deploy_cloud.sh --tsdb-only）；
      写失败不阻塞订阅主循环（原始数据仍有落盘兜底）
实现与 backend/app/mqtt_source.py 同源（参照参考项目 deploy_pkg/collect_sensor_data.py）：
    - paho-mqtt，MQTT 3.1.1（amqtt 0.12 实测对 MQTT 5.0 连接返回 Unsupported protocol version，v3.1.1 才正常）
    - 默认订阅 '#'（amqtt 对 'data/#' 前缀通配符路由有缺陷），on_message 过滤 $SYS
    - 唯一 client_id（含 pid），断线自动重连（1s→30s 退避）
    - on_connect/on_disconnect 用 paho 2.x 兼容签名（v3.1.1 下多出的形参用 *args 兜底）

环境变量（TDengine 写入，均可选，默认本地 127.0.0.1:6041）：
    TSDB_ENABLED  默认 1；设 0 关闭时序写入（仅落盘）
    TSDB_URL      taosadapter REST 地址，默认 http://127.0.0.1:6041
    TSDB_USER     默认 root；TSDB_PASS 默认 taosdata
    TSDB_DB       默认 nengtan

systemd: nengtan-collector.service
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import sys
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("BROKER_PORT", "41883"))
BROKER_USER = os.getenv("BROKER_USER", "")
BROKER_PASS = os.getenv("BROKER_PASS", "")
TOPICS = os.getenv("MQTT_TOPICS", "#")
OUT_DIR = Path(os.getenv("OUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "collected")))

# ------------------------- TDengine 时序写入 -------------------------
TSDB_ENABLED = os.getenv("TSDB_ENABLED", "1") == "1"
TSDB_URL = os.getenv("TSDB_URL", "http://127.0.0.1:6041").rstrip("/")
TSDB_USER = os.getenv("TSDB_USER", "root")
TSDB_PASS = os.getenv("TSDB_PASS", "taosdata")
TSDB_DB = os.getenv("TSDB_DB", "nengtan")
TSDB_STABLE = f"{TSDB_DB}.readings"
_TS_BUF: "deque[str]" = deque(maxlen=4096)  # 待写入的行 (ts,value,'box',...) 转义后片段
_TS_LOCK = threading.Lock()
_TS_FLUSH_SEC = 1.0  # 批量冲刷间隔
_TS_MAX_BATCH = 512  # 单次批量最大行数

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


# ------------------------- TDengine 时序写入 -------------------------

def _esc(s: str) -> str:
    """NCHAR 字符串单引号转义（' → ''），防 SQL 注入。"""
    return str(s).replace("'", "''")


def _ts_record(topic: str, payload: bytes) -> None:
    """解析 data/{box}/{device}/{instance}/{property} 读数并入时序缓冲。

    非 data/ 主题、非数值 payload 一律跳过（原始数据仍由落盘保留）。
    """
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "data":
        return
    raw = payload.decode("utf-8", errors="replace").strip()
    value = None
    try:
        value = float(raw)
    except (ValueError, TypeError):
        # 兼容 JSON payload: {"weight":0.54} / {"value":1.2} / {"val":3}
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k in ("value", "val", "weight", "reading", "data"):
                    if k in obj and obj[k] not in (None, ""):
                        try:
                            value = float(obj[k]); break
                        except (ValueError, TypeError):
                            continue
        except Exception:
            value = None
    if value is None or value != value:  # NaN / 无法解析
        return
    ts_ms = int(time.time() * 1000)
    box, device, instance, prop = (_esc(parts[1]), _esc(parts[2]), _esc(parts[3]), _esc(parts[4]))
    with _TS_LOCK:
        _TS_BUF.append((box, device, instance, prop, ts_ms, value))


def _ts_flush() -> None:
    """把缓冲批量写入 TDengine（REST /rest/sql）。失败仅告警，原始数据有落盘兜底。"""
    if not TSDB_ENABLED:
        return
    with _TS_LOCK:
        rows = list(_TS_BUF)
        _TS_BUF.clear()
    if not rows:
        return
    groups = {}
    for (box, device, instance, prop, ts_ms, value) in rows:
        groups.setdefault((box, device, instance, prop), []).append(
            f"({ts_ms},{value!r})")
    for (box, device, instance, prop), vals in groups.items():
        subtable = f"t_{box}_{device}_{instance}_{prop}".replace("-", "_")
        sql = (f"INSERT INTO {subtable} USING {TSDB_STABLE} "
               f"TAGS('{box}','{device}','{instance}','{prop}') VALUES "
               + " ".join(vals))
        auth = base64.b64encode(f"{TSDB_USER}:{TSDB_PASS}".encode()).decode()
        req = urllib.request.Request(
            f"{TSDB_URL}/rest/sql/{TSDB_DB}", data=sql.encode("utf-8"), method="POST",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "text/plain"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if data.get("code", 0) != 0:
                log.warning("TDengine 写入失败: %s (%s)", data.get("desc"), sql[:160])
            else:
                log.info("TDengine 已写入 %d 行", len(vals))
        except Exception as e:  # noqa: BLE001 TDengine 不可用不影响订阅主循环
            log.warning("TDengine 写入异常: %s", e)
            return


def _ts_flush_worker() -> None:
    while True:
        time.sleep(_TS_FLUSH_SEC)
        try:
            _ts_flush()
        except Exception:  # noqa: BLE001
            pass


def on_connect(client, userdata, flags, rc, properties=None, *args) -> None:
    if rc == 0:
        log.info("已连接 %s:%s, 订阅 %s", BROKER_HOST, BROKER_PORT, TOPICS)
        client.subscribe(TOPICS, qos=0)
    else:
        log.warning("连接失败 rc=%s, 将重试", rc)


def on_disconnect(client, userdata, *args) -> None:
    rc = args[0] if args else 0
    if rc != 0:
        log.warning("意外断开 (rc=%s), 自动重连", rc)


def on_message(client: mqtt.Client, userdata, msg) -> None:
    if msg.topic.startswith("$SYS"):  # 过滤系统主题
        return
    _record(msg.topic, msg.payload)
    _ts_record(msg.topic, msg.payload)
    log.debug("[%s] %s %s", msg.topic, len(msg.payload), msg.payload[:120])


def main() -> None:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"nengtan-cloud-collector-{os.getpid()}-{random.randint(1000, 9999)}",
        protocol=mqtt.MQTTv311,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    if BROKER_USER:
        client.username_pw_set(BROKER_USER, BROKER_PASS)
    client.reconnect_delay_set(min_delay=1, max_delay=30)  # 1s→30s 退避

    log.info("启动 collector: %s:%s topics=%s out=%s", BROKER_HOST, BROKER_PORT, TOPICS, OUT_DIR)
    if TSDB_ENABLED:
        threading.Thread(target=_ts_flush_worker, daemon=True).start()
        log.info("TDengine 时序写入已开启: %s stable=%s", TSDB_URL, TSDB_STABLE)
    while True:
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:  # noqa: BLE001 重连兜底
            log.warning("连接异常 %s, 5s 后重试", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
