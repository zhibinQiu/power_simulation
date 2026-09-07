"""数据中间件纯逻辑测试（不连任何 Broker）。

覆盖：标准消息组装（topic/payload）、时间归一、数值过滤、展平/改名/设备抽取、
适配器校验、注册表 build_all 行为、runner --check 自检。
"""
import json
import os
import sys
from pathlib import Path

import pytest

MW_DIR = Path(__file__).resolve().parents[1]            # .../cloud-deploy/middleware
CLOUD_DEPLOY_DIR = Path(__file__).resolve().parents[2]  # .../cloud-deploy（middleware 包所在）
sys.path.insert(0, str(CLOUD_DEPLOY_DIR))

from middleware.adapters import BaseAdapter, build_all  # noqa: E402
from middleware.adapters.base import flatten, numeric  # noqa: E402
from middleware.bridge import OutputBridge, compose_message, normalize_ts  # noqa: E402
from middleware.runner import main  # noqa: E402


class FakeBridge:
    """只收集 compose 结果，不真正发布。"""

    def __init__(self):
        self.published = []

    def publish(self, box, device, prop, value, ts=None):
        topic, payload = compose_message(box, device, prop, value, ts)
        self.published.append({"box": box, "device": device, "prop": prop,
                               "value": value, "ts": ts, "topic": topic,
                               "payload": json.loads(payload)})
        return True

    def status(self):
        return {"connected": False, "publish_ok": len(self.published),
                "publish_fail": 0, "last_error": "", "broker": "fake"}


def _adapter(cfg=None):
    base = {"id": "a1", "type": "mqtt", "name": "t", "box": "ext-x",
            "device": "dev1", "broker": {"host": "h"}, "topics": ["t/#"]}
    base.update(cfg or {})
    from middleware.adapters.mqtt_source import MqttSourceAdapter
    return MqttSourceAdapter(base, FakeBridge())


# ---------------------------------------------------------------------------
class TestCompose:
    def test_topic_and_payload(self):
        topic, payload = compose_message("ext-weigh", "scale1", "weight", 0.41, 1000)
        assert topic == "data/ext-weigh/scale1/scale1/weight"
        obj = json.loads(payload)
        assert obj["v"] == 0.41 and obj["t"] == 1000
        assert obj["device"] == "scale1" and obj["box"] == "ext-weigh"
        assert obj["prop"] == "weight" and obj["src"] == "external"

    def test_ts_normalize_seconds_to_ms(self):
        assert normalize_ts(1700000000) == 1700000000000
        assert normalize_ts(1700000000123) == 1700000000123
        assert normalize_ts("1700000000") == 1700000000000
        assert normalize_ts(None) is None
        assert normalize_ts("abc") is None
        assert normalize_ts(0) is None


# ---------------------------------------------------------------------------
class TestValueFilter:
    def test_numeric_coerce(self):
        assert numeric("0.41") == 0.41
        assert numeric(7) == 7.0
        assert numeric(True) is None      # 布尔不算读数
        assert numeric("") is None
        assert numeric("abc") is None
        assert numeric(None) is None
        assert numeric(float("nan")) is None   # NaN 不合法读数
        assert numeric(float("inf")) is None
        assert numeric("nan") is None


# ---------------------------------------------------------------------------
class TestFlattenAndEmit:
    def test_flatten_nested(self):
        assert flatten({"a": {"b": 1, "c": {"d": 2}}, "e": 3}) == {
            "a.b": 1, "a.c.d": 2, "e": 3}

    def test_emit_flat_skips_non_numeric(self):
        a = _adapter({"deviceKeys": ["device"]})
        n = a.emit_flat({"device": "s1", "weight": 12.3, "state": "ok", "ok": True,
                         "ts": 1700000000000})
        # 仅 weight 发布；state/ok 为非数值跳过；device 与 ts 为元数据字段不发布
        assert n == 1
        assert a.stats["readings"] == 1 and a.stats["skipped"] == 2

    def test_field_map_renames(self):
        a = _adapter({"fieldMap": {"gross": "weight"}, "deviceKeys": ["device"]})
        a.emit_flat({"device": "s1", "gross": 55.0})
        p = a.bridge.published
        assert p and p[0]["prop"] == "weight" and p[0]["value"] == 55.0

    def test_default_device_when_missing(self):
        a = _adapter({"device": "fallback", "deviceKeys": ["device"]})
        a.emit_flat({"temp": 36.6})
        assert a.stats["readings"] == 1

    def test_missing_device_skipped(self):
        a = _adapter({"device": "", "deviceKeys": []})
        n = a.emit_flat({"temp": 36.6})
        assert n == 0 and a.stats["skipped"] == 1

    def test_ts_from_message(self):
        a = _adapter({"deviceKeys": ["device"]})
        a.emit_flat({"device": "s1", "weight": 1.0, "timestamp": 1700000000})
        assert a.stats["readings"] == 1


# ---------------------------------------------------------------------------
class TestValidation:
    def test_mqtt_requires_broker_topics(self):
        a = _adapter({"broker": {"host": ""}, "topics": []})
        errs = a.validate()
        assert any("broker.host" in e for e in errs)
        assert any("topics" in e for e in errs)

    def test_box_required(self):
        a = _adapter({"box": ""})
        errs = a.validate()
        assert any("box" in e for e in errs)

    def test_build_all_skips_disabled_and_unknown(self):
        adapters, errors = build_all([
            {"id": "on", "type": "mqtt", "box": "ext-a", "device": "d",
             "broker": {"host": "h"}, "topics": ["t"]},
            {"id": "off", "type": "mqtt", "box": "ext-b", "device": "d",
             "broker": {"host": "h"}, "topics": ["t"], "enabled": False},
            {"id": "bad", "type": "nope"},
        ], FakeBridge())
        assert [a.id for a in adapters] == ["on"]
        assert len(errors) == 1 and "未知 type" in errors[0]

    def test_runner_check_exit_zero(self):
        rc = main(["--config", str(MW_DIR / "config.example.json"), "--check"])
        assert rc == 0
