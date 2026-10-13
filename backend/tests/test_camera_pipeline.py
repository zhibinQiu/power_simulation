#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄像头图片重组流水线 + ingest image/# 分支 + REST 路由 模拟验证（不依赖真实硬件）：

覆盖：
  1. Assembler：乱序/重复片重组 -> 落盘 + 索引 + FFD8/FFD9 校验；
  2. 坏图（缺 FFD8/FFD9）仍落盘但标记 jpegOk=False；
  3. 超时缺片：sweep 下发 resend（mock publish 到 cmd/{box}/camera），
     2 轮仍缺判废并记索引失败条目；
  4. 盒子 meta failed 事件记入索引；
  5. ingest 的 image/# 分支：fragment 不进 READINGS/CLOUD_DEVICES/消息日志，
     meta 只记消息日志；
  6. REST 路由：size>=2 抓拍拒绝（400）、图片列表/单图/删除冒烟。

运行：cd backend && python3 -m pytest tests/test_camera_pipeline.py -v
"""
from __future__ import annotations

import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.mqtt_source import camera_assembler as ca  # noqa: E402
from app.mqtt_source import ingest, _shared  # noqa: E402
from app.api import box_router  # noqa: E402


def _jpeg(n=1200, soi=b"\xff\xd8", eoi=b"\xff\xd9"):
    body = bytes((i * 5 + 7) % 256 for i in range(n - len(soi) - len(eoi)))
    return soi + body + eoi


def _frag(image_id, no, total, data, crc_ok=True):
    return {"imageId": image_id, "packetNo": no, "totalPackets": total,
            "packetLen": len(data), "crcOk": crc_ok,
            "data": base64.b64encode(data).decode("ascii")}


def _chunks(data, n):
    size = (len(data) + n - 1) // n
    return [data[i * size:(i + 1) * size] for i in range(n)]


@pytest.fixture
def asm_env(monkeypatch, tmp_path):
    """独立 Assembler 实例 + 临时存储目录 + mock 下发/通知。"""
    published = []
    notified = []
    monkeypatch.setattr(ca, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(ca, "_SWEEP_STARTED", True)   # 不起后台扫描线程
    monkeypatch.setattr(ca, "_ASSEMBLER", ca._Assembler())
    monkeypatch.setattr(ca, "publish",
                        lambda topic, payload: (published.append((topic, payload))
                                                or {"ok": True, "topic": topic}))
    monkeypatch.setattr(ca, "_notify",
                        lambda level, title, body, detail="": notified.append(
                            {"level": level, "title": title, "body": body}))
    return {"published": published, "notified": notified, "root": str(tmp_path)}


# ---------------------------------------------------------------------------
# 1. 乱序/重复片重组
# ---------------------------------------------------------------------------
def test_reassemble_out_of_order_and_duplicates(asm_env):
    jpeg = _jpeg()
    parts = _chunks(jpeg, 3)
    image_id = "cam1-1001"
    a = ca._ASSEMBLER
    a.handle_fragment("box1", "cam1", _frag(image_id, 3, 3, parts[2]))   # 乱序
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 3, parts[0]))
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 3, parts[0]))   # 重复片去重
    assert ca.list_assembling()              # 未齐套不落盘
    a.handle_fragment("box1", "cam1", _frag(image_id, 2, 3, parts[1]))

    path = ca.image_path("cam1", image_id)
    assert path and os.path.isfile(path)
    with open(path, "rb") as fp:
        assert fp.read() == jpeg
    items = ca.list_images("cam1")
    assert items[0]["imageId"] == image_id and items[0]["jpegOk"] is True
    assert items[0]["packets"] == 3 and items[0]["status"] == "completed"
    assert not ca.list_assembling()          # 齐套后缓冲已清
    assert asm_env["notified"] and asm_env["notified"][0]["level"] == "success"


def test_broken_jpeg_marked_but_stored(asm_env):
    jpeg = _jpeg(soi=b"\x00\x00")            # 缺 FFD8 头
    parts = _chunks(jpeg, 2)
    image_id = "cam1-1002"
    a = ca._ASSEMBLER
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 2, parts[0]))
    a.handle_fragment("box1", "cam1", _frag(image_id, 2, 2, parts[1]))
    items = ca.list_images("cam1")
    assert items[0]["jpegOk"] is False and "FFD8" in items[0]["jpegNote"]
    assert ca.image_path("cam1", image_id)   # 坏图也落盘（人工排查用）
    assert asm_env["notified"][0]["level"] == "warn"


# ---------------------------------------------------------------------------
# 2. 超时缺片 -> resend -> 判废
# ---------------------------------------------------------------------------
def test_timeout_resend_two_rounds_then_failed(asm_env, monkeypatch):
    monkeypatch.setattr(ca, "ASSEMBLE_TTL", 0)     # 立即超时
    jpeg = _jpeg()
    parts = _chunks(jpeg, 2)
    image_id = "cam1-1003"
    a = ca._ASSEMBLER
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 2, parts[0]))

    a.sweep()                                       # 第 1 轮补发
    assert len(asm_env["published"]) == 1
    topic, payload = asm_env["published"][0]
    assert topic == "cmd/box1/camera"
    assert payload["cmd"] == "resend" and payload["device"] == "cam1"
    assert payload["imageId"] == image_id and payload["packetNos"] == [2]

    a.sweep()                                       # 第 2 轮补发
    assert len(asm_env["published"]) == 2
    a.sweep()                                       # 第 3 次扫描：2 轮已满 -> 判废
    assert len(asm_env["published"]) == 2
    items = ca.list_images("cam1")
    assert items[0]["status"] == "failed" and "判废" in items[0]["message"]
    assert not ca.list_assembling()
    assert any(n["level"] == "error" for n in asm_env["notified"])


def test_resend_fragment_completes_image(asm_env, monkeypatch):
    monkeypatch.setattr(ca, "ASSEMBLE_TTL", 0)
    jpeg = _jpeg()
    parts = _chunks(jpeg, 2)
    image_id = "cam1-1004"
    a = ca._ASSEMBLER
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 2, parts[0]))
    a.sweep()                                       # 触发补发
    assert asm_env["published"][0][1]["packetNos"] == [2]
    a.handle_fragment("box1", "cam1", _frag(image_id, 2, 2, parts[1]))  # 补片到达
    assert ca.list_images("cam1")[0]["status"] == "completed"
    with open(ca.image_path("cam1", image_id), "rb") as fp:
        assert fp.read() == jpeg


# ---------------------------------------------------------------------------
# 3. meta 事件
# ---------------------------------------------------------------------------
def test_meta_failed_recorded(asm_env):
    a = ca._ASSEMBLER
    a.handle_meta("box1", "cam1", {"imageId": "cam1-1005", "status": "failed",
                                   "message": "抓拍过于频繁：拍图间隔需 ≥15s"})
    items = ca.list_images("cam1")
    assert items[0]["status"] == "failed" and "15s" in items[0]["message"]
    assert asm_env["notified"][0]["level"] == "warn"


# ---------------------------------------------------------------------------
# 4. ingest 的 image/# 分支纪律
# ---------------------------------------------------------------------------
def _msg(topic, payload):
    class M:
        pass
    m = M()
    m.topic = topic
    m.payload = json.dumps(payload).encode("utf-8")
    return m


def test_ingest_image_branch_isolated(asm_env):
    jpeg = _jpeg()
    parts = _chunks(jpeg, 2)
    frag = _frag("cam1-2001", 1, 2, parts[0])
    meta = {"imageId": "cam1-2001", "status": "started", "totalPackets": 2}
    readings_before = len(_shared.READINGS)
    cloud_before = len(_shared.CLOUD_DEVICES)
    log_before = len(_shared.MESSAGE_LOG)

    ingest._record_message(_msg("image/box1/cam1/fragment", frag))
    # fragment：不进数值缓存、不建云端设备、不记消息日志
    assert len(_shared.READINGS) == readings_before
    assert len(_shared.CLOUD_DEVICES) == cloud_before
    assert len(_shared.MESSAGE_LOG) == log_before
    assert ca.list_assembling()[0]["received"] == 1

    ingest._record_message(_msg("image/box1/cam1/meta", meta))
    # meta：记一条消息日志（审计），但同样不污染读数缓存
    assert len(_shared.MESSAGE_LOG) == log_before + 1
    assert _shared.MESSAGE_LOG[-1]["topic"] == "image/box1/cam1/meta"
    assert len(_shared.READINGS) == readings_before
    assert len(_shared.CLOUD_DEVICES) == cloud_before


# ---------------------------------------------------------------------------
# 5. REST 路由冒烟
# ---------------------------------------------------------------------------
def test_route_capture_rejects_large_size():
    req = box_router.BoxCameraCaptureRequest(box="nt001", resolution="4")
    with pytest.raises(Exception) as exc:
        box_router.box_camera_capture("cam1", req)
    assert "400" in str(exc.value) or "size" in str(exc.value)


def test_route_capture_publishes_cmd(monkeypatch):
    sent = []
    monkeypatch.setattr(box_router.mqtt_source, "publish",
                        lambda topic, payload: (sent.append((topic, payload))
                                                or {"ok": True, "topic": topic}))
    req = box_router.BoxCameraCaptureRequest(box="nt001", resolution="1")
    r = box_router.box_camera_capture("cam1", req)
    assert r["ok"] and r["reqId"]
    topic, payload = sent[0]
    assert topic == "cmd/nt001/camera"
    assert payload["cmd"] == "capture" and payload["device"] == "cam1"
    assert payload["resolution"] == "1"


def test_route_images_and_get_and_delete(asm_env, monkeypatch):
    # 先用 Assembler 造一张图，再走路由读取
    jpeg = _jpeg()
    parts = _chunks(jpeg, 2)
    image_id = "cam1-3001"
    a = ca._ASSEMBLER
    a.handle_fragment("box1", "cam1", _frag(image_id, 1, 2, parts[0]))
    a.handle_fragment("box1", "cam1", _frag(image_id, 2, 2, parts[1]))

    monkeypatch.setattr(box_router.mqtt_source, "camera_list_images", ca.list_images)
    monkeypatch.setattr(box_router.mqtt_source, "camera_list_assembling", ca.list_assembling)
    monkeypatch.setattr(box_router.mqtt_source, "camera_image_path", ca.image_path)
    monkeypatch.setattr(box_router.mqtt_source, "camera_delete_image", ca.delete_image)

    r = box_router.box_camera_images("cam1")
    assert r["ok"] and r["images"][0]["imageId"] == image_id

    resp = box_router.box_camera_image("cam1", image_id)
    assert getattr(resp, "media_type", "") == "image/jpeg"

    r = box_router.box_camera_image_delete("cam1", image_id)
    assert r["ok"]
    assert not ca.list_images("cam1")
    with pytest.raises(Exception):
        box_router.box_camera_image("cam1", image_id)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
