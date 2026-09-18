"""标准 MQTT 输出桥：按「能碳平台外部数据源接入规范」发布到平台订阅的同一 Broker。

任何外部源经中间件转换为标准消息：
  主题   data/{box}/{device}/{device}/{property}
  payload {"v": 数值, "t": 毫秒, "device":..., "box":..., "prop":..., "src": "external"}

bridge 不依赖平台任何代码；paho 客户端线程安全，适配器可直接并发 publish。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

_CLIENT_ID_PREFIX = "carbon-middleware"


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_ts(ts: Any) -> Optional[int]:
    """把 ts 归一为毫秒时间戳；无法解析返回 None（发布器取当前时刻）。"""
    if ts is None:
        return None
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    if t < 1e12:            # 秒 → 毫秒
        t *= 1000
    return int(t)


def compose_message(box: str, device: str, prop: str, value: float,
                    ts: Optional[int] = None) -> "tuple[str, str]":
    """组装 (topic, payload_json)。value 必须为 int/float（调用方已过滤）。"""
    t_ms = ts if ts is not None else now_ms()
    topic = f"data/{box}/{device}/{device}/{prop}"
    payload = json.dumps({
        "v": value, "t": t_ms, "device": device,
        "box": box, "prop": prop, "src": "external",
    }, ensure_ascii=False)
    return topic, payload


class OutputBridge:
    """数据输出桥：paho 直发 output.broker（唯一输出形态）。

    服务器上 output.broker 即同机云端 Broker :41883，与一体机上报同一 Broker、
    按主题前缀区分；断线由 loop_start 自动重连，适配器只管 publish()。
    """

    def __init__(self, out_cfg: Dict[str, Any], logger: Any = None):
        out_cfg = out_cfg or {}
        self.log = logger or (lambda *a: None)
        broker = (out_cfg or {}).get("broker") or {}
        self.host = str(broker.get("host") or "127.0.0.1")
        self.port = int(broker.get("port") or 41883)
        self.username = str(broker.get("username") or "")
        self.password = str(broker.get("password") or "")
        self.qos = int((out_cfg or {}).get("qos", 0))
        self.connected = False
        self.publish_ok = 0
        self.publish_fail = 0
        self.last_error = ""
        self._client: Any = None
        kwargs = {}
        if getattr(mqtt, "CallbackAPIVersion", None) is not None:  # paho>=2.0
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        self._client = mqtt.Client(
            client_id=f"{_CLIENT_ID_PREFIX}-{os.getpid()}-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv311, **kwargs,
        )
        if self.username:
            self._client.username_pw_set(self.username, self.password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        try:
            self._client.connect_async(self.host, self.port, keepalive=30)
        except Exception as e:  # noqa: BLE001
            self.last_error = f"连接目标 Broker 失败: {e}"
        self._client.loop_start()

    # 兼容 paho 1.6 / 2.x 回调签名
    def _on_connect(self, client, userdata, flags, rc, *extra):
        code = getattr(rc, "value", rc)
        self.connected = (int(code) == 0)
        if not self.connected:
            self.last_error = f"连接失败 rc={rc}"
        else:
            self.last_error = ""

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        self.last_error = "与平台 Broker 断线，paho 将自动重连"

    def publish(self, box: str, device: str, prop: str, value: float,
                ts: Optional[int] = None) -> bool:
        """按标准规范发布一条读数；返回是否投递成功（rc==0）。"""
        try:
            topic, payload = compose_message(box, device, prop, value,
                                             ts if ts is not None else now_ms())
            info = self._client.publish(topic, payload, qos=self.qos)
            ok = bool(getattr(info, "rc", 0) == mqtt.MQTT_ERR_SUCCESS)
        except Exception as e:  # noqa: BLE001
            ok = False
            self.last_error = f"发布失败: {e}"
        if ok:
            self.publish_ok += 1
        else:
            self.publish_fail += 1
        return ok

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "publish_ok": self.publish_ok,
            "publish_fail": self.publish_fail,
            "last_error": self.last_error,
            "broker": f"{self.host}:{self.port}",
        }

    def stop(self) -> None:
        if self._client is None:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass
