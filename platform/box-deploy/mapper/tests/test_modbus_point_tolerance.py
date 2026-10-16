#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modbus-RTU 逐点容错 + 平台「读寄存器」功能码取值单元测试。

背景：同一条 485 总线上多台设备时偶发丢帧（"响应太短"）。此前 read_all 只要
有一个点位读失败就抛异常，整台设备本拍数据全部丢弃 —— 表现为设备 DMI 仍注册
（平台显示在线）但读数长期停在旧值。现在改为：单点失败跳过、其余点位照常上报，
只有全部点位都失败才抛异常交给上层重连退避。

另覆盖 read_device_regs 按点位读取时的 fc 取值：必须用点位自身 fc（输入寄存器
点位 fc=4 回退成默认 3 会去读保持寄存器，读到的值与采集值完全对不上）。

运行：python3 -m pytest platform/box-deploy/mapper/tests -q
"""
import os
import sys
import types
import struct
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
MAPPER = os.path.join(os.path.dirname(HERE), "box_mapper.py")


class _AutoModule(types.ModuleType):
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
    spec = importlib.util.spec_from_file_location("box_mapper_tolerance_under_test", MAPPER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BM = load_mapper()

POINTS = [
    {"property": "voltage", "registerAddr": 0, "registerCount": 1,
     "type": "int16", "fc": 4, "scale": 0.01},
    {"property": "current", "registerAddr": 1, "registerCount": 1,
     "type": "int16", "fc": 4, "scale": 0.01},
    {"property": "power", "registerAddr": 3, "registerCount": 1,
     "type": "int16", "fc": 4, "scale": 0.01},
]


def make_reader(points=None):
    d = {
        "name": "power_supply_24v",
        "protocol": "modbus-rtu",
        "serial": {"port": "/dev/ttyFAKE485", "baudrate": 9600},
        "modbus": {"slaveId": 1},
        "points": points or POINTS,
    }
    r = BM.ModbusRtuReader(d)
    r.ser = object()          # 跳过真实串口 connect
    return r


def _regs(value, cnt):
    """把整数寄存器值编成 mapper 期望的原始字节（大端）。"""
    return struct.pack(">%dH" % max(1, cnt), *([value] * max(1, cnt)))


def patch_io(values):
    """values: {addr: int | None}；None 表示该地址读取失败（丢帧）。"""
    orig_shared, orig_read = BM._shared_serial, BM.modbus_read_regs_rtu
    BM._shared_serial = lambda port, cfg: object()

    def fake_read(ser, slave, addr, cnt, fc):
        value = values.get(addr, 0)
        if value is None:
            raise IOError("响应太短: 6/7 bytes")
        return _regs(value, cnt)

    BM.modbus_read_regs_rtu = fake_read
    return orig_shared, orig_read


def restore_io(saved):
    BM._shared_serial, BM.modbus_read_regs_rtu = saved


def test_single_failed_point_does_not_drop_device():
    """addr 1 丢帧时，电压/功率仍要上报（此前整台设备本拍数据会被丢弃）。"""
    saved = patch_io({0: 100, 1: None, 3: 250})
    try:
        r = make_reader()
        res = r.read_all()
    finally:
        restore_io(saved)
    assert res == {"voltage": 1.0, "power": 2.5}, res


def test_all_points_failed_raises_for_reconnect():
    """全部点位失败说明设备真的掉线，仍要抛异常让上层重连退避。"""
    saved = patch_io({0: None, 1: None, 3: None})
    try:
        r = make_reader()
        try:
            r.read_all()
        except IOError as e:
            assert "全部点位读取失败" in str(e), str(e)
        else:
            raise AssertionError("全部点位失败时应抛 IOError")
    finally:
        restore_io(saved)


def test_point_fc_defaults_to_holding_register():
    """未配置 fc 的点位默认走 0x03（保持寄存器），避免误读输入寄存器。"""
    seen = []

    def fake_read(ser, slave, addr, cnt, fc):
        seen.append(fc)
        return _regs(7, cnt)

    saved = (BM._shared_serial, BM.modbus_read_regs_rtu)
    BM._shared_serial = lambda port, cfg: object()
    BM.modbus_read_regs_rtu = fake_read
    try:
        r = make_reader([{"property": "v", "registerAddr": 0, "registerCount": 1,
                          "type": "int16", "scale": 1.0}])
        assert r.read_all() == {"v": 7.0}
    finally:
        restore_io(saved)
    assert seen == [3], seen


def test_decode_regs_short_data_returns_none():
    """响应被截断（字节数不足）应返回 None，而不是抛 struct.error 让整台设备作废。"""
    assert BM.decode_regs(b"\x00", "int16") is None
    assert BM.decode_regs(b"\x00\x01", "int32") is None
    assert BM.decode_regs(b"\x00\x01", "float32") is None
    assert BM.decode_regs(b"\x00\x01\x02", "int64") is None


def test_decode_regs_ambiguous_int_uses_register_count():
    """'int' 字长按实际字节数推断：1 个寄存器=16 位，2 个=32 位。"""
    assert BM.decode_regs(struct.pack(">H", 41), "int") == 41
    assert BM.decode_regs(struct.pack(">I", 123456), "int") == 123456
    assert BM.decode_regs(struct.pack(">H", 65535), "uint") == 65535


def test_decode_error_drops_only_that_point():
    """点位类型配置错误（解码抛异常）时，其余点位仍要照常上报。"""
    saved = patch_io({0: 100, 1: 100, 3: 250})
    try:
        points = [dict(POINTS[0], type="int16"),
                  dict(POINTS[1], type="not-a-type"),
                  dict(POINTS[2], type="int16")]
        r = make_reader(points)
        res = r.read_all()
    finally:
        restore_io(saved)
    assert res == {"voltage": 1.0, "power": 2.5}, res


# --------------------------------------------------------------------------
# 平台「读寄存器」按点位读取时的功能码取值（read_device_regs）
# --------------------------------------------------------------------------
def patch_read(points=None, raw=b"\x00\x05", dev_fc=None):
    """打桩 read_device_regs 依赖：设备配置 + 串口 + 底层读寄存器（记录 addr/fc）。"""
    dev = {"name": "power_supply_24v", "protocol": "modbus-rtu",
           "serial": {"port": "/dev/ttyFAKE485"}, "modbus": {"slaveId": 1},
           "points": points if points is not None else POINTS}
    if dev_fc is not None:
        dev["modbus"]["fc"] = dev_fc
    seen = []
    saved = (BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu)
    BM._find_device_cfg = lambda name: dev if name == "power_supply_24v" else None
    BM._shared_serial = lambda port, cfg: object()

    def fake_read(ser, slave, addr, cnt, fc):
        seen.append((addr, fc))
        return raw

    BM.modbus_read_regs_rtu = fake_read
    return seen, saved


def test_read_cmd_by_property_uses_point_fc():
    """按点位读取必须走点位自己的 fc：输入寄存器点位(fc=4)回退成 3 会读错寄存器区。

    实测 shuibeng-power：fc3 读回 0x0000(0.00V)/0x2710(100.00W)，而采集用的
    输入寄存器是 0x0005(0.05V)/0x0000(0.00W) —— 调试面板会给出与采集不一致的读数。
    """
    seen, saved = patch_read()
    try:
        ok, msg, detail = BM.read_device_regs("power_supply_24v", property_="voltage")
    finally:
        BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu = saved
    assert ok, msg
    assert seen == [(0, 4)], seen
    assert detail["fc"] == 4, detail
    assert detail["raw"] == ["0x0005"], detail
    assert detail["value"] == 0.05, detail


def test_read_cmd_point_fc_beats_explicit_and_device_fc():
    """点位自带 fc 时，优先于命令显式入参和设备级 modbus.fc（避免被误传的 3 带偏）。"""
    seen, saved = patch_read(dev_fc=3)
    try:
        ok, msg, detail = BM.read_device_regs("power_supply_24v", property_="power", fc=3)
    finally:
        BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu = saved
    assert ok, msg
    assert seen == [(3, 4)], seen
    assert detail["fc"] == 4, detail


def test_read_cmd_point_without_fc_falls_back():
    """点位未标 fc 时：先显式入参，再设备级 fc，最后默认 3（保持原行为）。"""
    no_fc = [{"property": "v", "registerAddr": 0, "registerCount": 1,
              "type": "int16", "scale": 1.0}]
    seen, saved = patch_read(points=no_fc)
    try:
        BM.read_device_regs("power_supply_24v", property_="v", fc=4)
    finally:
        BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu = saved
    assert seen == [(0, 4)], seen

    seen, saved = patch_read(points=no_fc, dev_fc=4)
    try:
        BM.read_device_regs("power_supply_24v", property_="v")
    finally:
        BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu = saved
    assert seen == [(0, 4)], seen

    seen, saved = patch_read(points=no_fc)
    try:
        BM.read_device_regs("power_supply_24v", property_="v")
    finally:
        BM._find_device_cfg, BM._shared_serial, BM.modbus_read_regs_rtu = saved
    assert seen == [(0, 3)], seen

