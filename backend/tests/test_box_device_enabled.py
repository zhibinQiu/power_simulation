"""采集设备「是否启用采集（enabled）」回归测试。

语义（本文件锁定的就是这几条）：
  1. 停用 =/= 删除：enabled=false 的设备照样保存在平台、照样下发到盒子并在云端登记，
     只是盒子的采集线程跳过它（不发问帧、不上报）。配置保留，重新勾选即恢复。
     所以停用的设备必须进下发产物 —— 反过来说，把它过滤掉就等于从盒子定义里删除它，
     与「配置保留」的前提矛盾；
  2. 停用必须体现在指纹里：_MAPPER_FP_KEYS 含 enabled，因此「启用/停用」是一次真实的
     配置变更。若哪一端算指纹时漏掉这个字段，就会出现「下发成功但盒子没变化」，
     而三端校验还报告一致 —— 这类不一致最难查；
  3. 请求不携带 enabled（None）时沿用旧记录：不能因为 Pydantic 把未传字段补成 None
     就当成「停用」，也不能把判断写成 enabled in p（恒为真，会把旧值冲掉）；
  4. 列表输出一律归一化为布尔 enabled（历史记录没有该字段的设备 = 启用）。

运行：cd backend && python -m pytest tests/test_box_device_enabled.py -v
"""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.box_console import devices as bd  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _dev(name="temp-1", **kw):
    """最小可用的新建/修改设备请求（modbus 串口）。"""
    p = {
        "mode": "apply",
        "protocol": "modbus",
        "modelName": "temp-model",
        "deviceName": name,
        "namespace": "default",
        "nodeName": "nt001",
        "collectCycle": 1000,
        "comm": {"commType": "serial", "slaveID": 1, "serialPort": "/dev/ttyRS485",
                 "baudRate": 9600, "parity": "none"},
        "properties": [{"name": "temperature", "type": "int", "accessMode": "r",
                        "registerType": "holdingRegister", "register": 0,
                        "scale": 0.1, "unit": "C"}],
    }
    p.update(kw)
    return p


@pytest.fixture
def store(monkeypatch):
    """内存版的 box_devices.json（读写都落在同一份 dict 里）。"""
    data = {"models": [], "devices": []}
    monkeypatch.setattr(bd, "_load_devices", lambda: data)
    monkeypatch.setattr(bd, "_save_devices", lambda d: None)
    monkeypatch.setattr(bd, "_cloud_precheck", lambda *a, **k: None)
    monkeypatch.setattr(bd, "_auto_sync_cloud", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(bd, "auto_push_box_after_apply",
                        lambda *a, **k: {"ok": True, "skipped": True})
    return data


# ---------------------------------------------------------------------------
# 下发产物：停用是「带标记下发」，不是从产物里删除
# ---------------------------------------------------------------------------
def test_mapper_device_carries_disabled_flag():
    """下发产物永远显式带 enabled：停用 false，缺省与显式 True 都归一为 true。

    （历史上这里缺省时不输出该字段，于是「平台缺省 / 盒子读到 None」成对出现；
    两端指纹算法但凡有一点差异就会静默不一致，现已同口径补全称。）
    """
    assert bd.to_mapper_device({"name": "a", "enabled": False})["enabled"] is False
    assert bd.to_mapper_device({"name": "a", "enabled": True})["enabled"] is True
    assert bd.to_mapper_device({"name": "a"})["enabled"] is True
    # 原生协议（LoRa / cellular）走的是另一条转换函数，口径必须一致
    assert bd._to_mapper_native_device({"name": "b", "enabled": False}, "lora")["enabled"] is False
    assert bd._to_mapper_native_device({"name": "b"}, "lora")["enabled"] is True


def test_disabled_device_is_still_deployed_and_in_fingerprint(store):
    """停用的设备照旧下发且计入指纹 —— 两端算出相同值才说明「下发 = 生效」。"""
    store["devices"] = [{"name": "temp-1", "protocol": "modbus", "node": "nt001",
                         "comm": {"commType": "serial", "slaveID": 1},
                         "properties": [{"name": "temperature"}], "enabled": False}]
    expected = bd._expected_mapper_devs()
    assert [d.get("name") for d in expected] == ["temp-1"]   # 没有被过滤掉
    assert expected[0]["enabled"] is False

    fp_off = bd.mapper_config_fingerprint(expected)
    store["devices"][0]["enabled"] = True
    fp_on = bd.mapper_config_fingerprint(bd._expected_mapper_devs())
    store["devices"][0].pop("enabled")
    fp_default = bd.mapper_config_fingerprint(bd._expected_mapper_devs())
    assert fp_off != fp_on                  # 启用/停用是两种不同的配置状态
    assert fp_default == fp_on              # 缺省 = 启用（两端同一口径）


# ---------------------------------------------------------------------------
# 存盘语义：显式选择落盘，未携带时沿用旧记录
# ---------------------------------------------------------------------------
def test_create_device_persists_disabled(store):
    res = bd.create_device(_dev(enabled=False))
    assert res["ok"] is True
    assert bd._load_devices()["devices"][0]["enabled"] is False


def test_edit_without_enabled_keeps_disabled(store):
    """编辑时表单没提交 enabled（缺 key / None 两种形态）都不得把停用冲掉。

    现场后果：一次不相干的保存把停用状态悄悄清掉，盒子又开始空等这台不在线的设备，
    串口超时反过来拖慢同一条总线上的其它设备。
    """
    bd.create_device(_dev(enabled=False))
    for absence in ({}, {"enabled": None}):
        p = _dev()
        p.pop("enabled", None)
        p.update(absence)
        bd.create_device(p)
        assert bd._load_devices()["devices"][0]["enabled"] is False


def test_edit_can_re_enable(store):
    bd.create_device(_dev(enabled=False))
    bd.create_device(_dev(enabled=True))
    assert bd._load_devices()["devices"][0]["enabled"] is True


def test_new_device_is_enabled_by_default(store):
    """新建不传 enabled：按「缺省启用」落盘，不写 None / False。"""
    bd.create_device(_dev())
    assert bd._load_devices()["devices"][0].get("enabled") is not False


# ---------------------------------------------------------------------------
# 请求模型：enabled 必须能穿过 Pydantic 到达业务层
# ---------------------------------------------------------------------------
def test_request_model_passes_enabled():
    """这是本功能最容易踩的一处：字段没在 BoxDeviceRequest 上声明时，请求体里的
    enabled 会被 Pydantic 静默丢弃，业务层 `p.get("enabled")` 永远是 None ——
    表现为「勾了停用、保存成功、盒子照旧在采」。
    """
    from app.api.box_router import BoxDeviceRequest

    assert BoxDeviceRequest(deviceName="a", enabled=False).model_dump()["enabled"] is False
    assert BoxDeviceRequest(deviceName="a", enabled=True).model_dump()["enabled"] is True
    assert BoxDeviceRequest(deviceName="a").model_dump()["enabled"] is None


# ---------------------------------------------------------------------------
# 列表输出：归一化布尔
# ---------------------------------------------------------------------------
def test_list_devices_normalizes_enabled(monkeypatch, store):
    monkeypatch.setattr(bd.mqtt_source, "CLOUD_DEVICES", {})
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: {"ok": True, "devices": []})
    store["devices"] = [
        {"name": "on-1", "protocol": "modbus"},
        {"name": "off-1", "protocol": "modbus", "enabled": False},
        {"name": "legacy-1", "protocol": "modbus", "enabled": True},
    ]
    got = {d["name"]: d["enabled"] for d in bd.list_devices()["devices"]}
    assert got == {"on-1": True, "off-1": False, "legacy-1": True}


# ---------------------------------------------------------------------------
# 三端校验：停用不得被误报成「盒子缺设备」
# ---------------------------------------------------------------------------
def test_consistency_treats_disabled_device_as_valid(monkeypatch, store):
    """盒子回报的 deviceNames 只含「正在采集」的设备，停用的设备天然不在里面。

    若照常比对名单，每台停用设备都会是一个点多少次「一键对齐」也修不好的假漂移，
    把真正的问题淹掉。停用的合法性已由指纹负责校验（enabled 计入指纹）。
    """
    import time as _t

    store["models"] = [{"name": "temp-model", "protocol": "modbus",
                        "properties": [{"name": "temperature", "type": "int"}]}]
    store["devices"] = [
        {"name": "live-1", "protocol": "modbus", "model": "temp-model", "node": "nt001",
         "comm": {"commType": "serial", "slaveID": 1},
         "properties": [{"name": "temperature"}], "enabled": True},
        {"name": "parked-1", "protocol": "modbus", "model": "temp-model", "node": "nt001",
         "comm": {"commType": "serial", "slaveID": 2},
         "properties": [{"name": "temperature"}], "enabled": False},
    ]
    monkeypatch.setattr(bd.cloud_agent, "crds",
                        lambda force=False: {"ok": True, "devices": [
                            {"name": "live-1"}, {"name": "parked-1"}]})
    monkeypatch.setattr(bd.mqtt_source, "box_config_state", lambda box: {
        "fingerprint": bd.mapper_config_fingerprint(bd._expected_mapper_devs()),
        "last_seen": _t.time(), "version": 3, "pid": 1, "source": "file",
        "deviceNames": ["live-1"],          # 盒子只上报自己在采集的那台
    })
    rep = bd.consistency("nt001")
    assert rep["missing_in_box"] == []
    assert rep["missing_in_cloud"] == []
    assert rep["aligned"] is True, rep["note"]

    # 停用 / 恢复时两端指纹必须跟着变，否则「改了没生效」看不出来
    store["devices"][1]["enabled"] = True
    monkeypatch.setattr(bd.mqtt_source, "box_config_state", lambda box: {
        "fingerprint": bd.mapper_config_fingerprint(bd._expected_mapper_devs()),
        "last_seen": _t.time(), "version": 4, "pid": 1, "source": "file",
        "deviceNames": ["live-1", "parked-1"],
    })
    assert bd.consistency("nt001")["aligned"] is True
