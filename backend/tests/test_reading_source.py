"""读数真源收敛（P3）：设备读数只认 MQTT data/# 实时链路。

此前 resolve_reading 是三源级联：CLOUD_DEVICES.primary → READINGS → CRD twins 兜底。
第三源会让读数在两个通道间来回跳（MQTT 断一会儿显示 twin 旧值、恢复又跳回实时值），
且掩盖「停报」事实。P3 起取消 twins 兜底，停报就是没读数，由 data_online/last_online 表达。
"""
import time

import pytest

from app.mqtt_source import parsing
from app.mqtt_source.parsing import CLOUD_DEVICES, READINGS, resolve_reading


@pytest.fixture(autouse=True)
def _clean():
    CLOUD_DEVICES.clear()
    READINGS.clear()
    saved_links = dict(parsing._shared._LINKS_REV)
    saved_factor = dict(parsing._shared._LINKS_FACTOR)
    parsing._shared._LINKS_REV.clear()
    parsing._shared._LINKS_FACTOR.clear()
    yield
    CLOUD_DEVICES.clear()
    READINGS.clear()
    parsing._shared._LINKS_REV.clear()
    parsing._shared._LINKS_FACTOR.clear()
    parsing._shared._LINKS_REV.update(saved_links)
    parsing._shared._LINKS_FACTOR.update(saved_factor)


def _link(device_id, cloud_id, factor=1.0):
    parsing._shared._LINKS_REV[device_id] = cloud_id
    parsing._shared._LINKS_FACTOR[cloud_id] = factor


def test_reading_comes_from_mqtt_primary():
    _link("dev-1", "flow-meter")
    CLOUD_DEVICES["flow-meter"] = {"primary": 12.5}
    assert resolve_reading("dev-1") == 12.5


def test_factor_applied():
    _link("dev-1", "flow-meter", factor=0.06)
    CLOUD_DEVICES["flow-meter"] = {"primary": 100.0}
    assert resolve_reading("dev-1") == pytest.approx(6.0)


def test_readings_field_fallback_still_works():
    _link("dev-1", "old-device")
    READINGS["old-device"] = {"v": 3.5}
    assert resolve_reading("dev-1") == 3.5


def test_no_twin_fallback_even_when_crd_is_fresh(monkeypatch):
    """核心回归：CRD twins 有新鲜上报值时，也不再作为读数来源。"""
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(
        parsing._shared.cloud_agent, "crds",
        lambda *a, **k: {"ok": True, "devices": [
            {"name": "flow-meter",
             "twins": [{"propertyName": "flow", "reported": "9.9", "timestamp": now_ms}]},
        ]})
    _link("dev-1", "flow-meter")
    # data/# 链路无任何数据 → 读数应为 None（而不是兜底成 twin 的 9.9）
    assert resolve_reading("dev-1") is None
    # 对照：twin 兜底函数本身仍然可用（在线/停报判定还要用）
    assert parsing._crd_twin_reading("flow-meter") == pytest.approx(9.9)


def test_no_link_returns_none():
    assert resolve_reading("unbound-device") is None
