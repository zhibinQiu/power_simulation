"""LoRa 透传 DTU 多从站问帧（backend/app/box_console/lora_dtu.py）回归测试。

锁住两类口径：
① 拼帧口径 —— 平台按从站号生成的问帧必须与现场在 LoRa NS 上手工测通的帧逐字节一致
   （站7=070300000001846c / 站2=0203000000018439 / 站8=0803000000018493；
   历史上从站号写成 1 时发的是 010300000001840a，终端不应答，设备长期"离线"）；
② 分组口径 —— 同一 devEUI 下挂多台传感器时只留一个主设备条目采集（带 lora.polls），
   其余从设备条目停采集，由主设备按站号路由上报，否则多台设备会互抢同一个 DTU 的下行窗口。
"""
from __future__ import annotations

import pytest

from app.box_console import lora_dtu


def _dev(name, eui, slave, reg_type=None, register=None):
    prop = {"name": "temperature", "type": "int", "scale": 0.1}
    if reg_type:
        prop["registerType"] = reg_type
    if register is not None:
        prop["register"] = register
    return {"name": name, "protocol": "lora",
            "lora": {"devEUI": eui, "slaveId": slave,
                     "downlink": {"enabled": True, "fPort": 10, "timeout": 5}},
            "properties": [prop]}


DEVICES = [
    _dev("shuitong-temp", "0120560100000245", 7),
    _dev("servers-temp", "0120560100000245", 2),
    _dev("server-temp", "0120560100000264", 8),
]


# --------------------------- 拼帧 ---------------------------
def test_read_frame_matches_field_verified_frames():
    """与现场 NS 手工测通的帧逐字节一致（站号写错就变成 010300000001840a）。"""
    assert lora_dtu.build_read_frame(7, 0, 1) == "070300000001846c"
    assert lora_dtu.build_read_frame(2, 0, 1) == "0203000000018439"
    assert lora_dtu.build_read_frame(8, 0, 1) == "0803000000018493"
    assert lora_dtu.build_read_frame(1, 0, 1) == "010300000001840a"


def test_register_span_uses_fc4_for_input_register():
    props = [{"name": "t", "type": "int", "registerType": "inputRegister", "register": 1}]
    assert lora_dtu._register_span(props) == (1, 1, 4)


def test_register_span_covers_all_points():
    props = [{"name": "a", "type": "int", "register": 2},
             {"name": "b", "type": "float", "register": 0}]
    addr, count, fc = lora_dtu._register_span(props)
    assert (addr, count, fc) == (0, 3, 3)      # 0 号起，float 占 2 个寄存器，共 3 个


# --------------------------- 分组（只反映现场拓扑） ---------------------------
def test_plan_groups_by_dev_eui():
    pl = lora_dtu.lora_plan(DEVICES)
    assert len(pl["groups"]) == 2
    g0 = pl["groups"][0]
    assert g0["devEUI"] == "0120560100000245"
    assert g0["members"] == ["shuitong-temp", "servers-temp"]
    # 每台设备各有一条属于自己的问帧；devEUI 只说明它们挂在同一终端下
    assert [p["slave"] for p in g0["polls"]] == [7, 2]
    assert [p["device"] for p in g0["polls"]] == ["shuitong-temp", "servers-temp"]
    assert [p["hex"] for p in g0["polls"]] == ["070300000001846c", "0203000000018439"]
    assert "master" not in g0                      # 不存在主/master 这一身份
    assert pl["groups"][1]["members"] == ["server-temp"]


def test_plan_skips_devices_without_eui_or_slave():
    devs = [_dev("no-eui", "", 3), _dev("passive", "0120560100000245", 0)]
    pl = lora_dtu.lora_plan(devs)
    assert pl["groups"] == []
    assert {s["name"] for s in pl["skipped"]} == {"no-eui", "passive"}
    assert "从站号为 0" in pl["skipped"][1]["reason"]


def test_plan_ignores_non_lora_protocols():
    pl = lora_dtu.lora_plan([{"name": "flow", "protocol": "modbus", "lora": {"devEUI": "abc", "slaveId": 1}}])
    assert pl["groups"] == [] and pl["skipped"] == []


# --------------------------- 下发条目 ---------------------------
def test_patches_one_reader_per_terminal():
    """同一 devEUI 只留主设备串行轮询全组从站，成员停采、由主设备按站号代报。

    多台设备各起一个采集线程向同一台 DTU 下发问帧会互相顶掉应答：实测 4 台温度
    各 5s 独立下发时抓包 3 次里只有 1 次回数据，四台读数一路老化到几分钟。
    """
    built = lora_dtu.build_patches(DEVICES, None)
    by_name = {p["name"]: p for p in built["patches"]}

    a = by_name["shuitong-temp"]            # 0245 组内第一台 -> 主设备
    assert a["enabled"] is True
    assert [p["slave"] for p in a["lora"]["polls"]] == [2, 7]    # 整组从站，按站号升序
    assert [p["device"] for p in a["lora"]["polls"]] == ["servers-temp", "shuitong-temp"]
    assert [p["hex"] for p in a["lora"]["polls"]] == ["0203000000018439", "070300000001846c"]
    assert a["lora"]["downlink"]["enabled"] is True
    assert a["lora"]["downlink"]["mode"] == "poll"
    assert a["lora"]["downlink"]["hex"] == ""      # 帧由各从站 poll 项自己的 hex 决定
    assert a["lora"]["slaveId"] == 7

    # 同组成员：不生成下发条目（读数由主设备按 polls[].device 代报），盒子配置里若
    # 还留着它的旧条目则随本次下发删除 —— 采集设备没有「停用」这一档。
    assert "servers-temp" not in by_name
    assert "servers-temp" in built["remove"]

    c = by_name["server-temp"]              # 0264 组只有它一台 -> 自己就是主设备
    assert c["enabled"] is True
    assert [p["slave"] for p in c["lora"]["polls"]] == [8]
    assert c["lora"]["polls"][0]["hex"] == "0803000000018493"

    ch = " ".join(built["changes"])
    assert "主设备" in ch and "代采" in ch


def test_patches_next_member_takes_over_when_primary_gone():
    """主设备被删除后，由组内剩下的设备顶上，整组不会失去采集能力。"""
    built = lora_dtu.build_patches([DEVICES[1]], None)   # 只剩 servers-temp（0245 组）
    by_name = {p["name"]: p for p in built["patches"]}
    assert list(by_name) == ["servers-temp"]
    assert by_name["servers-temp"]["enabled"] is True
    assert [p["slave"] for p in by_name["servers-temp"]["lora"]["polls"]] == [2]


def test_patches_keep_box_snapshot_custom_fields():
    """下发按 name 整条覆盖，因此必须以盒子现配置为底稿，保住现场定制字段。"""
    snap = [{"name": "shuitong-temp", "protocol": "lora", "interval": 5.0,
             "lora": {"devEUI": "0120560100000245", "slaveId": 7, "maxAge": 30,
                      "decode": {"scale": 1}, "username": "lora", "password": "x"},
             "points": [{"property": "temperature", "payloadKey": "temperature"}]}]
    built = lora_dtu.build_patches(DEVICES, snap)
    entry = [p for p in built["patches"] if p["name"] == "shuitong-temp"][0]
    assert entry["interval"] == 5.0
    assert entry["lora"]["maxAge"] == 30
    assert entry["lora"]["decode"] == {"scale": 1}
    assert entry["lora"]["username"] == "lora"           # 平台未配的项不被空值冲掉
    assert entry["points"][0]["payloadKey"] == "temperature"
    assert built["snapshot"] is True


def test_patches_empty_when_no_lora_devices():
    built = lora_dtu.build_patches([{"name": "f", "protocol": "modbus"}], None)
    assert built["patches"] == [] and built["changes"] == []


# --------------------------- 下发动作 ---------------------------
def test_lora_sync_dry_run_does_not_publish(monkeypatch):
    published = []
    monkeypatch.setattr(lora_dtu, "_load_devices", lambda: {"devices": DEVICES})
    monkeypatch.setattr(lora_dtu.mqtt_source, "publish_box_cmd",
                        lambda box, payload: published.append((box, payload)))
    monkeypatch.setattr(lora_dtu, "fetch_box_devices", lambda box, timeout=8.0: None)
    res = lora_dtu.lora_sync(box="nt001", dry_run=True)
    assert res["ok"] and res["dryRun"] is True
    assert published == []       # 预览不发布


def test_lora_sync_publishes_config_command(monkeypatch):
    published = []
    monkeypatch.setattr(lora_dtu, "_load_devices", lambda: {"devices": DEVICES})
    monkeypatch.setattr(lora_dtu.mqtt_source, "publish_box_cmd",
                        lambda box, payload: published.append((box, payload)) or {"ok": True, "topic": "cmd/nt001/deploy"})
    monkeypatch.setattr(lora_dtu, "fetch_box_devices", lambda box, timeout=8.0: None)
    res = lora_dtu.lora_sync(box="nt001")
    assert res["ok"] and res["applied"] is True
    assert len(published) == 1
    box, payload = published[0]
    assert box == "nt001"
    assert payload["cmd"] == "config" and payload["replace"] is False
    # 主设备各一台；servers-temp 是 0245 组成员，由主设备代采，不进 devices
    assert {d["name"] for d in payload["devices"]} == {"shuitong-temp", "server-temp"}
    assert payload["remove"] == ["servers-temp"]
    # 平台 LoRa 设备全集（含代采成员）：盒子据此清掉名单外的 lora 残留条目
    assert payload["lora_names"] == ["server-temp", "servers-temp", "shuitong-temp"]


def test_deleted_device_is_removed_from_box_not_disabled(monkeypatch):
    """平台上删掉的设备：不进下发条目，且从盒子配置里真正删除（不是留停采条目）。"""
    published = []
    monkeypatch.setattr(lora_dtu, "_load_devices", lambda: {"devices": DEVICES})
    monkeypatch.setattr(lora_dtu.mqtt_source, "publish_box_cmd",
                        lambda box, payload: published.append((box, payload)) or {"ok": True, "topic": "cmd/nt001/deploy"})
    # 盒子上还留着两条：zhileng-temp（平台已删）、server-temp（平台仍在）
    snap = [{"name": "zhileng-temp", "protocol": "lora", "interval": 5.0,
             "lora": {"devEUI": "0120560100000245", "slaveId": 7}},
            {"name": "server-temp", "protocol": "lora", "interval": 5.0,
             "lora": {"devEUI": "0120560100000264", "slaveId": 8}}]
    monkeypatch.setattr(lora_dtu, "fetch_box_devices", lambda box, timeout=8.0: snap)
    res = lora_dtu.lora_sync(box="nt001")
    _, payload = published[0]
    assert "zhileng-temp" in payload["remove"]          # 平台已无 -> 删除
    assert "server-temp" in {d["name"] for d in payload["devices"]}
    # 绝不能出现 enabled=false 的停采条目
    assert all(d.get("enabled") is True for d in payload["devices"])
    assert "servers-temp" in res["remove"]              # 代采成员同样从盒子删除


def test_lora_sync_requires_box(monkeypatch):
    monkeypatch.setattr(lora_dtu, "_load_devices", lambda: {"devices": []})
    res = lora_dtu.lora_sync(box="")
    assert res["ok"] is False and "未指定盒子" in res["error"]


def test_lora_sync_no_lora_device_is_noop(monkeypatch):
    monkeypatch.setattr(lora_dtu, "_load_devices",
                        lambda: {"devices": [{"name": "f", "protocol": "modbus", "node": "nt001"}]})
    monkeypatch.setattr(lora_dtu, "fetch_box_devices", lambda box, timeout=8.0: None)
    res = lora_dtu.lora_sync(box="nt001")
    assert res["ok"] and res["applied"] is False and "无需下发" in res["note"]
