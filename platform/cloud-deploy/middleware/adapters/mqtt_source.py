"""内置适配器 mqtt：订阅外部 MQTT Broker → 标准 MQTT（平台规范）。

适用：外部系统本身就是 MQTT，但 Broker 与平台订阅 Broker 不同（最常见场景）。
逻辑：订阅外部主题 → 收到 JSON 即 emit_flat（展平+字段改名+数值过滤）；
收到非 JSON 纯数值/纯文本则按主题末段作属性名、配置默认 device 发布。
断线由 paho loop_start 自动重连。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict

import paho.mqtt.client as mqtt

from middleware.adapters.base import BaseAdapter, numeric


class MqttSourceAdapter(BaseAdapter):
    def __init__(self, cfg: Dict[str, Any], bridge: Any, logger: Any = None):
        super().__init__(cfg, bridge, logger)
        b = self.cfg.get("broker") or {}
        self.host = str(b.get("host") or "")
        self.port = int(b.get("port") or 1883)
        self.username = str(b.get("username") or "")
        self.password = str(b.get("password") or "")
        self.topics = list(self.cfg.get("topics") or [])
        self.qos = int(self.cfg.get("qos", 0))
        self._client: Any = None

    def validate(self) -> list:
        errors = super().validate()
        if not self.host:
            errors.append(f"adapter[{self.id}].broker.host 不能为空")
        if not self.topics:
            errors.append(f"adapter[{self.id}].topics 不能为空")
        return errors

    def _on_connect(self, client, userdata, flags, rc, *extra):
        code = getattr(rc, "value", rc)
        if int(code) == 0:
            for t in self.topics:
                client.subscribe(t, qos=self.qos)
            self.log("info", f"[{self.id}] 已连接外部 Broker {self.host}:{self.port}，订阅 {self.topics}")
            self.stats["last_error"] = ""
        else:
            self.stats["last_error"] = f"连接外部 Broker 失败 rc={rc}"

    def _on_message(self, client, userdata, msg):
        try:
            text = (msg.payload or b"").decode("utf-8", "replace").strip()
            if not text:
                return
            try:
                obj = json.loads(text)
            except ValueError:
                obj = None
            if isinstance(obj, dict):
                n = self.emit_flat(obj)
                if n == 0 and self.cfg.get("device"):
                    # JSON 但无数值字段：尝试整段数值
                    v = numeric(text)
                    if v is not None:
                        self.emit(msg.topic.rstrip("/").split("/")[-1], v)
            elif self.cfg.get("device"):
                v = numeric(text)
                if v is not None:
                    self.emit(msg.topic.rstrip("/").split("/")[-1], v)
            else:
                self.stats["skipped"] += 1
        except Exception as e:  # noqa: BLE001
            self.stats["errors"] += 1
            self.stats["last_error"] = f"处理外部消息异常: {e}"
            self.log("error", f"[{self.id}] {e}")

    def test(self) -> Dict[str, Any]:
        """真实探测外部 Broker：TCP 连接 + MQTT CONNECT（5 秒超时）。"""
        errors = self.validate()
        if errors:
            return {"ok": False, "message": "；".join(errors)}
        kwargs = {}
        if getattr(mqtt, "CallbackAPIVersion", None) is not None:  # paho>=2.0
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        probe: Dict[str, Any] = {"rc": None}
        try:
            client = mqtt.Client(client_id=f"carbon-mw-probe-{uuid.uuid4().hex[:8]}",
                                 protocol=mqtt.MQTTv311, **kwargs)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"创建探测客户端失败：{e}"}
        if self.username:
            client.username_pw_set(self.username, self.password)

        def _on_connect(c, u, flags, rc, *extra):
            probe["rc"] = getattr(rc, "value", rc)

        client.on_connect = _on_connect
        try:
            client.connect_async(self.host, self.port, keepalive=10)
            client.loop_start()
            for _ in range(50):  # 5s
                if probe["rc"] is not None:
                    break
                time.sleep(0.1)
            rc = probe["rc"]
            if rc is None:
                return {"ok": False,
                        "message": f"连接 {self.host}:{self.port} 超时（5 秒无响应）"}
            if int(rc) != 0:
                return {"ok": False,
                        "message": f"连接 {self.host}:{self.port} 被拒绝 rc={rc}"
                                   f"（检查地址/端口/用户名密码）"}
            return {"ok": True,
                    "message": f"外部 Broker {self.host}:{self.port} 连通，将订阅 {self.topics}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"连接 {self.host}:{self.port} 失败：{e}"}
        finally:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    def start(self) -> None:
        if not self.host or not self.topics:
            raise RuntimeError(f"adapter[{self.id}] 配置不完整（host/topics）")
        kwargs = {}
        if getattr(mqtt, "CallbackAPIVersion", None) is not None:  # paho>=2.0
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        self._client = mqtt.Client(
            client_id=f"carbon-mw-src-{self.id}-{os.getpid()}-{uuid.uuid4().hex[:6]}",
            protocol=mqtt.MQTTv311, **kwargs,
        )
        if self.username:
            self._client.username_pw_set(self.username, self.password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()
        self.running = True
        self.stats["started_at"] = time.time()
        self.log("info", f"[{self.id}] 外部 MQTT 适配器启动（box={self.box}）")

    def stop(self) -> None:
        super().stop()
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        self.log("info", f"[{self.id}] 外部 MQTT 适配器已停止")
