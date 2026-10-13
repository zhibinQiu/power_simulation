#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CameraReader 模拟验证（不依赖真实摄像头硬件）：

用 pty 虚拟串口对模拟智景 SVL130w（A 版协议 U/# 帧，固件 XY-Y-01）：
  - 应答 H（拍图）→ UH# + R 帧（图片大小/包数）；
  - 应答 E（取包）→ UE# + F 帧（合成 FFD8...FFD9 假 JPEG 切片，带累加和校验）；
  - 可注入丢包（E 不应答）、校验错、应答延迟。

覆盖：
  1. A 版组帧/解帧与 camera_capture.py selftest 抓包用例逐字节一致；
  2. 完整抓拍流程：H/R/E/F 取包序列、meta/fragment 分片发布序列与内容、
     分片数据拼接 == 合成 JPEG；
  3. size>=2 拒绝（不发任何串口字节）；拍图间隔 <15s 拒绝；
  4. 单包超时重试、连续失败静置后断点续取；F 帧校验失败计数；
  5. 整事务持锁（抓拍期间外部拿不到同一把 _port_lock）；
  6. resend 免重拍补发：imageId 匹配才重取重发，不匹配拒绝。

运行：cd platform/box-deploy/mapper && python3 -m pytest test_camera_reader.py -v
"""
from __future__ import annotations

import json
import os
import pty
import select
import struct
import sys
import tempfile
import threading
import time
import types

import pytest

# ---------------------------------------------------------------------------
# box_mapper 导入前置桩：grpc / api_pb2 / paho 等盒子专有依赖在开发机上不存在
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
        "devices": [{"name": "cam1", "protocol": "camera",
                     "serial": {"port": "/dev/null"}, "camera": {"camId": 1}}],
        "mqtt": {"enabled": False},
    }).encode())
    os.close(_fd)
    os.environ["CONFIG_PATH"] = _cfg
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import box_mapper as bm  # noqa: E402

AU_HEAD, AU_TAIL = 0x55, 0x23


# ---------------------------------------------------------------------------
# pty 虚拟串口上的模拟摄像头
# ---------------------------------------------------------------------------
class SimCamera(threading.Thread):
    """模拟 SVL130w：H -> UH# + R 帧；E -> UE# + F 帧（JPEG 切片）；K -> UK#（在线探测）。"""

    def __init__(self, master_fd, cam_id=1, jpeg=b"", packet=512):
        super().__init__(daemon=True)
        self.fd = master_fd
        self.cam_id = cam_id
        self.jpeg = jpeg
        self.packet = packet
        self.e_delay = 0.0          # 每包应答前延迟（拖长事务，验证持锁）
        self.drop_e = {}            # {包号: 丢弃次数}——E 命令不应答
        self.drop_k = False         # True 时 K 探测不应答（模拟摄像头掉线/被拔）
        self.corrupt = set()        # 校验和注错的包号
        self.h_seen = threading.Event()
        self.k_seen = []            # K 探测收到的灯状态字节（验证「设为原状态」）
        self.e_seen = []
        self._stopped = False      # 不能叫 _stop：会遮蔽 threading.Thread._stop() 方法

    def stop(self):
        self._stopped = True

    def _pop_frame(self, buf):
        if len(buf) < 4 or buf[0] != AU_HEAD:
            if buf:
                del buf[:1]
            return None
        cmd = buf[1]
        ln = 7 if cmd == ord("H") else 6 if cmd == ord("E") else 5 if cmd == ord("K") else 4
        if len(buf) < ln:
            return None
        fr = bytes(buf[:ln])
        del buf[:ln]
        return fr

    def run(self):
        buf = bytearray()
        while not self._stopped:
            try:
                r, _, _ = select.select([self.fd], [], [], 0.02)
            except OSError:
                break                        # fd 已被夹具拆除关闭
            if r:
                try:
                    buf += os.read(self.fd, 4096)
                except OSError:
                    break
            while True:
                fr = self._pop_frame(buf)
                if fr is None:
                    break
                self._handle(fr)

    def _handle(self, fr):
        cmd, cid = fr[1], fr[2]
        if cid != self.cam_id:
            return
        if cmd == ord("K"):
            # K 补光灯探测：记录灯状态字节并应答 UK#；drop_k 时静默（模拟掉线）
            self.k_seen.append(fr[3])
            if self.drop_k:
                return
            os.write(self.fd, bytes([AU_HEAD, ord("K"), cid, AU_TAIL]))
        elif cmd == ord("H"):
            pkt = int.from_bytes(fr[4:6], "little")
            self.packet = pkt or self.packet
            self.h_seen.set()
            total = len(self.jpeg)
            packs = (total + self.packet - 1) // self.packet
            os.write(self.fd, bytes([AU_HEAD, ord("H"), cid, AU_TAIL]))
            rframe = bytes([AU_HEAD, ord("R"), cid]) + struct.pack("<I", total) \
                + struct.pack("<H", packs) + bytes([AU_TAIL])
            os.write(self.fd, rframe)
        elif cmd == ord("E"):
            no = int.from_bytes(fr[3:5], "little")
            self.e_seen.append(no)
            if self.drop_e.get(no, 0) > 0:
                self.drop_e[no] -= 1
                return                       # 丢包：不应答
            if self.e_delay:
                time.sleep(self.e_delay)
            data = self.jpeg[(no - 1) * self.packet: no * self.packet]
            os.write(self.fd, bytes([AU_HEAD, ord("E"), cid, AU_TAIL]))
            body = bytes([AU_HEAD, 0x46, cid]) + struct.pack("<H", no) \
                + struct.pack("<H", len(data)) + data
            chk = sum(body) & 0xFFFF
            if no in self.corrupt:
                chk ^= 0x00FF
            os.write(self.fd, body + struct.pack("<H", chk))


def make_jpeg(size=1300):
    body = bytes((i * 7 + 13) % 256 for i in range(size - 4))
    return b"\xff\xd8" + body + b"\xff\xd9"


@pytest.fixture
def cam_env(monkeypatch):
    """pty 对 + CameraReader + 发布 mock。yield (reader, sim, calls, master_fd)。"""
    calls = {"meta": [], "frag": []}
    monkeypatch.setattr(bm, "mqtt_publish_image_meta",
                        lambda dev, m: (calls["meta"].append(dict(m)) or True))
    monkeypatch.setattr(bm, "mqtt_publish_image_fragment",
                        lambda dev, f: (calls["frag"].append(dict(f)) or True))
    monkeypatch.setattr(bm, "_mqtt_connected", lambda: True)
    # 节流参数缩小到测试量级（纪律逻辑不变，只缩短 sleep）
    monkeypatch.setattr(bm, "CAM_CMD_GAP", 0.02)
    monkeypatch.setattr(bm, "CAM_PKT_GAP", 0.005)
    monkeypatch.setattr(bm, "CAM_PKT_REST_EVERY", 1000)
    monkeypatch.setattr(bm, "CAM_FATIGUE_REST", 0.05)
    monkeypatch.setattr(bm, "CAM_PKT_TIMEOUT", 0.4)
    monkeypatch.setattr(bm, "CAM_PROBE_LOCK_WAIT", 0.2)   # 锁忙用例不等满 5s
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)
    jpeg = make_jpeg()
    sim = SimCamera(master, cam_id=1, jpeg=jpeg, packet=512)
    sim.start()
    reader = bm.CameraReader({
        "name": "cam1",
        "serial": {"port": slave_name, "baudrate": 9600, "databits": 8,
                   "parity": "N", "stopbits": 1},
        "camera": {"camId": 1, "size": "1", "packet": 512},
    })
    reader.connect()
    yield reader, sim, calls, jpeg
    sim.stop()
    sim.join(timeout=2)                 # 先等模拟线程退出，再关 fd（避免 select 竞态告警）
    try:
        bm._reset_serial(slave_name)
    except Exception:
        pass
    os.close(master)
    os.close(slave)


# ---------------------------------------------------------------------------
# 1. 组帧/解帧与 camera_capture.py selftest 抓包用例一致
# ---------------------------------------------------------------------------
def test_frame_builders_match_capture_reference():
    # H 命令 = 说明书示例 55 48 01 32 00 02 23（size '2'、分包 512、ID=1）
    assert bm._au_frame("H", 1, b"2" + struct.pack("<H", 512)) == \
        bytes.fromhex("5548013200022 3".replace(" ", ""))
    # R 帧解析（18358B/36 包，来自实测抓包）
    rbuf = bytearray(bytes.fromhex("55 52 01 B6 47 00 00 24 00 23".replace(" ", "")))
    assert bm._au_pop_rframe(rbuf, 1) == (18358, 36) and not rbuf
    # F 帧解析 + 累加和校验
    body = bytes([AU_HEAD, 0x46, 1]) + struct.pack("<H", 3) + struct.pack("<H", 4) + b"ABCD"
    fbuf = bytearray(body + struct.pack("<H", sum(body) & 0xFFFF))
    no, data, ok = bm._au_pop_dataframe(fbuf, 1)
    assert no == 3 and data == b"ABCD" and ok and not fbuf
    # 错误应答帧
    ebuf = bytearray([AU_HEAD, 0x3F, 1, AU_TAIL])
    assert bm._au_pop_err(ebuf, 1) and not ebuf


def test_resync_keeps_partial_frame_head():
    # 头部是未到齐的合法 F 帧（55 46 <id> ...）时必须保留等齐，不能切头
    partial = bytearray([AU_HEAD, 0x46, 1, 0x01, 0x00])
    bm._au_resync(partial, 1)
    assert bytes(partial) == bytes([AU_HEAD, 0x46, 1, 0x01, 0x00])
    # 噪声在前、帧头在后：丢弃噪声
    noisy = bytearray(b"\x00\x11\x22" + bytes([AU_HEAD, 0x46, 1]))
    bm._au_resync(noisy, 1)
    assert bytes(noisy) == bytes([AU_HEAD, 0x46, 1])


# ---------------------------------------------------------------------------
# 2. 完整抓拍流程
# ---------------------------------------------------------------------------
def test_capture_flow_and_fragment_sequence(cam_env):
    reader, sim, calls, jpeg = cam_env
    packs = (len(jpeg) + 511) // 512
    res = reader.capture(size="1", trigger="manual", req_id="t1")
    assert res["ok"], res.get("message")
    assert res["totalPackets"] == packs and res["totalSize"] == len(jpeg)
    # 取包序列：E 1..packs 按序
    assert sim.e_seen == list(range(1, packs + 1))
    # meta：started -> completed
    assert [m["status"] for m in calls["meta"]] == ["started", "completed"]
    assert calls["meta"][0]["totalPackets"] == packs
    assert calls["meta"][0]["reqId"] == "t1"
    assert calls["meta"][1]["badCrc"] == 0
    # fragment：按包号顺序、imageId 一致、拼接 == 合成 JPEG
    frags = calls["frag"]
    assert [f["packetNo"] for f in frags] == list(range(1, packs + 1))
    assert len({f["imageId"] for f in frags}) == 1
    assert frags[0]["imageId"] == res["imageId"]
    import base64
    assembled = b"".join(base64.b64decode(f["data"]) for f in frags)
    assert assembled == jpeg
    assert all(f["crcOk"] for f in frags)
    # 状态量（2026-10-12 裁减后：仅 last_capture_ts + last_image 两键，
    # ok/total/image_count 统计点已从 read_all 移除）
    st = reader.read_all()
    assert "last_capture_ts" in st
    assert "ok" not in st and "total" not in st and "image_count" not in st
    assert st["last_image"] == res["imageId"]


# ---------------------------------------------------------------------------
# 3. 拒绝路径
# ---------------------------------------------------------------------------
def test_capture_rejects_large_size(cam_env):
    reader, sim, calls, jpeg = cam_env
    res = reader.capture(size="4")
    assert not res["ok"] and "size" in res["message"]
    assert not sim.h_seen.is_set()           # 未触发任何串口事务
    assert not calls["frag"] and not calls["meta"]


def test_capture_throttled_min_interval(cam_env):
    reader, sim, calls, jpeg = cam_env
    assert reader.capture(size="1")["ok"]
    res2 = reader.capture(size="1")          # 距上次 <15s，直接拒绝
    assert not res2["ok"] and "15" in res2["message"]


# ---------------------------------------------------------------------------
# 4. 重试 / 断点续取 / 校验计数
# ---------------------------------------------------------------------------
def test_packet_retry_on_timeout(cam_env):
    reader, sim, calls, jpeg = cam_env
    sim.drop_e = {2: 2}                      # 第 2 包前 2 次不应答 -> 第 3 次成功
    res = reader.capture(size="1")
    assert res["ok"], res.get("message")
    packs = (len(jpeg) + 511) // 512
    assert [f["packetNo"] for f in calls["frag"]] == list(range(1, packs + 1))
    assert sim.e_seen.count(2) == 3          # 第 2 包取了 3 次


def test_fatigue_rest_and_resume(cam_env):
    reader, sim, calls, jpeg = cam_env
    sim.drop_e = {2: 3}                      # 3 次重试全丢 -> 静置清缓冲后断点续取成功
    res = reader.capture(size="1")
    assert res["ok"], res.get("message")
    assert sim.e_seen.count(2) == 4          # 3 次重试 + 续取 1 次


def test_crc_bad_counted_but_completes(cam_env):
    reader, sim, calls, jpeg = cam_env
    sim.corrupt = {2}
    res = reader.capture(size="1")
    assert res["ok"]
    assert res["badCrc"] == 1
    frag2 = [f for f in calls["frag"] if f["packetNo"] == 2][0]
    assert frag2["crcOk"] is False


# ---------------------------------------------------------------------------
# 5. 整事务持锁
# ---------------------------------------------------------------------------
def test_transaction_holds_port_lock(cam_env):
    reader, sim, calls, jpeg = cam_env
    sim.e_delay = 0.1                        # 拖长事务，确保持锁窗口可观测
    lock = bm._port_lock(reader.port)
    result = {}
    th = threading.Thread(target=lambda: result.update(reader.capture(size="1")),
                          daemon=True)
    th.start()
    assert sim.h_seen.wait(2)                # 抓拍已开始（H 已发）
    assert not lock.acquire(timeout=0.05)    # 事务期间外部拿不到同一把锁
    th.join(timeout=30)
    assert result.get("ok"), result.get("message")
    assert lock.acquire(timeout=1)           # 事务结束锁已释放
    lock.release()


# ---------------------------------------------------------------------------
# 6. resend 免重拍补发
# ---------------------------------------------------------------------------
def test_resend_republishes_requested_packets(cam_env):
    reader, sim, calls, jpeg = cam_env
    res = reader.capture(size="1")
    assert res["ok"]
    image_id = res["imageId"]
    n_before = len(calls["frag"])
    r = reader.resend(image_id, [2, 1, 2])   # 去重排序后补 1、2 两片
    assert r["ok"], r.get("message")
    new_frags = calls["frag"][n_before:]
    assert [f["packetNo"] for f in new_frags] == [1, 2]
    assert all(f["imageId"] == image_id for f in new_frags)


def test_resend_rejects_unknown_image(cam_env):
    reader, sim, calls, jpeg = cam_env
    r = reader.resend("no-such-image", [1])
    assert not r["ok"]


# ---------------------------------------------------------------------------
# 5. K 在线探测（read_all = 探测 + 状态回报；2026-10-12 起）
# ---------------------------------------------------------------------------

def test_probe_pass_reports_status(cam_env):
    """探测通过：SimCamera 应答 UK#，read_all 返回状态两键；K 载荷为灯原状态 0。"""
    reader, sim, calls, jpeg = cam_env
    st = reader.read_all()
    assert "last_capture_ts" in st and "last_image" in st
    assert sim.k_seen and sim.k_seen[-1] == 0   # 补光灯「设为原状态」（默认关=0）


def test_probe_fail_raises_ioerror(cam_env):
    """探测失败：drop_k 模拟掉线（无应答），read_all 抛 IOError → 采集循环退避停报。"""
    reader, sim, calls, jpeg = cam_env
    sim.drop_k = True
    with pytest.raises(IOError):
        reader.read_all()


def test_probe_lock_busy_returns_empty(cam_env):
    """锁忙：抓拍事务持锁时 read_all 返回 {}（本轮静默跳过，不报错不进退避）。"""
    reader, sim, calls, jpeg = cam_env
    assert reader._lock.acquire(timeout=0.5)
    try:
        assert reader.read_all() == {}
    finally:
        reader._lock.release()
    # 放锁后探测恢复：再次 read_all 正常返回状态
    st = reader.read_all()
    assert "last_capture_ts" in st


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
