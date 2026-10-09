"""MQTT 识别出的盒子节点：归属不明不得合成「未分组」假盒子（2026-09-28）。

平台订阅的是 `#`，除 data/<box>/… 之外还有 cloud/state、ext/ 上行空间、命令回执等
大量消息会经过设备识别。此前 box 兜底成「未分组」（概览侧还有 unknown-box），概览把
这些消息聚合成一张名为「未分组」的能碳一体机卡片——无 IP、无服务、点不开也删不掉，
还会在拓扑图里与真实盒子抢位置。

这里锁住两层口径：
① 识别层：归属不明返回空串，绝不返回占位盒子名；
② 概览层：空/占位 box 一律跳过，只有真实 boxId 才合成节点。
"""
from __future__ import annotations

from app import mqtt_source
from app.box_console.overview import _mqtt_boxes, _merge_nodes
from app.mqtt_source import box_state
from app.mqtt_source.parsing import _identify_cloud_device


# ------------------------------ ① 识别层 ------------------------------

def test_box_taken_from_data_topic():
    """标准上报主题 data/<box>/<device>/<instance>/<property> → box = 第 2 段。"""
    dev, box = _identify_cloud_device("data/nt001/flow-meter/flow-meter/flow_rate", {"v": 1.2})
    assert box == "nt001"
    assert dev == "flow-meter"


def test_box_taken_from_payload_when_topic_has_no_box():
    """payload 显式 box 字段优先（盒子多设备聚合上报）。"""
    _, box = _identify_cloud_device("data/up/agg", {"device": "flow-meter", "box": "nt001"})
    assert box == "nt001"


def test_unknown_box_is_empty_not_placeholder():
    """非 data/<box>/… 且 payload 无 box → 空串，不得兜底成「未分组」。

    ext/ 上行空间（外部数据系统经一体机上行）就是典型：它不是一体机本身。
    """
    dev, box = _identify_cloud_device("ext/steel/bf1", {"device": "bf1", "v": 12.5})
    assert dev == "bf1"
    assert box == ""
    assert box != "未分组"


def test_command_topic_without_box_is_empty():
    """命令回执/其它非数据主题：无归属即留空（不得造出占位盒子）。"""
    _, box = _identify_cloud_device("cmd/nt001/deploy", {"cmd": "config", "ok": True})
    assert box == ""


# ------------------------------ ② 概览层 ------------------------------

SNAPSHOT = {
    "flow-meter": {"id": "flow-meter", "box": "nt001", "last_seen": 1.0},
    "ghost-1": {"id": "ghost-1", "box": "未分组", "last_seen": 2.0},
    "ghost-2": {"id": "ghost-2", "box": "", "last_seen": 3.0},
    "ghost-3": {"id": "ghost-3", "box": "unknown-box", "last_seen": 4.0},
    "ext-steel-bf1": {"id": "ext-steel-bf1", "box": "ext-steel", "last_seen": 5.0},
}


def test_mqtt_boxes_skips_placeholder(monkeypatch):
    monkeypatch.setattr(mqtt_source, "snapshot_cloud_devices", lambda: SNAPSHOT)
    names = [n["name"] for n in _mqtt_boxes()]
    assert names == ["ext-steel", "nt001"]
    assert "未分组" not in names
    assert "unknown-box" not in names


def test_merge_nodes_has_no_placeholder(monkeypatch):
    monkeypatch.setattr(mqtt_source, "snapshot_cloud_devices", lambda: SNAPSHOT)
    merged = _merge_nodes({"nodes": [{"name": "nt001", "is_edge": True}]}, _mqtt_boxes())
    names = [n["name"] for n in merged]
    assert "未分组" not in names
    # 真实盒子不被去重逻辑误删
    assert "nt001" in names


def test_box_state_ignores_unknown_box():
    """归属不明的状态帧不落 BOX_SERVICES 缓存。"""
    try:
        box_state._record_box_state("state", {"services": [{"name": "box-mapper"}]})
        assert "未分组" not in mqtt_source.BOX_SERVICES
        assert "" not in mqtt_source.BOX_SERVICES
        box_state._record_box_state("state/nt001/services", {"services": [{"name": "box-mapper"}]})
        assert mqtt_source.box_services("nt001")[0]["name"] == "box-mapper"
    finally:
        mqtt_source.BOX_SERVICES.pop("nt001", None)
        mqtt_source.BOX_SERVICES.pop("未分组", None)
        mqtt_source.BOX_SERVICES.pop("", None)
