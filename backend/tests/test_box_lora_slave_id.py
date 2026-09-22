"""LoRa 设备「从站号（slaveId）」回归测试（2026-09-21）。

现场一台 LoRa 透传 DTU（DR206）下挂多台 485 传感器，共用同一个 devEUI，靠各自从站号区分
（如 shuitong-temp=站7、env-temp=站2、server-temp=站8）。此前平台侧只有 Modbus 有从站号
（comm.slaveID），LoRa 设备的从站号虽然存在配置里（lora.slaveId）却既不展示也不可编辑、
更不会写进下发的 Device YAML，等于配了也发不下去。

本文件锁住：
1. LoRa 设备 YAML 的 protocol.configData 输出 slaveId（随下发到达边缘）；
2. 未配置时输出 0（被动上报，不下发问帧）；
3. 保存/编辑设备时 lora.slaveId 原样保留（不丢失、不被清零）；
4. Modbus 仍走 comm.slaveID，不受影响。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.box_console import cloud_ops  # noqa: E402
from app.box_console import devices as dev_mod  # noqa: E402

generate_device_yaml = dev_mod.generate_device_yaml


def _payload(**over):
    base = {
        "modelName": "lora-temp-model", "deviceName": "shuitong-temp", "namespace": "default",
        "nodeName": "nt001", "collectCycle": 5000, "protocol": "lora",
        "comm": {}, "opcua": {}, "bluetooth": {}, "cellular": {},
        "lora": {"broker": "127.0.0.1", "port": 1883, "applicationID": "0ce81243",
                 "devEUI": "0120560100000245", "slaveId": 7},
        "properties": [{"name": "temperature", "type": "int", "scale": 0.1}],
    }
    base.update(over)
    return base


def test_lora_yaml_outputs_slave_id():
    y = generate_device_yaml(_payload())
    assert "slaveId: 7" in y["device"], "LoRa 设备 YAML 必须带从站号，否则边缘无法按站号寻址"


def test_lora_yaml_slave_id_defaults_to_zero():
    y = generate_device_yaml(_payload(lora={"devEUI": "0120560100000245"}))
    assert "slaveId: 0" in y["device"]


def test_lora_yaml_keeps_deveui():
    y = generate_device_yaml(_payload())
    assert "0120560100000245" in y["device"]


def test_modbus_yaml_still_uses_comm_slave_id():
    y = generate_device_yaml(_payload(
        protocol="modbus",
        comm={"commType": "serial", "slaveID": 6, "serialPort": "/dev/ttyRS485", "baudRate": 9600},
    ))
    assert "slaveID: 6" in y["device"]


def test_create_device_persists_lora_slave_id(monkeypatch):
    box = {"data": {"devices": [], "models": [{
        "name": "lora-temp-model", "namespace": "default", "protocol": "lora",
        "properties": [{"name": "temperature", "type": "int", "scale": 0.1}], "yaml": "",
    }]}}
    monkeypatch.setattr(dev_mod, "_load_devices", lambda: box["data"])
    monkeypatch.setattr(dev_mod, "_save_devices", lambda d: box.__setitem__("data", d))
    monkeypatch.setattr(cloud_ops, "apply_devices_to_cloud",
                        lambda **kw: {"ok": True, "rc": 0, "stdout": "", "stderr": "", "applied": []})
    monkeypatch.setattr(cloud_ops, "_cloud_delete_crds",
                        lambda *a, **kw: {"ok": True, "rc": 0, "stdout": "", "stderr": ""})

    dev_mod.create_device(dict(_payload(), mode="apply"))
    saved = next(d for d in box["data"]["devices"] if d["name"] == "shuitong-temp")
    assert saved["lora"]["slaveId"] == 7, "保存设备不得丢失 LoRa 从站号"
    assert "slaveId: 7" in saved["yaml"], "存盘 YAML 应与渲染结果一致（含从站号）"


def test_edit_device_keeps_lora_slave_id(monkeypatch):
    """改设备名/其它字段后从站号必须保留（同一 DTU 下靠它区分设备）。"""
    existing = {
        "name": "shuitong-temp", "namespace": "default", "model": "lora-temp-model", "node": "nt001",
        "protocol": "lora", "collectCycle": 5000, "cloudDevice": "", "comm": {}, "opcua": {},
        "bluetooth": {}, "cellular": {},
        "lora": {"broker": "127.0.0.1", "port": 1883, "applicationID": "0ce81243",
                 "devEUI": "0120560100000245", "slaveId": 7},
        "properties": [{"name": "temperature", "type": "int", "scale": 0.1}],
        "yaml": "kind: Device\n", "status": "reporting",
    }
    box = {"data": {"devices": [existing], "models": [{
        "name": "lora-temp-model", "namespace": "default", "protocol": "lora",
        "properties": [{"name": "temperature", "type": "int", "scale": 0.1}], "yaml": "",
    }]}}
    monkeypatch.setattr(dev_mod, "_load_devices", lambda: box["data"])
    monkeypatch.setattr(dev_mod, "_save_devices", lambda d: box.__setitem__("data", d))
    monkeypatch.setattr(cloud_ops, "apply_devices_to_cloud", lambda **kw: {
        "ok": True, "rc": 0,
        "stdout": "device.devices.kubeedge.io/shuitong-temp2 configured\n", "stderr": "", "applied": []})
    monkeypatch.setattr(cloud_ops, "_cloud_delete_crds",
                        lambda *a, **kw: {"ok": True, "rc": 0, "stdout": "", "stderr": ""})
    monkeypatch.setattr(cloud_ops, "_cloud_device_exists", lambda *a, **kw: True)

    dev_mod.create_device(dict(_payload(deviceName="shuitong-temp2", origName="shuitong-temp"), mode="apply"))
    saved = next(d for d in box["data"]["devices"] if d["name"] == "shuitong-temp2")
    assert saved["lora"]["slaveId"] == 7
    assert saved["lora"]["devEUI"] == "0120560100000245"
