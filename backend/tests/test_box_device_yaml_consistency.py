"""本地设备配置 ⇄ 下发 YAML/云端 CRD 一致性回归测试（2026-09-21）。

背景：一次真实事故——在服务器上新增 LoRa 设备 servers-temp（绑定已存在的 lora-temp-model，
请求未携带点位，按「点位由模型承载」的语义沿用模型点位）后，本地 devices.properties 是
temperature，而落盘并下发到云端的 Device YAML 却是 device_yaml 的空点位兜底产物
`- name: "value"`（collectCycle 也退回 1000）。结果：平台显示 devices.properties=temperature、
云端 CRD 的 spec.properties=[value] —— 两边不一致，盒子按 value 取数导致设备无数据。

根因是 create_device 先用原始请求（properties 可能为空）生成 YAML，之后才算出「最终点位」
props_for_sync（= 请求点位 or 模型点位），却没用最终点位重生成设备 YAML。

本文件锁住：
1. 新建/编辑设备未带点位时，存盘 YAML 必须渲染模型的点位，不得退化成兜底的 "value"；
2. 设备 YAML 的采集周期与请求一致（不被兜底值覆盖）；
3. 模型点位不变诉求：请求未带点位时不得把共享模型点位清空；
4. 模型点位变更重刷同模型设备 YAML 时，nengtan.io/hwid label 不得丢失。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.box_console import cloud_ops  # noqa: E402
from app.box_console import devices as dev_mod  # noqa: E402
from app.domain.box.hwid import HWID_LABEL  # noqa: E402


MODEL_POINTS = [{"name": "temperature", "type": "int", "accessMode": "r", "scale": 0.1, "unit": "℃"}]

LORA_CONF = {
    "broker": "127.0.0.1", "port": 41884, "applicationID": "0ce81243-64fb-455c-a484-9b26acb42f65",
    "devEUI": "0120560100000245", "slaveId": 2,
}


def _req(**over):
    """新建/保存设备的最小请求体（properties 缺省 = 未携带点位，沿用绑定模型的点位）。"""
    base = {
        "mode": "apply", "modelName": "lora-temp-model", "deviceName": "servers-temp",
        "namespace": "default", "nodeName": "nt001", "collectCycle": 5000, "protocol": "lora",
        "comm": {}, "opcua": {}, "bluetooth": {}, "cellular": {}, "lora": dict(LORA_CONF),
    }
    base.update(over)
    return base


def _cfg(devices=None, models=None):
    return {
        "devices": devices or [],
        "models": models or [{
            "name": "lora-temp-model", "namespace": "default", "protocol": "lora",
            "properties": [dict(p) for p in MODEL_POINTS], "yaml": "kind: DeviceModel\n",
        }],
    }


@pytest.fixture()
def mem_store(monkeypatch):
    """把 _load_devices/_save_devices 换到内存盒，避免污染真实 backend/config/box_devices.json。"""

    def _install(cfg):
        box = {"data": cfg}

        def _load():
            return box["data"]

        def _save(d):
            box["data"] = d

        monkeypatch.setattr(dev_mod, "_load_devices", _load)
        monkeypatch.setattr(dev_mod, "_save_devices", _save)
        monkeypatch.setattr(cloud_ops, "_load_devices", _load)
        monkeypatch.setattr(cloud_ops, "_save_devices", _save)
        # 云端下发/删除：记录调用，不做真实 HTTP
        calls = {"apply": [], "delete": []}
        monkeypatch.setattr(cloud_ops, "apply_devices_to_cloud",
                            lambda **kw: (calls["apply"].append(kw.get("device_name")), {
                                "ok": True, "rc": 0, "stdout": "", "stderr": "", "applied": []})[1])
        monkeypatch.setattr(cloud_ops, "_cloud_delete_crds",
                            lambda *a, **kw: {"ok": True, "rc": 0, "stdout": "", "stderr": ""})
        monkeypatch.setattr(cloud_ops, "_cloud_device_exists", lambda *a, **kw: False)
        box["calls"] = calls
        return box

    return _install


def _saved(box, name):
    return next(d for d in box["data"]["devices"] if d.get("name") == name)


# ------------------------- 1. 未带点位时 YAML 必须用模型的点位 -------------------------


def test_new_device_without_properties_renders_model_points(mem_store):
    """设备绑定模型、请求未带点位：存盘 YAML 必须渲染模型点位，而不是兜底的 "value"。

    这是本次事故的核心：YAML 一旦退化成 value，下发后云端 CRD 与实际配置就不一致。
    """
    box = mem_store(_cfg())
    dev_mod.create_device(_req())
    saved = _saved(box, "servers-temp")
    assert [p["name"] for p in saved["properties"]] == ["temperature"]
    assert '- name: "temperature"' in saved["yaml"], "设备 YAML 必须渲染模型的点位"
    assert 'name: "value"' not in saved["yaml"], "不得出现 device_yaml 的空点位兜底产物 value"


def test_new_device_yaml_uses_requested_collect_cycle(mem_store):
    """同一事故的另一面：兜底点位会把 collectCycle 一并退回 1000（请求是 5000）。"""
    box = mem_store(_cfg())
    dev_mod.create_device(_req())
    saved = _saved(box, "servers-temp")
    assert "collectCycle: 5000" in saved["yaml"]
    assert "collectCycle: 1000" not in saved["yaml"]


def test_edit_without_properties_keeps_model_points(mem_store):
    """编辑已有设备（未改点位）同样按最终点位重生成 YAML，不退化。"""
    existing = {
        "name": "servers-temp", "namespace": "default", "hwId": "lora-0120560100000245-s2",
        "model": "lora-temp-model", "node": "nt001", "protocol": "lora", "collectCycle": 5000,
        "cloudDevice": "", "comm": {}, "opcua": {}, "bluetooth": {}, "cellular": {},
        "lora": dict(LORA_CONF), "properties": [dict(p) for p in MODEL_POINTS],
        "yaml": "kind: Device\n", "status": "reporting",
    }
    box = mem_store(_cfg(devices=[existing]))
    cloud_ops._cloud_device_exists = lambda *a, **kw: True  # noqa: F811
    dev_mod.create_device(_req(origName="servers-temp"))
    saved = _saved(box, "servers-temp")
    assert '- name: "temperature"' in saved["yaml"]
    assert 'name: "value"' not in saved["yaml"]


# ------------------------- 2. 不得清掉共享模型的点位 -------------------------


def test_model_points_survive_device_save(mem_store):
    """请求未带点位时不得改写共享模型（历史事故：保存一台设备清空同模型所有设备的点位）。"""
    box = mem_store(_cfg())
    dev_mod.create_device(_req())
    model = next(m for m in box["data"]["models"] if m["name"] == "lora-temp-model")
    assert [p["name"] for p in model["properties"]] == ["temperature"]


# ------------------------- 3. 重刷同模型设备 YAML 时保留 hwId -------------------------
def test_regenerate_keeps_hwid_label(mem_store):
    """模型点位变更会重刷所有引用设备的 YAML，此时不得丢掉 nengtan.io/hwid label。"""
    existing = {
        "name": "servers-temp", "namespace": "default", "hwId": "lora-0120560100000245-s2",
        "model": "lora-temp-model", "node": "nt001", "protocol": "lora", "collectCycle": 5000,
        "cloudDevice": "", "comm": {}, "opcua": {}, "bluetooth": {}, "cellular": {},
        "lora": dict(LORA_CONF), "properties": [dict(p) for p in MODEL_POINTS],
        "yaml": "kind: Device\n", "status": "reporting",
    }
    box = mem_store(_cfg(devices=[existing]))
    dev_mod.create_device(_req(properties=[dict(p) for p in MODEL_POINTS]))
    saved = _saved(box, "servers-temp")
    assert f"{HWID_LABEL}: \"lora-0120560100000245-s2\"" in saved["yaml"]


# ------------------------- 4. 存量设备 YAML 补齐后必须连带下发 -------------------------


def _legacy(name, hwid, model, proto="modbus", lora=None):
    """hwId 能力上线前落盘的老设备：记录里有 hwId，YAML 却是无 label 的旧模板。"""
    return {
        "name": name, "namespace": "default", "hwId": hwid, "model": model, "node": "nt001",
        "protocol": proto, "collectCycle": 5000, "cloudDevice": "", "comm": {}, "opcua": {},
        "bluetooth": {}, "cellular": {}, "lora": lora or {},
        "properties": [dict(p) for p in MODEL_POINTS],
        "yaml": f"kind: Device\nmetadata:\n  name: \"{name}\"\n", "status": "reporting",
    }


def test_stale_yaml_is_repaired_and_redeployed(mem_store):
    """保存任意设备时，缺 hwid label 的存量 YAML 要补齐，并随本次保存一并发到云端。

    只改本地不发云端 = 本地修正了、云端 CRD 还是旧样，仍是「两边不一致」。
    """
    legacy = _legacy("flow-meter", "mb-ttyrs485-s6", "flow-meter-model")
    box = mem_store(_cfg(devices=[legacy]))
    dev_mod.create_device(_req())
    repaired = _saved(box, "flow-meter")
    assert f"{HWID_LABEL}: \"mb-ttyrs485-s6\"" in repaired["yaml"], "存量 YAML 必须补齐 hwid label"
    assert "flow-meter" in box["calls"]["apply"], "补齐后必须连带下发，否则云端仍是旧 CRD"


def test_model_sync_backfills_pointless_device(mem_store):
    """同模型的存量设备点位为空时，会被模型点位补齐（而不是渲染成兜底的 value）。"""
    empty = _legacy("ghost", "dev-abc123", "lora-temp-model")
    empty["properties"] = []
    box = mem_store(_cfg(devices=[empty]))
    dev_mod.create_device(_req())
    ghost = _saved(box, "ghost")
    assert [p["name"] for p in ghost["properties"]] == ["temperature"]
    assert 'name: "value"' not in ghost["yaml"]
    # 补齐了点位就要发到云端，否则本地与云端又不一致
    assert "ghost" in box["calls"]["apply"]


def test_resync_skips_devices_without_points():
    """resync 自身对点位为空的设备必须跳过：重刷会命中 value 兜底，反而制造不一致。"""
    empty = _legacy("ghost", "dev-abc123", "lora-temp-model")
    empty["properties"] = []
    data = {"devices": [empty]}
    assert dev_mod._resync_stale_device_yamls(data) == []
    assert data["devices"][0]["yaml"] == empty["yaml"]
