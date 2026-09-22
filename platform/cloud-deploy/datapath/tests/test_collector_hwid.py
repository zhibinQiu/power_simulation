"""collector 时序身份键：payload 里的 hwId 优先于主题里的设备名。

背景：设备改名只改显示名（name），硬件唯一 ID（hwId）保持不变。若时序子表/devide tag
仍用设备名，改名后新数据进新子表、历史查不到。故盒子 mapper 上报时回传 hwId，
collector 用它作为身份键 —— 改名前后落到同一张子表。
"""
import importlib.util
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "collector.py"))


def _load():
    spec = importlib.util.spec_from_file_location("nengtan_collector", _SRC)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as e:      # 本地无 paho 等运行依赖时跳过
        pytest.skip(f"缺少运行依赖：{e}")
    return mod


@pytest.fixture()
def collector():
    mod = _load()
    mod._TS_BUF.clear()
    yield mod
    mod._TS_BUF.clear()


def _pub(collector, topic, payload):
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    collector._ts_record(topic, payload)
    return list(collector._TS_BUF)


def test_hwid_wins_over_topic_device_name(collector):
    buf = _pub(collector, "data/nt001/shuitong-temp/shuitong-temp/temperature",
               {"device": "shuitong-temp", "box": "nt001", "temperature": 24.5,
                "ts": 1700000000.0, "hwId": "lora-0120560100000245-s7"})
    assert len(buf) == 1
    box, device, instance, prop, value, _ts = buf[0]
    assert device == "lora-0120560100000245-s7"    # 身份键 = 硬件 ID
    assert instance == "shuitong-temp"             # 显示名仍在 instance tag
    assert (box, prop, value) == ("nt001", "temperature", 24.5)


def test_fallback_to_topic_name_when_no_hwid(collector):
    """旧设备/旧 mapper 无 hwId：行为完全不变（仍用主题里的设备名）。"""
    buf = _pub(collector, "data/nt001/flow-meter/flow-meter/flow",
               {"device": "flow-meter", "box": "nt001", "flow": 12.5, "ts": 1700000000.0})
    assert buf[0][1] == "flow-meter"


def test_plain_number_payload_unchanged(collector):
    buf = _pub(collector, "data/nt001/old-dev/old-dev/weight", b"0.54")
    assert buf[0][1] == "old-dev" and buf[0][4] == 0.54


def test_rename_keeps_same_subtable(collector):
    """改名前后：主题里的设备名变了，子表身份键不变 —— 这是本改动的目的。"""
    before = _pub(collector, "data/nt001/env-temp/env-temp/temperature",
                  {"device": "env-temp", "temperature": 23.0, "hwId": "lora-eui-s2"})
    after = _pub(collector, "data/nt001/servers-temp/servers-temp/temperature",
                 {"device": "servers-temp", "temperature": 23.4, "hwId": "lora-eui-s2"})
    assert before[0][1] == after[0][1] == "lora-eui-s2"
    assert collector._subtable_name(*before[0][:4]) == collector._subtable_name(*after[0][:4])


def test_non_data_topic_ignored(collector):
    buf = _pub(collector, "state/nt001/services", {"hwId": "x"})
    assert buf == []
