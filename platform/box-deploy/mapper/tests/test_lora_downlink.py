#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LoRaWAN 下行（Class C 主动取数）单元测试。

mapper 依赖 grpc / api_pb2 等边缘侧运行时（盒子上有、开发机没有），
这里用 stub 注入 sys.modules 后按文件加载 box_mapper.py，只测下行逻辑，
不触碰串口/DMI/网络。运行：python3 tests/test_lora_downlink.py
"""
import os
import sys
import json
import time
import types
import base64
import threading
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPER = os.path.join(os.path.dirname(HERE), "box_mapper.py")


# --------------------------------------------------------------------------
# stub：grpc / protobuf（仅满足 import，测试不使用）
# --------------------------------------------------------------------------
class _AutoModule(types.ModuleType):
    """任何未定义属性都自动返回一个同名占位类（满足 pb/pb_grpc 的模块级引用）。"""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (object,), {})
        setattr(self, name, cls)
        return cls


def _stub_modules():
    def mod(name, cls=_AutoModule, **attrs):
        m = cls(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    if "grpc" not in sys.modules:
        grpc = mod("grpc", cls=types.ModuleType)
        grpc.insecure_channel = lambda *a, **k: None
        grpc.server = lambda *a, **k: None
        grpc.RpcError = type("RpcError", (Exception,), {})
        mod("api_pb2")
        mod("api_pb2_grpc")
        google = mod("google", cls=types.ModuleType)
        google.protobuf = mod("google.protobuf", cls=types.ModuleType)
        mod("google.protobuf.any_pb2")
        mod("google.protobuf.wrappers_pb2")


def load_mapper():
    _stub_modules()
    os.environ.setdefault("CONFIG_PATH", os.path.join(HERE, "fixtures", "config_lora.json"))
    spec = importlib.util.spec_from_file_location("box_mapper_under_test", MAPPER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BM = load_mapper()


# --------------------------------------------------------------------------
# 测试替身
# --------------------------------------------------------------------------
class FakeInfo:
    def wait_for_publish(self, t=0.1):
        return True


class FakeCli:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, json.loads(payload), qos))
        return FakeInfo()


def make_reader(downlink=None, dev_eui="0011223344556677", app_id="1",
                decode=None, points=None, polls=None):
    cfg = {
        "broker": "127.0.0.1",
        "port": 41884,
        "applicationID": app_id,
        "devEUI": dev_eui,
        "maxAge": 0,
    }
    if downlink is not None:
        cfg["downlink"] = downlink
    if decode is not None:
        cfg["decode"] = decode
    if polls is not None:
        cfg["polls"] = polls
    d = {
        "name": "lora_temp_001",
        "protocol": "lora",
        "lora": cfg,
        "points": points or [{"property": "temperature", "payloadKey": "temperature", "scale": 1.0}],
    }
    r = BM.LoraReader(d)
    r._cli = FakeCli()
    r._conn.set()          # 模拟 MQTT 已连接；"未连接"场景见 test_downlink_waits_* 用例
    return r


def feed(r, dev_eui, values, topic=""):
    """模拟 ChirpStack 上行报文到达。"""
    payload = dict(values)
    payload["devEUI"] = dev_eui
    msg = types.SimpleNamespace(topic=topic or "application/1/device/%s/event/up" % dev_eui,
                                payload=json.dumps(payload).encode())
    r._on_message(None, None, msg)


# --------------------------------------------------------------------------
# 用例
# --------------------------------------------------------------------------
def test_default_down_topic():
    r = make_reader(downlink={"enabled": True})
    assert r._down_topic("aabb") == "application/1/device/aabb/command/down", r._down_topic("aabb")


def test_custom_down_topic():
    r = make_reader(downlink={"enabled": True, "topic": "lorawan/{appID}/{devEUI}/down"})
    assert r._down_topic("aabb") == "lorawan/1/aabb/down"


def test_down_payload_hex_to_base64():
    r = make_reader(downlink={"enabled": True, "fPort": 2, "hex": "0102ff"})
    p = r._down_payload("aabb")
    assert p["devEui"] == "aabb"
    assert p["fPort"] == 2
    assert p["confirmed"] is False
    assert base64.b64decode(p["data"]) == b"\x01\x02\xff"


def test_down_payload_text():
    r = make_reader(downlink={"enabled": True, "payload": "READ"})
    assert base64.b64decode(r._down_payload("aabb")["data"]) == b"READ"


def test_down_payload_object_v4_codec():
    """v4 codec 场景：下发解码对象（object），不带 data。"""
    r = make_reader(downlink={"enabled": True, "object": {"cmd": "read"}})
    p = r._down_payload("aabb")
    assert p == {"devEui": "aabb", "confirmed": False, "fPort": 1, "object": {"cmd": "read"}}


def test_down_payload_empty_by_default():
    r = make_reader(downlink={"enabled": True})
    assert base64.b64decode(r._down_payload("aabb")["data"]) == b""


def test_send_downlink_publishes():
    r = make_reader(downlink={"enabled": True, "hex": "01"})
    assert r.send_downlink() is True
    topic, payload, qos = r._cli.published[0]
    assert topic == "application/1/device/0011223344556677/command/down"
    assert payload["devEui"] == "0011223344556677"


def test_downlink_waits_for_mqtt_connected():
    """回归：连接还没就绪时不丢帧 —— 就绪后本拍仍能把问帧发出去。

    旧实现在 connect_async 完成后立刻 publish，qos=0 只入队不发出（rc=NO_CONN），
    每次重启都会白丢第一拍问帧并刷一条"下行发布失败"的误导性告警。
    """
    r = make_reader(downlink={"enabled": True, "hex": "070300000001846c"})
    r._conn.clear()
    t = threading.Timer(0.3, r._conn.set)
    t.start()
    try:
        assert r.send_downlink() is True
    finally:
        t.join()
    assert len(r._cli.published) == 1


def test_downlink_skips_when_connection_never_ready():
    """连接始终不上来：明确说"通道未就绪"，不产生"看着发出去了"的假成功。"""
    r = make_reader(downlink={"enabled": True, "hex": "01"})
    r._conn.clear()
    assert r.send_downlink() is False
    assert r._cli.published == []


def test_send_downlink_without_eui_known():
    r = make_reader(downlink={"enabled": True}, dev_eui="")
    assert r.send_downlink() is False
    assert r._cli.published == []


def test_send_downlink_uses_cached_eui_when_wildcard():
    r = make_reader(downlink={"enabled": True}, dev_eui="")
    feed(r, "aabbccdd", {"temperature": 21.5})
    assert r.send_downlink() is True
    assert r._cli.published[0][0] == "application/1/device/aabbccdd/command/down"


def test_poll_once_success():
    """下发后终端在 0.3s 回传 -> 取数成功。"""
    r = make_reader(downlink={"enabled": True, "timeout": 3.0})
    feed(r, "0011223344556677", {"temperature": 20.0})   # 旧值

    def uplink_later():
        time.sleep(0.3)
        feed(r, "0011223344556677", {"temperature": 26.4})

    threading.Thread(target=uplink_later, daemon=True).start()
    t0 = time.time()
    assert r.poll_once() is True
    assert time.time() - t0 < 3.0
    # read_all 每拍都会重新下发，这里关掉下行直接验证已回传的缓存值
    r.dl_enabled = False
    assert r.read_all()["temperature"] == 26.4


def test_poll_once_timeout_returns_empty():
    """终端不应答 -> poll 超时，read_all 返回空（不重复上报旧值）。"""
    r = make_reader(downlink={"enabled": True, "timeout": 0.5})
    feed(r, "0011223344556677", {"temperature": 20.0})
    assert r.poll_once() is False
    assert r.read_all() == {}


def test_read_all_returns_empty_when_downlink_disabled_channel():
    """无 devEUI 且无缓存：无通道可下发，本拍跳过。"""
    r = make_reader(downlink={"enabled": True, "timeout": 0.3}, dev_eui="")
    assert r.read_all() == {}


def test_passive_mode_unchanged():
    """downlink 未启用时保持原被动语义：直接返回缓存的最新值。"""
    r = make_reader(downlink=None)
    feed(r, "0011223344556677", {"temperature": 19.1})
    assert r.read_all() == {"temperature": 19.1}
    assert r._cli.published == []


def test_rest_channel():
    """配置 rest.url 时走 REST 入队，不再发 MQTT。"""
    calls = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        calls["url"] = req.full_url
        calls["body"] = json.loads(req.data.decode())
        calls["auth"] = req.get_header("Authorization")
        return FakeResp()

    import urllib.request
    old = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        r = make_reader(downlink={
            "enabled": True,
            "hex": "0A",
            "rest": {"url": "http://127.0.0.1:8080/api/devices/{devEUI}/queue", "token": "T"},
        })
        assert r.send_downlink() is True
    finally:
        urllib.request.urlopen = old
    assert calls["url"] == "http://127.0.0.1:8080/api/devices/0011223344556677/queue"
    assert calls["auth"] == "Bearer T"
    assert calls["body"]["queueItem"]["data"] == base64.b64encode(b"\x0a").decode()
    assert r._cli.published == []


def feed_raw(r, dev_eui, raw, topic=""):
    """模拟 ChirpStack 未配 codec 的上行：顶层只给 base64 的 data 原始帧。"""
    payload = {
        "applicationId": "1",
        "deviceName": "dr206",
        "devEUI": dev_eui,
        "fPort": 1,
        "data": base64.b64encode(raw).decode(),
    }
    msg = types.SimpleNamespace(
        topic=topic or "application/1/device/%s/event/up" % dev_eui,
        payload=json.dumps(payload).encode())
    r._on_message(None, None, msg)


def test_decode_modbus_rtu_frame():
    """Modbus RTU 应答 07 03 02 <reg16> crc crc -> 0.1 scale 温度。"""
    r = make_reader(decode={"type": "modbus-temp", "scale": 0.1})
    feed_raw(r, "0011223344556677", bytes.fromhex("07030200FA840C"))   # 0x00FA=250
    assert r.read_all() == {"temperature": 25.0}


def test_decode_two_bytes_trimmed():
    """DTU 已剥帧头：仅温度字 2 字节。"""
    r = make_reader(decode={"type": "modbus-temp", "scale": 0.1})
    feed_raw(r, "0011223344556677", bytes.fromhex("00FB"))             # 0x00FB=251
    assert r.read_all() == {"temperature": 25.1}


def test_decode_negative_temp():
    """有符号：0xFFF6 = -10 -> -1.0。"""
    r = make_reader(decode={"type": "modbus-temp", "scale": 0.1})
    feed_raw(r, "0011223344556677", bytes.fromhex("FFF6"))
    assert r.read_all() == {"temperature": -1.0}


def test_decode_off_without_config():
    """未配 decode 保持原语义：原始帧拿不到 payloadKey -> 空值不上报。"""
    r = make_reader()
    feed_raw(r, "0011223344556677", bytes.fromhex("07030200FA840C"))
    assert r.read_all() == {}


def test_decode_object_still_priority():
    """NS 配了 codec 且带 object 时仍走 payloadKey，不被原始帧解码覆盖。"""
    r = make_reader(decode={"type": "modbus-temp", "scale": 0.1})
    r._on_message(None, None, types.SimpleNamespace(
        topic="application/1/device/0011223344556677/event/up",
        payload=json.dumps({
            "devEUI": "0011223344556677",
            "object": {"temperature": 26.4},
            "data": base64.b64encode(bytes.fromhex("00FA")).decode(),
        }).encode()))
    assert r.read_all() == {"temperature": 26.4}


def test_decode_generic_fields():
    """通用 fields 提取：跳过帧头取温度字。"""
    pts = [{"property": "temperature", "scale": 0.1}]
    r = make_reader(decode={
        "fields": [{"property": "temperature", "offset": 1, "width": 2,
                    "signed": True, "scale": 0.1}],
    }, points=pts)
    feed_raw(r, "0011223344556677", bytes.fromhex("FF00FB"))
    assert r.read_all() == {"temperature": 25.1}


def test_decode_generic_fields_out_of_range():
    r = make_reader(decode={
        "fields": [{"property": "temperature", "offset": 5, "width": 2, "signed": True}],
    }, points=[{"property": "temperature"}])
    feed_raw(r, "0011223344556677", bytes.fromhex("00FB"))
    assert r.read_all() == {}


# --------------------------------------------------------------------------
# 多从站：一台 DTU 挂多台 485 传感器（按从站号区分、分流到多台平台设备）
# --------------------------------------------------------------------------
class AutoReplyCli:
    """模拟透传 DTU：收到问帧后按问的从站号回一帧 Modbus 应答。

    silent 里的从站不回（模拟该站掉线/不存在），用于验证"一台不应答不拖累别台"。
    trimmed 里的从站回裸数据段（帧头被 DTU 剥掉），用于验证兜底归位。
    """

    def __init__(self, reader, delay=0.05, silent=(), trimmed=()):
        self.reader = reader
        self.delay = delay
        self.silent = set(silent)
        self.trimmed = set(trimmed)
        self.published = []

    def publish(self, topic, payload, qos=0):
        p = json.loads(payload)
        self.published.append((topic, p, qos))
        slave = base64.b64decode(p["data"])[0]
        threading.Thread(target=self._reply, args=(slave,), daemon=True).start()
        return FakeInfo()

    def _reply(self, slave):
        time.sleep(self.delay)
        if slave in self.silent:
            return
        val = {2: 250, 3: 600}.get(slave, 0)          # 站2 -> 25.0℃，站3 -> 60.0%
        body = bytes([slave, 3, 2, (val >> 8) & 0xFF, val & 0xFF])
        crc = BM._mb_crc16(body)
        raw = body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        if slave in self.trimmed:
            raw = raw[3:-2]                            # 只留数据段
        msg = types.SimpleNamespace(
            topic="application/1/device/0011223344556677/event/up",
            payload=json.dumps({
                "devEUI": "0011223344556677",
                "data": base64.b64encode(raw).decode(),
            }).encode())
        self.reader._on_message(None, None, msg)


def make_multi_reader(polls, **kw):
    kw.setdefault("downlink", {"enabled": True, "mode": "poll", "timeout": 3.0})
    return make_reader(polls=polls, **kw)


TWO_SLAVES = [
    {"slave": 2, "device": "temp_rs50", "registerAddr": 0, "count": 1,
     "points": [{"property": "temperature", "type": "int16", "scale": 0.1}]},
    {"slave": 3, "device": "humidity_rs50", "registerAddr": 0, "count": 1,
     "points": [{"property": "humidity", "type": "uint16", "scale": 0.1}]},
]


def test_build_modbus_read_frame_crc():
    """自动拼帧的 CRC 必须与手工核对的已知帧一致（含 DR206 模板帧）。"""
    assert BM._build_modbus_read_frame(7, 0, 1, 3) == "070300000001846c"
    assert BM._build_modbus_read_frame(2, 0, 1, 3) == "0203000000018439"
    assert BM._build_modbus_read_frame(3, 0, 2, 3) == "030300000002c5e9"
    assert BM._build_modbus_read_frame(2, 0, 1, 4) == "02040000000131f9"


def test_polls_parsed_and_frame_autobuilt():
    """polls 只给站号/地址/数量时自动补 hex（省掉手算 CRC 这个头号错源）。"""
    r = make_multi_reader(TWO_SLAVES)
    assert [p["slave"] for p in r.polls] == [2, 3]
    assert r.polls[0]["hex"] == "0203000000018439"
    assert r.polls[0]["device"] == "temp_rs50"
    assert r.polls[1]["hex"] == "03030000000185e8"


def test_polls_explicit_hex_wins():
    r = make_multi_reader([{"slave": 3, "device": "h", "hex": "03 03 00 00 00 01 85 E8",
                            "points": []}])
    assert r.polls[0]["hex"] == "03030000000185e8"   # 空格被清掉


def test_polls_bad_hex_skipped():
    r = make_multi_reader([{"slave": 2, "device": "x", "hex": "0G01", "points": []},
                           {"slave": 3, "device": "y", "hex": "03030000000185e8", "points": []}])
    assert [p["slave"] for p in r.polls] == [3]


def test_polls_missing_slave_skipped():
    r = make_multi_reader([{"device": "x", "hex": "03030000000185e8", "points": []}])
    assert r.polls == []


def test_polls_multi_slave_routed():
    """核心：两个从站各回各的，按站号归位并分流到两台平台设备。"""
    r = make_multi_reader(TWO_SLAVES)
    r._cli = AutoReplyCli(r)
    assert r.read_all() == {"temperature": 25.0, "humidity": 60.0}
    assert r.routed == {"temp_rs50": {"temperature": 25.0},
                        "humidity_rs50": {"humidity": 60.0}}
    # 每站各下发一次，且带的是自己的问帧
    assert [base64.b64decode(p["data"])[0] for _, p, _ in r._cli.published] == [2, 3]


def test_polls_per_slave_points_and_types():
    """各从站的点位/类型独立：站2 有符号 int16，站3 无符号 uint16 + 不同 scale。"""
    r = make_multi_reader([
        {"slave": 2, "device": "d2", "registerAddr": 0, "count": 1,
         "points": [{"property": "t", "type": "int16", "scale": 0.1}]},
        {"slave": 3, "device": "d3", "registerAddr": 0, "count": 1,
         "points": [{"property": "h", "type": "uint16", "scale": 1.0}]},
    ])
    r._cli = AutoReplyCli(r)
    r.read_all()
    assert r.routed == {"d2": {"t": 25.0}, "d3": {"h": 600.0}}


def test_polls_one_slave_silent_does_not_block_others():
    """站3 不应答：站2 的值照常取到并上报，只 warn 不失败整拍。"""
    r = make_multi_reader(TWO_SLAVES)
    r._cli = AutoReplyCli(r, silent={3})
    assert r.read_all() == {"temperature": 25.0}
    assert r.routed == {"temp_rs50": {"temperature": 25.0}}


def test_polls_all_silent_returns_empty():
    """全部从站无应答：返回空，采集线程会跳过本拍（不重复上报旧值）。"""
    r = make_multi_reader(TWO_SLAVES)
    r._cli = AutoReplyCli(r, silent={2, 3})
    assert r.read_all() == {}
    assert r.routed == {}


def test_polls_trimmed_frame_falls_back_to_pending_slave():
    """DTU 剥掉 Modbus 帧头只给数据段：回落到"本拍正在等的那台"，照样归位。"""
    r = make_multi_reader(TWO_SLAVES)
    r._cli = AutoReplyCli(r, trimmed={2, 3})
    assert r.read_all() == {"temperature": 25.0, "humidity": 60.0}


def test_polls_device_defaults_to_own_name():
    """polls 不配 device 时归到本设备名下（等价单设备，向后兼容）。"""
    r = make_multi_reader([{"slave": 2, "registerAddr": 0, "count": 1,
                            "points": [{"property": "temperature", "scale": 0.1}]}])
    r._cli = AutoReplyCli(r)
    r.read_all()
    assert r.routed == {"lora_temp_001": {"temperature": 25.0}}


def test_polls_no_downlink_channel_returns_empty():
    """没配 devEUI 又没收到过上行：无从下发，本拍返回空而不是瞎发。"""
    r = make_multi_reader(TWO_SLAVES, dev_eui="")
    r._cli = FakeCli()
    assert r.read_all() == {}
    assert r._cli.published == []


def test_polls_snapshot_values_merges():
    r = make_multi_reader(TWO_SLAVES)
    r._cli = AutoReplyCli(r)
    r.read_all()
    assert r.snapshot_values() == {"temperature": 25.0, "humidity": 60.0}


def test_single_slave_mode_unaffected_by_polls_code():
    """未配 polls 时完全走老路径（被动语义 + decode 解码）。"""
    r = make_reader(decode={"type": "modbus-temp", "scale": 0.1})
    assert r.polls == []
    feed_raw(r, "0011223344556677", bytes.fromhex("07030200FA840C"))
    assert r.read_all() == {"temperature": 25.0}


def test_decode_modbus_reply_generic_points():
    """通用应答解码：帧头剥离 + regIndex 指定寄存器下标。"""
    raw = bytes.fromhex("02030400640102" + "0000")    # 站2 03 04B [0064 0102] CRC
    vals = BM._decode_modbus_reply(raw, [
        {"property": "a", "scale": 0.1},
        {"property": "b", "type": "uint16", "regIndex": 1},
    ])
    assert vals == {"a": 10.0, "b": 258}


def test_decode_modbus_reply_trimmed_payload():
    """帧头已剥（裸数据段）：直接按点位顺序取寄存器。"""
    vals = BM._decode_modbus_reply(bytes.fromhex("00fa"), [
        {"property": "t", "type": "int16", "scale": 0.1},
    ])
    assert vals == {"t": 25.0}


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (t.__name__, e))
        except Exception as e:
            failed += 1
            print("ERR  %s: %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
