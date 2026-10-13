#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LoRa 下行链路观测与退避（不依赖真实终端 / NS）：

背景（2026-10-13 现场故障）：DR206 这类透传终端不会自发上行，读数完全靠
mapper 下发问帧驱动；而 ChirpStack 只在"近期收到过该终端上行"时才肯下发下行
（rx history 为空时直接拒绝：gateway rx history is empty after filtering,
no downlink path available）。于是下行一断就是死结：下行发不出 → 终端不回 →
永远没有上行 → 永远发不出。mapper 自救不了，但必须做到两件事：
  1. 看得清：区分「ChirpStack 没下发（需现场起搏终端）」与「下发到网关了但终端
     不答（射频/485/从站问题）」，这两类处置完全不同；
  2. 别添乱：确认无下行路径后退避轮询周期、不再同拍补发，避免无效问帧把
     ChirpStack 下行队列堆爆（现场实测 19 分钟堆到 150+ 条）。

覆盖：
  1. 网关下行帧（ChirpStack → 网关）按 DevAddr 归属，别的终端不计入；
  2. 从上行事件学会本终端 DevAddr；
  3. 无网关下行帧 → 归为"无下行路径"，计数递增、日志点名需现场起搏；
  4. 有网关下行帧但仍无应答 → 归为"空口/终端侧"，不累加无下行计数；
  5. 连续无下行 → 退避升级（周期放大、取消同拍补发）；
  6. 拿到应答 → 退避立即归零、周期回到正常；
  7. 非 LoRa 采集线程不受影响（_cycle_interval 原样返回）。

运行：cd platform/box-deploy/mapper && python3 -m pytest test_lora_downlink.py -v
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import types

import pytest


# ---------------------------------------------------------------------------
# box_mapper 导入前置桩：grpc / api_pb2 等盒子专有依赖在开发机上不存在
# ---------------------------------------------------------------------------
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


if "box_mapper" not in sys.modules:
    _stub("grpc", server=lambda *a, **k: None,
          insecure_channel=lambda *a, **k: None,
          RpcError=type("RpcError", (Exception,), {}))
    _stub("api_pb2")
    _stub("api_pb2_grpc",
          DeviceMapperServiceServicer=object,
          add_DeviceMapperServiceServicer_to_server=lambda *a, **k: None,
          DeviceManagerServiceStub=lambda *a, **k: None)
    _stub("google")
    _stub("google.protobuf")
    _stub("google.protobuf.any_pb2", Any=type("Any", (), {}))
    _stub("google.protobuf.wrappers_pb2",
          **{n: type(n, (), {}) for n in (
              "StringValue", "Int32Value", "Int64Value", "FloatValue",
              "DoubleValue", "BoolValue", "BytesValue")})
    _fd, _cfg = tempfile.mkstemp(suffix=".json")
    os.write(_fd, json.dumps({
        "devices": [{"name": "env-temp", "protocol": "lora", "interval": 30.0}],
        "mqtt": {"enabled": False},
    }).encode())
    os.close(_fd)
    os.environ["CONFIG_PATH"] = _cfg
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import box_mapper as bm  # noqa: E402


DEV_ADDR = "01234567"          # 本终端 DevAddr（平台侧写法）
OTHER_ADDR = "89abcdef"        # 同一 NS 上另一台终端


def _gw_frame(dev_addr_hex):
    """构造一帧 ChirpStack → 网关的 command/down（DevAddr 在空中是小端）。"""
    head = bytes.fromhex(dev_addr_hex)[::-1]
    phy = base64.b64encode(head + b"\x00\x0a\x01\x02").decode()
    return json.dumps({"phyPayload": phy, "txInfo": {"frequency": 505300000}}).encode()


def _mk_reader(monkeypatch, gw_emits=True, answer=True, no_down_max=2):
    """一台 LoraReader：单从站，可脚本化「ChirpStack 是否下发 / 终端是否应答」。"""
    r = bm.LoraReader({
        "name": "env-temp",
        "interval": 30.0,
        "lora": {
            "devEUI": "0120560100000264",
            "applicationID": "app-1",
            "noDownMax": no_down_max,
            "polls": [{"slave": 1, "device": "env-temp", "hex": "010300000001840a"}],
            "downlink": {"enabled": True, "fPort": 10, "timeout": 0.05},
        },
        "points": [{"property": "temperature", "type": "int16", "scale": 0.1}],
    })
    calls = {"down": 0}

    def _send(eui=None, hex_data=None, fport=None):
        calls["down"] += 1
        if gw_emits:
            r._note_gateway_downlink(_gw_frame(DEV_ADDR))
        return True

    monkeypatch.setattr(r, "send_downlink", _send)
    monkeypatch.setattr(r, "_wait_slave", lambda slave, before: answer)
    r._calls = calls
    return r


# -- 1/2：网关下行帧归属 ----------------------------------------------------
def test_gateway_downlink_attributed_by_dev_addr():
    r = bm.LoraReader({
        "name": "env-temp", "interval": 30.0,
        "lora": {"devEUI": "0120560100000264", "applicationID": "app-1"},
    })
    r.dev_addr = DEV_ADDR
    r._note_gateway_downlink(_gw_frame(OTHER_ADDR))   # 别的终端的下行帧
    assert r._gw_down_count == 0
    r._note_gateway_downlink(_gw_frame(DEV_ADDR))     # 本终端的
    assert r._gw_down_count == 1
    assert r._gw_down_ts > 0


def test_dev_addr_learned_from_uplink_event():
    r = bm.LoraReader({"name": "env-temp", "lora": {"devEUI": "0120560100000264"}})
    assert r.dev_addr == ""
    r._note_dev_addr({"deviceInfo": {"devEui": "0120560100000264", "devAddr": DEV_ADDR}})
    assert r.dev_addr == DEV_ADDR
    # 已学会后不再被别的帧改写
    r._note_dev_addr({"devAddr": OTHER_ADDR})
    assert r.dev_addr == DEV_ADDR


# -- 3/4：两类无应答的区分 --------------------------------------------------
def test_no_gateway_downlink_counts_as_no_downlink_path(monkeypatch, capsys):
    r = _mk_reader(monkeypatch, gw_emits=False, answer=False)
    r._read_polls()
    assert r._no_down_streak == 1
    out = capsys.readouterr().out
    assert "ChirpStack 未向网关下发下行帧" in out
    assert "无下行路径" in out


def test_gateway_downlink_without_answer_is_terminal_side(monkeypatch, capsys):
    r = _mk_reader(monkeypatch, gw_emits=True, answer=False)
    r._read_polls()
    assert r._no_down_streak == 0          # 帧已到网关 → 不是"无下行路径"
    out = capsys.readouterr().out
    assert "网关已收到下行" in out
    assert "无下行路径" not in out


# -- 5：退避升级并取消同拍补发 ----------------------------------------------
def test_backoff_escalates_and_skips_retry(monkeypatch, capsys):
    r = _mk_reader(monkeypatch, gw_emits=False, answer=False)
    assert r.cycle_interval() == 30.0
    r._read_polls()                       # 第 1 拍：计数 1，未达 noDownMax，会补发
    assert r._backoff == 0
    assert r._calls["down"] == 2
    r._calls["down"] = 0
    r._read_polls()                       # 第 2 拍：达到阈值 → 退避升到第 1 档
    assert r._backoff == 1
    assert r.cycle_interval() == 60.0
    r._calls["down"] = 0
    r._read_polls()                       # 第 3 拍：退避生效 → 不再同拍补发
    assert r._calls["down"] == 1
    out = capsys.readouterr().out
    assert "轮询周期退避至" in out


def test_backoff_caps_at_last_multiplier(monkeypatch):
    r = _mk_reader(monkeypatch, gw_emits=False, answer=False)
    for _ in range(12):
        r._read_polls()
    assert r._backoff == len(r._backoff_mults) - 1
    assert r.cycle_interval() == 30.0 * r._backoff_mults[-1]


# -- 6：恢复即收敛 ----------------------------------------------------------
def test_backoff_resets_when_data_returns(monkeypatch, capsys):
    r = _mk_reader(monkeypatch, gw_emits=False, answer=False)
    r._read_polls()
    r._read_polls()
    assert r._backoff == 1

    # 终端恢复应答：注入一帧有效应答后再跑一拍
    r._by_slave[1] = {"ts": 0.0, "values": {"temperature": 26.0}}
    monkeypatch.setattr(r, "_wait_slave", lambda slave, before: True)
    r._read_polls()
    assert r._backoff == 0
    assert r._no_down_streak == 0
    assert r.cycle_interval() == 30.0
    assert "下行链路恢复" in capsys.readouterr().out


# -- 7：非 LoRa 设备不受影响 ------------------------------------------------
def test_cycle_interval_passthrough_for_other_protocols():
    class _Plain:
        pass

    assert bm._cycle_interval(_Plain(), 2.0) == 2.0
    assert bm._cycle_interval(None, 5.0) == 5.0
