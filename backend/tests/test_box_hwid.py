"""设备硬件唯一 ID（hwId）口径回归测试。

锁住三件事：
 ① hwId 由硬件特征派生（LoRa = DevEUI + 从站号；Modbus = 串口/IP + 从站号），
    同一台硬件改显示名后 hwId 不变 —— 这是「改名不断链」的根基；
 ② hwId 必须是 K8s label value 安全串（会写进 Device CRD 的 nengtan.io/hwid）；
 ③ 存量设备补齐（backfill）与改名继承（ensure_hwid(inherit=…)）的语义。
"""
import re

import pytest

from app.domain.box import DeviceYamlFactory
from app.domain.box.hwid import (
    HWID_LABEL,
    backfill_hwids,
    ensure_hwid,
    hwid_of,
    new_hwid,
    slug,
)

K8S_LABEL_VALUE = re.compile(r"^[a-zA-Z0-9]([-_.a-zA-Z0-9]*[a-zA-Z0-9])?$")


def _dev(**kw):
    base = {"name": "d", "protocol": "modbus", "comm": {}, "lora": {}, "opcua": {},
            "bluetooth": {}, "cellular": {}}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# ① 按硬件特征派生
# ---------------------------------------------------------------------------


def test_modbus_rtu_uses_port_and_slave():
    d = _dev(comm={"commType": "serial", "serialPort": "/dev/ttyRS485", "slaveID": 6})
    assert hwid_of(d) == "mb-ttyrs485-s6"


def test_modbus_tcp_uses_ip_port_slave():
    d = _dev(comm={"commType": "tcp", "tcpIP": "192.168.1.10", "tcpPort": 502, "slaveID": 1})
    # 分隔符一律折叠成 '-'（IP 的点号也折叠），保证 label value 安全
    assert hwid_of(d) == "mb-192-168-1-10-502-s1"


def test_lora_uses_deveui_and_slave():
    """同一台 LoRa DTU 下挂多个 485 传感器：DevEUI + 从站号才唯一（见现场 servers-temp）。"""
    a = _dev(protocol="lora", lora={"devEUI": "0120560100000245", "slaveId": 7})
    b = _dev(protocol="lora", lora={"devEUI": "0120560100000245", "slaveId": 2})
    assert hwid_of(a) == "lora-0120560100000245-s7"
    assert hwid_of(b) == "lora-0120560100000245-s2"
    assert hwid_of(a) != hwid_of(b)


def test_lora_without_slave_keeps_deveui_only():
    """从站号 0/空 = 终端自身上报（无下挂 485 传感器）。"""
    d = _dev(protocol="lora", lora={"devEUI": "0120560100000264", "slaveId": 0})
    assert hwid_of(d) == "lora-0120560100000264"


def test_fallback_random_when_no_hardware_feature():
    d = _dev(protocol="modbus", comm={})
    assert hwid_of(d) == ""
    rid = new_hwid()
    assert rid.startswith("dev-") and len(rid) == 16


def test_opcua_and_bluetooth_and_cellular():
    assert hwid_of(_dev(protocol="opcua", opcua={"url": "opc.tcp://127.0.0.1:4840"})) == \
        hwid_of(_dev(protocol="opcua", opcua={"url": "opc.tcp://127.0.0.1:4840"}))
    assert hwid_of(_dev(protocol="opcua", opcua={"url": "opc.tcp://127.0.0.1:4840"})) != \
        hwid_of(_dev(protocol="opcua", opcua={"url": "opc.tcp://127.0.0.1:4841"}))
    assert hwid_of(_dev(protocol="bluetooth",
                        bluetooth={"macAddress": "AA:BB:CC:DD:EE:FF"})) == ""   # 占位 MAC 不算
    assert hwid_of(_dev(protocol="bluetooth",
                        bluetooth={"macAddress": "11:22:33:44:55:66"})) == "bt-11-22-33-44-55-66"
    assert hwid_of(_dev(protocol="cellular", cellular={"imei": "867293058172"})).startswith("cel-")


# ---------------------------------------------------------------------------
# ② label value 安全性（会写进 Device CRD）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["/dev/ttyRS485", "opc.tcp://127.0.0.1:4840", "AA:BB:CC:DD:EE:FF",
                                 "0120560100000245", "中文名 测试"])
def test_hwid_is_k8s_label_safe(raw):
    d = _dev(protocol="lora", lora={"devEUI": raw, "slaveId": 3})
    h = hwid_of(d)
    assert K8S_LABEL_VALUE.match(h), h
    assert len(h) <= 63


def test_slug_trims_unsafe_chars():
    assert slug("/dev/ttyRS485") == "dev-ttyrs485"   # 路径分隔符也折叠成 '-'
    assert slug("") == ""


# ---------------------------------------------------------------------------
# ③ 继承 / 补齐 / 唯一性
# ---------------------------------------------------------------------------


def test_rename_inherits_hwid():
    """改名：沿用原设备的 hwId（名字变了，身份不变）。"""
    old = {"name": "old-name", "hwId": "mb-ttyrs485-s6"}
    new = _dev(name="new-name", comm={"commType": "serial", "serialPort": "/dev/ttyRS485", "slaveID": 6})
    assert ensure_hwid(new, inherit=old["hwId"]) == "mb-ttyrs485-s6"


def test_existing_hwid_wins_over_inherit():
    d = _dev(hwId="mb-ttyrs485-s9")
    assert ensure_hwid(d, inherit="mb-ttyrs485-s6") == "mb-ttyrs485-s9"


def test_conflict_appends_name_digest():
    """两台设备派生出同一个 hwId 时，后者追加名字摘要（不静默共用身份）。"""
    a = _dev(name="a", comm={"commType": "serial", "serialPort": "/dev/ttyUSB0", "slaveID": 1})
    b = _dev(name="b", comm={"commType": "serial", "serialPort": "/dev/ttyUSB0", "slaveID": 1})
    ha = ensure_hwid(a, taken=set())
    hb = ensure_hwid(b, taken={ha})
    assert ha != hb and hb.startswith(ha)


def test_backfill_fills_missing_and_dedups():
    devs = [
        {"name": "x", "protocol": "lora", "lora": {"devEUI": "eui-1", "slaveId": 7}, "comm": {}},
        {"name": "y", "protocol": "lora", "lora": {"devEUI": "eui-1", "slaveId": 7}, "comm": {}},
        {"name": "z", "hwId": "keep-me", "protocol": "modbus", "comm": {}, "lora": {}},
    ]
    filled = backfill_hwids(devs)
    assert filled == 2
    assert devs[2]["hwId"] == "keep-me"          # 已有不动
    assert devs[0]["hwId"] != devs[1]["hwId"]    # 冲突已去重


def test_backfill_is_idempotent():
    devs = [{"name": "x", "protocol": "modbus",
             "comm": {"commType": "serial", "serialPort": "/dev/ttyRS485", "slaveID": 6}, "lora": {}}]
    backfill_hwids(devs)
    first = devs[0]["hwId"]
    assert backfill_hwids(devs) == 0
    assert devs[0]["hwId"] == first


# ---------------------------------------------------------------------------
# ④ 写进 Device CRD
# ---------------------------------------------------------------------------


def test_device_yaml_carries_hwid_label():
    y = DeviceYamlFactory.get("modbus").render({
        "modelName": "m", "deviceName": "flow-meter", "namespace": "default",
        "nodeName": "nt001", "collectCycle": 1000, "protocol": "modbus",
        "hwId": "mb-ttyrs485-s6", "properties": [{"name": "flow"}],
        "comm": {"commType": "serial", "serialPort": "/dev/ttyRS485", "slaveID": 6},
        "opcua": {}, "bluetooth": {}, "lora": {}, "cellular": {},
    })
    assert f'{HWID_LABEL}: "mb-ttyrs485-s6"' in y["device"]


def test_device_yaml_omits_empty_hwid():
    y = DeviceYamlFactory.get("modbus").render({
        "modelName": "m", "deviceName": "d", "namespace": "default", "nodeName": "n",
        "collectCycle": 1000, "protocol": "modbus", "properties": [{"name": "v"}],
        "comm": {}, "opcua": {}, "bluetooth": {}, "lora": {}, "cellular": {},
    })
    assert HWID_LABEL not in y["device"]
