"""设备模型「可写属性数值范围」与写操作硬性限制（app/box_console/write_guard.py）。

用户诉求：在设备模型中，具备可写能力的属性（accessMode = rw）可以填写数值范围
（min / max）；引用该模型的设备在执行写操作（下发写设定命令、回写 twins）时，
写入值必须落在该范围内——越界或写入只读属性一律拒绝下发（硬性限制，不降级放行）。

验证重点：
- ① 范围解析优先级：设备可写点位（原始值按 scale 折算）> 设备属性（来自模型）> 模型属性；
- ② 写入值越界 / 写入只读属性被拒绝；未配置范围、未登记属性、非数值放行；
- ③ 下发命令（cmd/{box}/cmd，cmd=write）与回写 twins 两个写入入口都被拦截；
- ④ 模型可写属性在下发盒子时自动派生为可写点位（含换算后的寄存器原始值范围）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.box_console import realtime_data  # noqa: E402
from app.box_console import write_guard  # noqa: E402
from app.box_console.devices import to_mapper_device  # noqa: E402

MODEL_PROPS = [
    # 数控电源设定电压：0~24.00V（寄存器原始值 0~2400，points.scale = 0.01）
    {"name": "voltage_set", "type": "int", "accessMode": "rw",
     "registerType": "holdingRegister", "register": 10, "scale": 0.01,
     "unit": "V", "min": 0, "max": 24},
    # 只读采集量：不允许写入
    {"name": "temp", "type": "float", "accessMode": "r",
     "registerType": "holdingRegister", "register": 0},
    # 可写但未配置范围：不限制
    {"name": "output_on", "type": "int", "accessMode": "rw",
     "registerType": "coil", "register": 1},
]


def _data(writes=None, props=None, model_props=None):
    props = MODEL_PROPS if props is None else props
    model_props = props if model_props is None else model_props
    dev = {
        "name": "dev1", "model": "m1", "node": "nt001", "protocol": "modbus",
        "collectCycle": 1000, "namespace": "default",
        "comm": {"commType": "serial", "slaveID": 1, "serialPort": "/dev/ttyS0",
                 "baudRate": 9600},
        "properties": [dict(p) for p in props],
    }
    if writes is not None:
        dev["writes"] = writes
    return {"models": [{"name": "m1", "protocol": "modbus",
                        "properties": [dict(p) for p in model_props]}],
            "devices": [dev]}


@pytest.fixture
def dev(monkeypatch):
    data = _data()
    monkeypatch.setattr(write_guard, "_load_devices", lambda: data)
    return data


# ------------------------- ① 范围解析 -------------------------

def test_resolve_range_from_model_property(dev):
    r = write_guard.resolve_range("dev1", "voltage_set")
    assert r is not None and (r["min"], r["max"]) == (0.0, 24.0)
    assert r["source"] == "设备属性（来自模型）"


def test_resolve_range_from_model_when_device_props_missing(monkeypatch):
    """设备属性里没有该点位时，回落到其引用模型的属性范围。"""
    monkeypatch.setattr(write_guard, "_load_devices",
                        lambda: _data(props=[MODEL_PROPS[1]], model_props=MODEL_PROPS))
    r = write_guard.resolve_range("dev1", "voltage_set")
    assert r is not None and (r["min"], r["max"]) == (0.0, 24.0)
    assert r["source"] == "设备模型属性"


def test_resolve_range_none_when_unset(dev):
    assert write_guard.resolve_range("dev1", "output_on") is None
    assert write_guard.resolve_range("dev1", "not_exist") is None
    assert write_guard.resolve_range("no-such-device", "voltage_set") is None


def test_resolve_range_of_write_point_converted_by_scale(monkeypatch):
    """可写点位的 min/max 是寄存器原始值：按 scale 折算回工程值再比较。"""
    monkeypatch.setattr(write_guard, "_load_devices", lambda: _data(writes=[
        {"property": "voltage_set", "kind": "holding", "registerAddr": 10,
         "scale": 100, "min": 0, "max": 2400},
    ]))
    r = write_guard.resolve_range("dev1", "voltage_set")
    assert (r["min"], r["max"]) == (0.0, 24.0)
    assert r["source"] == "设备可写点位"


# ------------------------- ② 写入校验 -------------------------

def test_validate_write_within_range(dev):
    assert write_guard.validate_write("dev1", "voltage_set", 12).get("ok")
    assert write_guard.validate_write("dev1", "voltage_set", "0").get("ok")
    assert write_guard.validate_write("dev1", "voltage_set", 24).get("ok")


def test_validate_write_out_of_range(dev):
    low = write_guard.validate_write("dev1", "voltage_set", -1)
    high = write_guard.validate_write("dev1", "voltage_set", 24.5)
    assert low.get("ok") is False and "低于下限" in low.get("error", "")
    assert high.get("ok") is False and "高于上限" in high.get("error", "")


def test_validate_write_readonly_property_rejected(dev):
    res = write_guard.validate_write("dev1", "temp", 30)
    assert res.get("ok") is False and "只读" in res.get("error", "")


def test_validate_write_write_point_overrides_readonly(monkeypatch):
    """设备单独配置了可写点位时，即使模型属性标只读也允许写（显式配置优先）。"""
    monkeypatch.setattr(write_guard, "_load_devices", lambda: _data(writes=[
        {"property": "temp", "kind": "holding", "registerAddr": 3, "scale": 1},
    ]))
    assert write_guard.validate_write("dev1", "temp", 30).get("ok")


def test_validate_write_pass_when_no_range_or_unknown(dev):
    assert write_guard.validate_write("dev1", "output_on", 1).get("ok")
    assert write_guard.validate_write("dev1", "unknown_prop", 9999).get("ok")
    # 非数值（线圈布尔 / 字符串枚举）不做范围校验
    assert write_guard.validate_write("dev1", "voltage_set", True).get("ok")


# ------------------------- ③ 写入入口拦截 -------------------------

def test_cmd_payload_write_denied(dev):
    payload = json.dumps({"box": "nt001", "device": "dev1", "cmd": "write",
                          "property": "voltage_set", "value": 30})
    err = write_guard.validate_cmd_payload("cmd/nt001/cmd", payload)
    assert err and "高于上限" in err


def test_cmd_payload_write_allowed(dev):
    payload = {"box": "nt001", "device": "dev1", "cmd": "write",
               "property": "voltage_set", "value": 12}
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(payload)) is None


def test_cmd_payload_ignores_non_write(dev):
    read_payload = json.dumps({"box": "nt001", "device": "dev1", "cmd": "read"})
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", read_payload) is None
    # LoRa 下行（cmd=down）、其它主题、非 JSON 载荷一律放行
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", '{"cmd":"down"}') is None
    assert write_guard.validate_cmd_payload("data/nt001/dev1/x", "not-json") is None
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", "not-json") is None


def test_cmd_payload_ignores_inline_min_max(dev):
    """安全上下限只在设备配置中设置：命令载荷自带的 min/max 不再生效。

    output_on 是可写但未配置范围的属性 → 即使载荷夹带 min/max 也按「无范围」放行；
    而 voltage_set 在配置中为 0~24，载荷放宽到 0~1000 仍按配置范围拒绝。
    """
    payload = {"box": "nt001", "device": "dev1", "cmd": "write",
               "property": "output_on", "value": 70000, "min": 0, "max": 65535}
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(payload)) is None

    widened = {"box": "nt001", "device": "dev1", "cmd": "write",
               "property": "voltage_set", "value": 99, "min": 0, "max": 1000}
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(widened))


def test_publish_test_blocks_out_of_range(dev, monkeypatch):
    calls = []
    monkeypatch.setattr(realtime_data.mqtt_source, "publish",
                        lambda topic, payload: calls.append((topic, payload)) or {"ok": True})
    payload = json.dumps({"box": "nt001", "device": "dev1", "cmd": "write",
                          "property": "voltage_set", "value": 99})
    res = realtime_data.publish_test({"topic": "cmd/nt001/cmd", "payload": payload})
    assert res.get("ok") is False and "超出允许写入范围" in (res.get("error") or "")
    assert calls == []          # 越界一律不下发

    ok_payload = json.dumps({"box": "nt001", "device": "dev1", "cmd": "write",
                             "property": "voltage_set", "value": 12})
    res = realtime_data.publish_test({"topic": "cmd/nt001/cmd", "payload": ok_payload})
    assert res.get("ok") is True and len(calls) == 1


def test_ingest_device_value_blocks_out_of_range(dev, monkeypatch):
    calls = []
    monkeypatch.setattr(realtime_data.cloud_agent, "ingest",
                        lambda *a, **k: calls.append(a) or {"ok": True})
    res = realtime_data.ingest_device_value(
        {"device": "dev1", "namespace": "default", "property": "voltage_set", "value": 48})
    assert res.get("ok") is False and "已拒绝回写" in (res.get("error") or "")
    assert calls == []

    res = realtime_data.ingest_device_value(
        {"device": "dev1", "namespace": "default", "property": "voltage_set", "value": 12})
    assert res.get("ok") is True and len(calls) == 1


# ------------------------- ④ 配置规范化 -------------------------

def test_normalize_properties_keeps_range_only_for_writable():
    props = write_guard.normalize_properties([
        {"name": "a", "accessMode": "rw", "min": "1", "max": "10"},
        {"name": "b", "accessMode": "r", "min": 1, "max": 2},
        {"name": "c", "accessMode": "rw", "min": "abc", "max": 3},
        {"name": "d", "accessMode": "rw", "min": 9, "max": 1},   # 下限 > 上限：无效
    ])
    assert props[0]["min"] == 1.0 and props[0]["max"] == 10.0
    assert "min" not in props[1] and "max" not in props[1]
    assert "min" not in props[2] and props[2]["max"] == 3.0
    assert "min" not in props[3] and "max" not in props[3]


# ------------------------- ⑤ 裸写（addr 模式）：无安全范围一律拒绝 -------------------------

def test_cmd_payload_bare_addr_requires_range(dev):
    """裸写寄存器未带安全范围、配置中同地址也无范围 → 拒绝（fail-closed）。"""
    payload = {"box": "nt001", "device": "dev1", "cmd": "write",
               "addr": 5, "kind": "holding", "value": 100}
    err = write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(payload))
    assert err and "缺少安全范围" in err


def test_cmd_payload_bare_addr_uses_configured_range(monkeypatch):
    """裸写地址命中设备可写点位范围（寄存器原始值）时按该范围硬校验。"""
    monkeypatch.setattr(write_guard, "_load_devices", lambda: _data(writes=[
        {"property": "voltage_set", "kind": "holding", "registerAddr": 10,
         "scale": 100, "min": 0, "max": 2400},
    ]))
    ok = {"box": "nt001", "device": "dev1", "cmd": "write",
          "addr": 10, "kind": "holding", "value": 1200}
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(ok)) is None
    bad = dict(ok, value=2500)
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(bad))


def test_cmd_payload_bare_addr_ignores_inline_limits(dev):
    """裸写的安全范围同样只认设备配置：载荷自带 min/max 不能替代配置。"""
    base = {"box": "nt001", "device": "dev1", "cmd": "write",
            "addr": 5, "kind": "holding", "value": 100}
    # 配置中地址 5 无范围 → 带不带 min/max 都拒绝（fail-closed）
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(base))
    assert write_guard.validate_cmd_payload(
        "cmd/nt001/cmd", json.dumps(dict(base, min=0, max=200)))


def test_cmd_payload_bare_coil_uses_coil_range(monkeypatch):
    """线圈裸写按 coilAddr 命中范围（0/1）。"""
    monkeypatch.setattr(write_guard, "_load_devices", lambda: _data(writes=[
        {"property": "output_on", "kind": "coil", "coilAddr": 1, "min": 0, "max": 1},
    ]))
    ok = {"box": "nt001", "device": "dev1", "cmd": "write", "addr": 1, "kind": "coil", "value": 1}
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(ok)) is None
    bad = dict(ok, value=2)
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(bad))


# ------------------------- ⑤b 从站号只认设备配置 -------------------------

def test_config_slave_reads_device_config():
    dev = {"comm": {"slaveID": 3}, "modbus": {"slaveId": 9}}
    assert write_guard.config_slave(dev) == 3
    # LoRa 透传设备的从站号在 lora.slaveId
    assert write_guard.config_slave({"lora": {"slaveId": 7}}) == 7
    assert write_guard.config_slave({}) is None


def test_cmd_payload_rejects_mismatched_slave(dev):
    """从站号属于设备配置：命令里另行指定（与配置不符）一律拒绝。"""
    base = {"box": "nt001", "device": "dev1", "cmd": "write",
            "property": "voltage_set", "value": 12}
    # 配置从站号为 1，命令指定 7 → 拒绝（否则等于写到同一总线上的另一台设备）
    err = write_guard.validate_cmd_payload(
        "cmd/nt001/cmd", json.dumps(dict(base, slaveId=7)))
    assert err and "从站号" in err
    # 与配置一致 / 不带从站号 → 正常放行
    assert write_guard.validate_cmd_payload(
        "cmd/nt001/cmd", json.dumps(dict(base, slaveId=1))) is None
    assert write_guard.validate_cmd_payload("cmd/nt001/cmd", json.dumps(base)) is None


# ------------------------- ⑥ 全局出口：任何调用方都过同一硬约束 -------------------------

def test_mqtt_publish_outlet_blocks_out_of_range(dev):
    """唯一 MQTT 下发出口（前端 / 自动化 / 脚本 / AI 工具均经此）统一拦截。"""
    from app import mqtt_source
    payload = json.dumps({"box": "nt001", "device": "dev1", "cmd": "write",
                          "property": "voltage_set", "value": 99})
    res = mqtt_source.publish("cmd/nt001/cmd", payload)
    assert res.get("ok") is False and res.get("blocked") is True
    assert "设备写入硬性限制" in (res.get("error") or "")


def test_mqtt_publish_outlet_ignores_data_topics(dev, monkeypatch):
    """非命令主题（data/# 等）不受设备写入硬约束影响（仍按原逻辑发布）。"""
    from app import mqtt_source
    monkeypatch.setattr(mqtt_source._shared, "_PAHO_OK", False)
    r = mqtt_source.publish("data/nt001/dev1/x", '{"value":1}')
    assert r.get("blocked") is not True
    assert "paho-mqtt" in (r.get("error") or "")


def test_mqtt_publish_outlet_validates_device_config(dev):
    """设备配置整包（cmd/{box}/config）中可写点位范围非法时拒绝下发。"""
    from app import mqtt_source
    payload = {"cmd": "config", "box": "nt001", "devices": [
        {"name": "dev1", "writes": [{"property": "v", "kind": "holding",
                                     "registerAddr": 1, "min": 10, "max": 1}]}]}
    res = mqtt_source.publish("cmd/nt001/config", json.dumps(payload))
    assert res.get("ok") is False and "范围非法" in (res.get("error") or "")


def test_mqtt_publish_outlet_allows_deploy_topic(dev, monkeypatch):
    """应用部署主题（cmd/{box}/deploy）不是设备写值，不受数值范围限制。"""
    from app import mqtt_source
    monkeypatch.setattr(mqtt_source._shared, "_PAHO_OK", False)
    r = mqtt_source.publish("cmd/nt001/deploy", json.dumps({"cmd": "list"}))
    assert r.get("blocked") is not True


def test_mqtt_publish_outlet_blocks_write_smuggled_in_deploy(dev):
    """防旁路：写命令改发到 deploy 等其它命令主题时同样被硬约束拦截。"""
    from app import mqtt_source
    payload = {"cmd": "write", "box": "nt001", "device": "dev1",
               "property": "voltage_set", "value": 99}
    res = mqtt_source.publish("cmd/nt001/deploy", json.dumps(payload))
    assert res.get("ok") is False and res.get("blocked") is True


def test_mqtt_publish_outlet_blocks_bad_devices_in_deploy(dev):
    """防旁路：deploy 载荷夹带 devices 配置（范围非法）同样拒绝下发。"""
    from app import mqtt_source
    payload = {"cmd": "deploy", "box": "nt001", "devices": [
        {"name": "dev1", "writes": [{"property": "v", "kind": "holding",
                                     "registerAddr": 1, "min": 5, "max": 1}]}]}
    res = mqtt_source.publish("cmd/nt001/deploy", json.dumps(payload))
    assert res.get("ok") is False and "范围非法" in (res.get("error") or "")


def test_cloud_agent_ingest_outlet_blocks_out_of_range(dev, monkeypatch):
    """回写 twins 出口同样限幅：AI / 脚本直调 cloud_agent.ingest 也无法绕过。"""
    from app import cloud_agent
    calls = []
    monkeypatch.setattr(cloud_agent, "_http",
                        lambda *a, **k: calls.append(a) or (True, {"ok": True}, ""))
    bad = cloud_agent.ingest("dev1", "default", "voltage_set", 48)
    assert bad.get("ok") is False and calls == []
    good = cloud_agent.ingest("dev1", "default", "voltage_set", 12)
    assert good.get("ok") is True and len(calls) == 1


def test_guard_ingest_allows_readonly_report(dev):
    """数据上报语义：只读属性上报不受只读限制（只做数值范围限幅）。"""
    assert write_guard.guard_ingest("dev1", "temp", 30) is None


def test_write_device_value_entry_blocks_out_of_range(dev, monkeypatch):
    """统一写入入口（AI 训练 / 自动化 / 脚本推荐通道）：越界不发出任何消息。"""
    calls = []
    monkeypatch.setattr(realtime_data.mqtt_source, "publish",
                        lambda topic, payload: calls.append((topic, payload)) or {"ok": True})
    bad = realtime_data.write_device_value(
        {"box": "nt001", "device": "dev1", "property": "voltage_set", "value": 99})
    assert bad.get("ok") is False and bad.get("blocked") is True and calls == []
    good = realtime_data.write_device_value(
        {"box": "nt001", "device": "dev1", "property": "voltage_set", "value": 12})
    assert good.get("ok") is True and len(calls) == 1
    topic, payload = calls[0]
    assert topic == "cmd/nt001/cmd"
    assert payload.get("property") == "voltage_set" and payload.get("cmd") == "write"
    # 从站号取自设备配置，命令载荷里不携带 slave / slaveId
    assert "slave" not in payload and "slaveId" not in payload


def test_write_device_value_entry_bare_addr_needs_config_range(dev, monkeypatch):
    """统一入口的裸写同样 fail-closed：范围只认设备配置，载荷自带 min/max 不算。"""
    calls = []
    monkeypatch.setattr(realtime_data.mqtt_source, "publish",
                        lambda topic, payload: calls.append(topic) or {"ok": True})
    r = realtime_data.write_device_value(
        {"box": "nt001", "device": "dev1", "addr": 7, "kind": "holding", "value": 5})
    assert r.get("ok") is False and calls == []
    r2 = realtime_data.write_device_value(
        {"box": "nt001", "device": "dev1", "addr": 7, "kind": "holding",
         "value": 5, "min": 0, "max": 10})
    assert r2.get("ok") is False and calls == []
    # 在设备配置（可写点位）中给该地址配好范围后即可下发
    monkeypatch.setattr(write_guard, "_load_devices", lambda: _data(writes=[
        {"property": "voltage_set", "kind": "holding", "registerAddr": 7,
         "scale": 100, "min": 0, "max": 10},
    ]))
    r3 = realtime_data.write_device_value(
        {"box": "nt001", "device": "dev1", "addr": 7, "kind": "holding", "value": 5})
    assert r3.get("ok") is True and len(calls) == 1


# ------------------------- ⑦ 下发盒子：模型可写属性派生可写点位 -------------------------

def test_to_mapper_device_derives_writes_from_model_property():
    dev = _data()["devices"][0]
    mapper_dev = to_mapper_device(dev)
    writes = mapper_dev.get("writes") or []
    by_prop = {w["property"]: w for w in writes}
    assert set(by_prop) == {"voltage_set", "output_on"}
    # 工程值 0~24.00V、points.scale=0.01 → 盒子侧原始值 0~2400、writes.scale=100
    v = by_prop["voltage_set"]
    assert v["kind"] == "holding" and v["registerAddr"] == 10
    assert v["scale"] == 100 and v["min"] == 0 and v["max"] == 2400
    # 线圈类可写属性派生为线圈点位（不做数值范围换算）
    assert by_prop["output_on"]["kind"] == "coil" and by_prop["output_on"]["coilAddr"] == 1
    # 只读属性不派生
    assert "temp" not in by_prop


def test_to_mapper_device_keeps_manual_writes():
    manual = [{"property": "voltage_set", "kind": "holding", "registerAddr": 99,
               "scale": 1, "min": 0, "max": 24}]
    dev = _data(writes=manual)["devices"][0]
    writes = to_mapper_device(dev)["writes"]
    assert len(writes) == 2                      # 手工点位保留 + 其余模型可写属性派生
    assert [w for w in writes if w["property"] == "voltage_set"][0]["registerAddr"] == 99


def test_to_mapper_device_fills_manual_write_range_from_property():
    """手工可写点位没填 min/max 时，用同名模型属性范围补齐（换算成原始值）。"""
    manual = [{"property": "voltage_set", "kind": "holding", "registerAddr": 10,
               "scale": 100}]
    dev = _data(writes=manual)["devices"][0]
    w = [x for x in to_mapper_device(dev)["writes"]
         if x["property"] == "voltage_set"][0]
    assert (w["min"], w["max"]) == (0, 2400)     # 工程值 0~24V × scale 100
