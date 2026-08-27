"""「发测试消息」功能完整测试用例（backend）。

覆盖链路：
  POST /api/box/publish (box_console.publish_test) → mqtt_source.publish（向云端 Broker 发布）
  → Broker 回环到平台订阅线程 → _record_message 解析 → 实时消息流 / 设备读数刷新

运行：
  cd backend && python -m pytest tests/test_publish.py -v
（不需要真实 Broker：publish 用 FakeClient mock，回环解析直接调用 _record_message）
"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import box_console  # noqa: E402
from app import mqtt_source  # noqa: E402

# ---------------------------------------------------------------------------
# 测试替身：FakeClient 模拟 paho 客户端，publish 不连真实 Broker
# ---------------------------------------------------------------------------
class FakeClient:
    """paho 客户端替身：connect/publish 触发对应回调（与真实 paho 行为一致）。"""

    def __init__(self):
        self.published = []
        self.connected = False
        self._cred = None
        self.on_connect = None
        self.on_publish = None

    def username_pw_set(self, u, p=None):
        self._cred = (u, p)

    def connect(self, host, port, keepalive):
        self.connected = True
        if self.on_connect:
            self.on_connect(self, None, None, 0)
        return 0

    def loop_start(self):
        return None

    def loop_stop(self):
        return None

    def disconnect(self):
        self.connected = False

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        if self.on_publish:
            self.on_publish(self, None, 1)
        return SimpleNamespace(rc=0)


class FakeMsg:
    """模拟 paho on_message 的 msg（topic / payload 字节串）。"""

    def __init__(self, topic: str, payload: str):
        self.topic = topic
        self.payload = payload.encode("utf-8")


@pytest.fixture(autouse=True)
def fake_paho(monkeypatch):
    """全局替换 mqtt.Client（publish 直接用 mqtt.Client 创建，带唯一 client_id），保证测试不触网。"""

    fakes = []

    class _FakeCls:
        def __new__(cls, *a, **kw):
            c = FakeClient()
            fakes.append(c)
            return c

    monkeypatch.setattr(mqtt_source.mqtt, "Client", _FakeCls)
    monkeypatch.setattr(mqtt_source, "_PAHO_OK", True)
    return fakes


@pytest.fixture(autouse=True)
def clean_state():
    """每个用例前清空消息流 / 读数 / 云端设备缓存，避免串扰。"""
    with mqtt_source._LOCK:
        mqtt_source.MESSAGE_LOG.clear()
        mqtt_source.READINGS.clear()
        mqtt_source.CLOUD_DEVICES.clear()
    yield
    with mqtt_source._LOCK:
        mqtt_source.MESSAGE_LOG.clear()
        mqtt_source.READINGS.clear()
        mqtt_source.CLOUD_DEVICES.clear()


# ---------------------------------------------------------------------------
# 一、API 层：box_console.publish_test 入参校验
# ---------------------------------------------------------------------------
class TestPublishTestValidation:
    def test_empty_topic_rejected(self):
        """主题为空时必须返回 ok=False 且给出友好错误，不触网。"""
        r = box_console.publish_test({"topic": "  ", "payload": "x"})
        assert r["ok"] is False
        assert "topic" in r.get("error", "").lower()

    def test_topic_stripped(self):
        """主题两端的空白应被去除后再发布。"""
        r = box_console.publish_test({"topic": "  data/box-001/device-1  ", "payload": '{"value":1}'})
        assert r["ok"] is True
        assert r["topic"] == "data/box-001/device-1"

    def test_missing_topic_key_safe(self):
        """缺 topic 字段也不应抛异常。"""
        r = box_console.publish_test({"payload": "{}"})
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 二、MQTT 层：mqtt_source.publish 发布行为
# ---------------------------------------------------------------------------
class TestPublishToBroker:
    def test_publish_success_returns_topic(self, fake_paho):
        """正常发布应返回 ok=True + 实际主题，且把载荷原样交到客户端。"""
        r = mqtt_source.publish("data/box-001/device-1", '{"value":66.6}')
        assert r == {"ok": True, "topic": "data/box-001/device-1"}
        assert len(fake_paho) == 1
        topic, payload, qos = fake_paho[0].published[0]
        assert topic == "data/box-001/device-1"
        assert payload == '{"value":66.6}'

    def test_publish_payload_dict_json_encoded(self, fake_paho):
        """非字符串载荷（dict）应被 JSON 序列化后发布。"""
        mqtt_source.publish("test/dict", {"value": 1.5, "unit": "kW"})
        topic, payload, qos = fake_paho[0].published[0]
        import json
        assert json.loads(payload) == {"value": 1.5, "unit": "kW"}

    def test_publish_no_paho_returns_friendly_error(self, monkeypatch):
        """paho 未安装时应返回友好错误而非抛异常。"""
        monkeypatch.setattr(mqtt_source, "_PAHO_OK", False)
        r = mqtt_source.publish("data/x", "y")
        assert r["ok"] is False
        assert "paho-mqtt" in r.get("error", "")

    def test_publish_broker_unreachable_returns_error(self, monkeypatch):
        """Broker 连接失败时应返回 ok=False + 异常信息，不崩溃。"""
        def _boom(*a, **kw):
            raise ConnectionRefusedError("refused")
        monkeypatch.setattr(mqtt_source.mqtt, "Client", _boom)
        r = mqtt_source.publish("data/x", "y")
        assert r["ok"] is False
        assert "refused" in r.get("error", "")


# ---------------------------------------------------------------------------
# 三、回环解析：_record_message 收到 data/# 消息 → 消息流 + 设备读数
# ---------------------------------------------------------------------------
class TestRecordMessageLoopback:
    def test_data_topic_enters_message_stream(self):
        """data/ 主题消息必须进入实时消息流（MESSAGE_LOG），供前端「实时消息流」展示。"""
        before = mqtt_source._STATE["message_count"]
        mqtt_source._record_message(FakeMsg("data/box-001/device-1", '{"value":88.8}'))
        assert mqtt_source._STATE["message_count"] == before + 1
        assert mqtt_source.MESSAGE_LOG[-1]["topic"] == "data/box-001/device-1"

    def test_data_topic_updates_readings(self):
        """data/ 主题 JSON 数值字段应刷新平台读数：主读数登记在 READINGS[cloud_id] 兼容键。"""
        mqtt_source._record_message(FakeMsg("data/box-001/device-1", '{"device":"device-1","value":66.6}'))
        assert mqtt_source.READINGS.get("device-1", {}).get("v") == 66.6

    def test_data_topic_updates_cloud_device(self):
        """data/ 主题应更新云端设备缓存（CLOUD_DEVICES）的主读数与最近上报时间。"""
        mqtt_source._record_message(FakeMsg("data/box-001/device-1", '{"device":"device-1","box":"box-001","value":42.0}'))
        cd = mqtt_source.CLOUD_DEVICES.get("device-1")
        assert cd is not None
        assert cd["primary"] == 42.0
        assert cd["last_seen"] > 0
        assert cd["box"] == "box-001"

    def test_message_log_capped_at_200(self):
        """消息流有上限（200 条），超限后淘汰最旧消息，防止内存无限增长。"""
        for i in range(250):
            mqtt_source._record_message(FakeMsg("data/box-001/device-1", f'{{"value":{i}}}'))
        assert len(mqtt_source.MESSAGE_LOG) <= mqtt_source.MESSAGE_LOG_MAX
        assert mqtt_source.MESSAGE_LOG[-1]["topic"] == "data/box-001/device-1"

    def test_sys_topic_updates_broker_stats(self):
        """$SYS/broker/* 统计消息应更新 Broker 实时统计（不影响设备读数）。"""
        mqtt_source._record_message(FakeMsg("$SYS/broker/clients/connected", "3"))
        assert mqtt_source.BROKER_STATS["clients_connected"] == 3
        assert mqtt_source.CLOUD_DEVICES == {}
        assert mqtt_source.READINGS == {}

    def test_cloud_topic_does_not_enter_stream(self):
        """cloud/#（agent 推送概览/CRD/日志）不计入设备消息流。"""
        mqtt_source._record_message(FakeMsg("cloud/state", '{"cloudcore":"running"}'))
        assert not any(m["topic"].startswith("cloud/") for m in mqtt_source.MESSAGE_LOG)

    def test_malformed_json_still_logged(self):
        """非 JSON 载荷也应计入消息流（原始回显），但不出现在读数里。"""
        mqtt_source._record_message(FakeMsg("data/box-001/device-1", "not-json"))
        assert mqtt_source.MESSAGE_LOG[-1]["topic"] == "data/box-001/device-1"
        assert mqtt_source.MESSAGE_LOG[-1]["payload"] == "not-json"


# ---------------------------------------------------------------------------
# 四、消息流对外接口：recent_messages
# ---------------------------------------------------------------------------
class TestRecentMessages:
    def test_returns_latest_100(self):
        """recent_messages() 返回最近最多 100 条，供前端轮询展示。"""
        for i in range(150):
            mqtt_source._record_message(FakeMsg("data/box-001/device-1", f'{{"value":{i}}}'))
        msgs = box_console.recent_messages()
        assert len(msgs) <= 100
        assert msgs[-1]["topic"] == "data/box-001/device-1"

    def test_message_order_newest_last(self):
        """消息流按时间顺序追加，最新一条在末尾（前端自动滚到底部即最新）。"""
        mqtt_source._record_message(FakeMsg("data/a", '{"v":1}'))
        mqtt_source._record_message(FakeMsg("data/b", '{"v":2}'))
        msgs = box_console.recent_messages()
        assert msgs[-2]["topic"] == "data/a"
        assert msgs[-1]["topic"] == "data/b"


# ---------------------------------------------------------------------------
# 五、端到端：publish → 回环解析 全链路（模拟一次真实发测试消息）
# ---------------------------------------------------------------------------
class TestEndToEnd:
    def test_full_loop_publish_to_stream(self, fake_paho):
        """发一条 data/ 测试消息后：发布成功 → 消息进入流 → 设备读数刷新。"""
        # 1) 前端调用 API 发布
        r = box_console.publish_test({"topic": "data/box-001/device-1", "payload": '{"device":"device-1","value":99.9}'})
        assert r["ok"] is True
        # 2) Broker 回环 → 平台订阅线程收到（模拟 on_message 回调）
        mqtt_source._on_message(None, None, FakeMsg("data/box-001/device-1", '{"device":"device-1","value":99.9}'))
        # 3) 消息流可见
        assert box_console.recent_messages()[-1]["topic"] == "data/box-001/device-1"
        # 4) 设备实时读数已刷新
        assert mqtt_source.READINGS.get("device-1", {}).get("v") == 99.9
        assert mqtt_source.CLOUD_DEVICES["device-1"]["primary"] == 99.9

    def test_publish_then_stream_has_timestamp(self, fake_paho):
        """消息流条目应带 ISO 时间戳（前端 fmtTime 展示用）。"""
        box_console.publish_test({"topic": "data/box-001/device-1", "payload": '{"value":1}'})
        mqtt_source._on_message(None, None, FakeMsg("data/box-001/device-1", '{"value":1}'))
        rec = box_console.recent_messages()[-1]
        assert "ts" in rec
        assert "T" in rec["ts"]  # ISO 8601
