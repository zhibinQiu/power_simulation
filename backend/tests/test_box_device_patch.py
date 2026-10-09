"""Modbus 直连设备的盒子下发条目（backend/app/box_console/lora_dtu.py）。

背景（2026-09-28 zhileng-power 离线事故）：平台保存设备只把 LoRa 设备的问帧推给盒子，
Modbus 设备的从站号/串口/周期改动留在平台本地与云端 CRD 里，盒子 config.json 不更新 ——
平台把 zhileng-power 的从站号 1→3 之后，盒子仍按站 3 取数（现场站 3 无设备），设备静默
无数据 6 天，平台侧看配置"一切正常"。

这里锁住两条口径：
① 平台 comm → 盒子条目：从站号/串口/波特率/校验位/采集周期/点位（线圈不算采集点位，
   input 寄存器走 FC4、其余 FC3，limit≥2 的整数按 int32 解）；
② 以盒子现配置为底稿：平台参数覆盖通信字段，点位沿用盒子正在跑的那份（现场常手工调过），
   不产生 enabled=false 的停采条目。
"""
from __future__ import annotations

from app.box_console import lora_dtu


POWER = {
    "name": "zhileng-power",
    "protocol": "modbus",
    "namespace": "default",
    "node": "nt001",
    "collectCycle": 2000,
    "hwId": "mb-ttyrs485-s1",
    "comm": {"commType": "serial", "serialPort": "/dev/ttyRS485", "baudRate": 9600,
             "dataBits": 8, "parity": "none", "stopBits": 1, "slaveID": 1},
    "properties": [
        {"name": "voltage", "type": "int", "registerType": "inputRegister",
         "register": 0, "limit": 1, "scale": "0.01"},
        {"name": "flow_total", "type": "int", "registerType": "holdingRegister",
         "register": 12, "limit": 2, "scale": 0.01},
        # 线圈只做可写点位，不能进采集点位（mapper 只支持 FC3/FC4）
        {"name": "output_on", "type": "int", "registerType": "coil",
         "register": 0, "limit": 1, "scale": 1},
    ],
}


def test_modbus_entry_built_from_platform_config():
    entry = lora_dtu._direct_entry(POWER, None)
    assert entry["name"] == "zhileng-power"
    assert entry["protocol"] == "modbus-rtu"
    assert entry["modbus"]["slaveId"] == 1
    assert entry["serial"] == {"port": "/dev/ttyRS485", "baudrate": 9600,
                               "databits": 8, "parity": "N", "stopbits": 1}
    assert entry["interval"] == 2.0
    assert entry["enabled"] is True
    assert entry["hwId"] == "mb-ttyrs485-s1"
    pts = {p["property"]: p for p in entry["points"]}
    assert set(pts) == {"voltage", "flow_total"}          # 线圈被排除
    assert pts["voltage"]["fc"] == 4                      # inputRegister -> FC4
    assert pts["flow_total"]["fc"] == 3                   # holdingRegister -> FC3
    assert pts["flow_total"]["registerCount"] == 2 and pts["flow_total"]["type"] == "int32"
    assert pts["voltage"]["scale"] == 0.01                # 字符串 scale 也要归一成数值


POWER_WR = dict(POWER, properties=[
    {"name": "voltage", "type": "int", "registerType": "inputRegister",
     "register": 0, "limit": 1, "scale": "0.01"},
    # 保持寄存器可写：0~2400 原始值 = 0~24.00V 工程值
    {"name": "voltage_set", "type": "int", "accessMode": "rw",
     "registerType": "holdingRegister", "register": 0, "limit": 1,
     "scale": "0.01", "min": 0, "max": 24},
    # 线圈可写：打开输出
    {"name": "output_on", "type": "int", "accessMode": "rw",
     "registerType": "coil", "register": 0, "limit": 1, "scale": 1},
    # 只读点位不进 writes
    {"name": "work_mode_actual", "type": "int", "accessMode": "r",
     "registerType": "inputRegister", "register": 6, "limit": 1, "scale": 1},
])


def test_modbus_writes_derived_from_access_mode():
    """可写点位由 accessMode=rw 派生：盒子写命令只认 config.json 的 writes[]。"""
    entry = lora_dtu._direct_entry(POWER_WR, None)
    ws = {w["property"]: w for w in entry["writes"]}
    assert set(ws) == {"voltage_set", "output_on"}
    # 工程值 -> 原始值：scale 取倒数，上下限按同一系数换算
    assert ws["voltage_set"]["kind"] == "holding"
    assert ws["voltage_set"]["registerAddr"] == 0
    assert ws["voltage_set"]["scale"] == 100
    assert (ws["voltage_set"]["min"], ws["voltage_set"]["max"]) == (0, 2400)
    assert ws["output_on"]["kind"] == "coil" and ws["output_on"]["coilAddr"] == 0


def test_modbus_writes_keeps_box_only_entries():
    """平台派生项优先（平台是可写性配置源），盒子手配的独有项保留。"""
    snap = {"name": "zhileng-power", "protocol": "modbus-rtu",
            "writes": [{"property": "voltage_set", "registerAddr": 0, "scale": 1},
                       {"property": "factory_only", "registerAddr": 99, "kind": "holding"}]}
    entry = lora_dtu._direct_entry(POWER_WR, snap)
    ws = {w["property"]: w for w in entry["writes"]}
    assert ws["voltage_set"]["scale"] == 100          # 平台口径覆盖盒子旧值
    assert ws["factory_only"]["registerAddr"] == 99   # 现场独有项不被冲掉
    assert "output_on" in ws


def test_modbus_entry_keeps_box_points_but_applies_platform_slave():
    """以盒子现配置为底稿：平台从站号必须生效，盒子手调的点位不被平台覆盖。"""
    snap = {"name": "zhileng-power", "protocol": "modbus-rtu", "interval": 2.0,
            "serial": {"port": "/dev/ttyRS485", "baudrate": 9600, "databits": 8,
                       "parity": "N", "stopbits": 1},
            "modbus": {"slaveId": 3, "byteOrder": "1234"},
            "points": [{"property": "voltage", "registerAddr": 0, "registerCount": 1,
                        "type": "int16", "scale": 0.01, "fc": 4}],
            "writes": [{"property": "voltage_set", "registerAddr": 0, "kind": "holding"}]}
    dev = dict(POWER, comm=dict(POWER["comm"], slaveID=1))
    entry = lora_dtu._direct_entry(dev, snap)
    assert entry["modbus"]["slaveId"] == 1                # 平台改了从站号 -> 盒子必须跟着改
    assert entry["points"] == snap["points"]              # 现场定制点位沿用
    assert entry["writes"] == snap["writes"]              # 可写点位不被冲掉


def test_build_patches_includes_modbus_device():
    built = lora_dtu.build_patches([POWER], None)
    names = [p["name"] for p in built["patches"]]
    assert "zhileng-power" in names
    entry = [p for p in built["patches"] if p["name"] == "zhileng-power"][0]
    assert entry["enabled"] is True
    assert entry["modbus"]["slaveId"] == 1
    assert not built["remove"]                            # Modbus 条目不进删除名单


def test_modbus_tcp_entry_uses_tcp_block():
    dev = dict(POWER, comm={"commType": "tcp", "tcpIP": "192.168.1.10", "tcpPort": 502,
                            "slaveID": 4})
    entry = lora_dtu._direct_entry(dev, None)
    assert entry["protocol"] == "modbus-tcp"
    assert entry["tcp"] == {"host": "192.168.1.10", "port": 502}
    assert "serial" not in entry
    assert entry["modbus"]["slaveId"] == 4


def test_lora_sync_dry_run_carries_modbus_patch(monkeypatch):
    published = []
    monkeypatch.setattr(lora_dtu, "_load_devices", lambda: {"devices": [POWER]})
    def _publish(box, payload):
        published.append((box, payload))
        return {"ok": True, "topic": "cmd/%s/config" % box}

    monkeypatch.setattr(lora_dtu.mqtt_source, "publish_box_cmd", _publish)
    monkeypatch.setattr(lora_dtu, "fetch_box_devices", lambda box, timeout=8.0: None)
    res = lora_dtu.lora_sync(box="nt001", dry_run=True)
    assert res["ok"] and published == []
    patch = [p for p in res["patches"] if p["name"] == "zhileng-power"][0]
    assert patch["modbus"]["slaveId"] == 1

    res = lora_dtu.lora_sync(box="nt001", dry_run=False)
    assert res["ok"] and res["applied"]
    payload = published[-1][1]
    assert payload["cmd"] == "config" and payload["replace"] is False
    assert [d["name"] for d in payload["devices"]] == ["zhileng-power"]
