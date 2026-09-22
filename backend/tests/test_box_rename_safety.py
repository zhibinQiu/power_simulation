"""设备改名安全性回归测试（2026-09-21）。

背景：用户在「数据源管理」里对设备做重命名后，shuitong-temp / env-temp 两台设备在云端
口径下失去实时数据——云端 K8s 里这两台的 Device CRD 已不存在。根因是改名保存时后端
「先下发新名、随后无条件删除云端旧名 CRD」，且未校验新设备是否真的生效、未拦截改名目标名
与其它设备重名（重名会静默顶替一台设备）。

本文件锁住修复后的行为：
1. 改名目标名已被其它设备占用 → 直接报错，不动本地配置、不下发；
2. 云端未确认新设备生效 → 保留旧 CRD（宁可残留，不可让设备云端身份丢失）；
3. 新旧名在 K8s 中是同一对象（大小写/下划线等价）→ 跳过删除；
4. 旧名仍被其它设备引用（设备名或 cloudDevice 绑定）→ 跳过删除；
5. 确认生效且旧名无人使用 → 正常删除旧 CRD；
6. 保存/改名未携带点位时不得清空共享模型点位（级联清空会让同模型设备全部无数据）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.box_console import cloud_ops  # noqa: E402
from app.box_console import devices as dev_mod  # noqa: E402


# ----------------------------- 辅助：构造内存态配置 -----------------------------

def _cfg(devices=None, models=None):
    return {
        "devices": list(devices or []),
        "models": list(models or []),
        "cloud": {"host": "127.0.0.1", "agent_port": 42083},
    }


def _dev(name, model="lora-temp-model", node="nt001", protocol="lora", cloud_device=""):
    return {
        "name": name, "namespace": "default", "model": model, "node": node,
        "protocol": protocol, "collectCycle": 5000, "cloudDevice": cloud_device,
        "comm": {}, "opcua": {}, "bluetooth": {}, "lora": {"devEUI": "0120560100000245", "slaveId": 7},
        "cellular": {}, "properties": [{"name": "temperature", "type": "int", "scale": 0.1}],
        "yaml": "kind: Device\n", "status": "reporting",
    }


def _model(name="lora-temp-model", props=None):
    return {
        "name": name, "namespace": "default", "protocol": "lora",
        "properties": list(props if props is not None else [{"name": "temperature", "type": "int", "scale": 0.1}]),
        "yaml": "kind: DeviceModel\n",
    }


@pytest.fixture()
def mem_cfg(monkeypatch):
    """把 devices/cloud_ops 的配置读写重定向到内存，避免污染真实 config/box_devices.json。"""

    def make(seed):
        box = {"data": seed}

        def _load():
            return box["data"]

        def _save(d):
            box["data"] = d

        return box, _load, _save

    def _install(seed):
        box, load, save = make(seed)
        monkeypatch.setattr(dev_mod, "_load_devices", load)
        monkeypatch.setattr(dev_mod, "_save_devices", save)
        monkeypatch.setattr(cloud_ops, "_load_devices", load)
        monkeypatch.setattr(cloud_ops, "_save_devices", save)
        return box

    return _install


@pytest.fixture()
def no_cloud(monkeypatch):
    """默认让云端调用「成功下发但没有任何可确认输出」，删除动作记录下来。"""
    calls = {"apply": [], "delete": [], "exists": None}

    def _apply(device_name=None, dry_run=False, model_name=None):
        calls["apply"].append(device_name)
        return {"ok": True, "rc": 0, "stdout": "", "stderr": "", "applied": [device_name]}

    def _delete(kind, name, namespace):
        calls["delete"].append((kind, name, namespace))
        return {"ok": True, "rc": 0, "stdout": "", "stderr": "", "deleted": [kind]}

    monkeypatch.setattr(cloud_ops, "apply_devices_to_cloud", _apply)
    monkeypatch.setattr(cloud_ops, "_cloud_delete_crds", _delete)
    monkeypatch.setattr(cloud_ops, "_cloud_device_exists",
                        lambda name, namespace="default": bool(calls["exists"]))
    monkeypatch.setattr(dev_mod, "apply_devices_to_cloud", _apply)
    return calls


# ----------------------------- 1. 改名目标名冲突 -----------------------------

def test_rename_to_existing_name_is_rejected(mem_cfg, no_cloud):
    mem_cfg(_cfg(devices=[_dev("shuitong-temp"), _dev("env-temp")], models=[_model()]))
    with pytest.raises(ValueError) as ei:
        dev_mod.create_device({
            "mode": "apply", "deviceName": "env-temp", "origName": "shuitong-temp",
            "modelName": "lora-temp-model", "protocol": "lora", "nodeName": "nt001",
            "collectCycle": 5000, "properties": _model()["properties"],
        })
    assert "已被其它设备占用" in str(ei.value)
    # 未下发、未删除任何云端对象
    assert no_cloud["apply"] == []
    assert no_cloud["delete"] == []


# ----------------------------- 2~5. 旧 CRD 删除策略 -----------------------------

def test_old_crd_kept_when_new_device_not_confirmed(mem_cfg, no_cloud):
    mem_cfg(_cfg(devices=[_dev("env-temp")], models=[_model()]))
    # apply 成功但输出里没有目标 Device 文档、云端也查不到 → 不删旧 CRD
    r = cloud_ops._auto_sync_cloud("env-temp", "default", "shuitong-temp")
    assert r["ok"] is True
    assert r["old_crd_removed"] is False
    assert r["old_crd_kept"] == "shuitong-temp"
    assert no_cloud["delete"] == []


def test_old_crd_removed_when_new_device_confirmed(mem_cfg, no_cloud):
    # 改名保存后的本地态：旧名记录已移除，且没有设备再引用旧名
    mem_cfg(_cfg(devices=[_dev("env-temp")], models=[_model()]))
    no_cloud["exists"] = True
    r = cloud_ops._auto_sync_cloud("env-temp", "default", "shuitong-temp")
    assert r["old_crd_removed"] is True
    assert no_cloud["delete"] == [("device", "shuitong-temp", "default")]


def test_old_crd_kept_when_names_are_same_k8s_object(no_cloud):
    no_cloud["exists"] = True
    r = cloud_ops._auto_sync_cloud("shuitong-temp", "default", "shuitong_temp")
    assert r["old_crd_removed"] is False
    assert "同一对象" in (r.get("old_crd_reason") or "")
    assert no_cloud["delete"] == []


def test_old_crd_kept_when_old_name_still_bound(mem_cfg, no_cloud):
    # 另一台设备通过 cloudDevice 绑定到旧名
    mem_cfg(_cfg(devices=[_dev("server-temp", cloud_device="shuitong-temp")], models=[_model()]))
    no_cloud["exists"] = True
    r = cloud_ops._auto_sync_cloud("env-temp", "default", "shuitong-temp")
    assert r["old_crd_removed"] is False
    assert "仍被其它设备引用" in (r.get("old_crd_reason") or "")
    assert no_cloud["delete"] == []


def test_k8s_name_equal():
    assert cloud_ops._k8s_name_equal("shuitong_temp", "shuitong-temp") is True
    assert cloud_ops._k8s_name_equal("Env-Temp", "env-temp") is True
    assert cloud_ops._k8s_name_equal("shuitong-temp", "env-temp") is False
    assert cloud_ops._k8s_name_equal("", "") is False


def test_applied_device_confirmed_parses_kubectl_output():
    res = {"stdout": "devicemodel.devices.kubeedge.io/lora-temp-model configured\n"
                     "device.devices.kubeedge.io/env-temp created\n"}
    assert cloud_ops._applied_device_confirmed(res, "env-temp") is True
    assert cloud_ops._applied_device_confirmed(res, "shuitong-temp") is False
    assert cloud_ops._applied_device_confirmed({"stdout": ""}, "env-temp") is False


# ----------------------------- 6. 共享模型点位不被清空 -----------------------------

def test_save_device_without_properties_keeps_model_points(mem_cfg, no_cloud):
    box = mem_cfg(_cfg(devices=[_dev("shuitong-temp"), _dev("env-temp")], models=[_model()]))
    no_cloud["exists"] = True
    dev_mod.create_device({
        "mode": "apply", "deviceName": "shuitong-temp", "origName": "shuitong-temp",
        "modelName": "lora-temp-model", "protocol": "lora", "nodeName": "nt001",
        "collectCycle": 5000,
        # 未携带 properties（前端模型承载点位时可能出现）
    })
    model = next(m for m in box["data"]["models"] if m["name"] == "lora-temp-model")
    assert model["properties"], "共享模型点位不得被保存设备请求清空"
    for d in box["data"]["devices"]:
        assert d["properties"], f"设备 {d['name']} 点位不得被级联清空"


def test_rename_syncs_sibling_devices(mem_cfg, no_cloud):
    """改名后同模型被重刷 YAML 的其它设备也要一并发下（避免本地改了云端没改）。"""
    calls = no_cloud

    def _apply(device_name=None, dry_run=False, model_name=None):
        calls["apply"].append(device_name)
        return {"ok": True, "rc": 0, "stdout": "", "stderr": "", "applied": [device_name]}

    cloud_ops.apply_devices_to_cloud = _apply  # noqa: F811
    calls["exists"] = True
    r = cloud_ops._auto_sync_cloud("shuitong-temp", "default", "water-temp",
                                   extra_devices=["env-temp", "server-temp"])
    assert r["ok"] is True
    assert "shuitong-temp" in calls["apply"]
    assert "env-temp" in calls["apply"] and "server-temp" in calls["apply"]
    assert calls["delete"] == [("device", "water-temp", "default")]
