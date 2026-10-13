"""mqtt_source 包：摄像头图片分片重组器（image/# 主题）。

链路（详见《摄像头接入方案.md》）：盒子 CameraReader 逐包取回摄像头数据后立即经
image/{box}/{device}/meta|fragment（qos=1）直发，盒子不拼图、不落盘；本模块负责：
  - 按 imageId 重组：乱序容忍、重复片去重；
  - 齐套按 packetNo 顺序拼接 → FFD8/FFD9 校验 → 落盘 backend/data/camera/{device}/
    并维护每设备 index.json；
  - 180s 未齐套：经 cmd/{box}/camera 下发 resend 补片（摄像头内部缓存免重拍），
    最多 2 轮，仍缺判废；
  - 盒子 meta 事件（started/completed/failed）同步进度与失败记录；
  - 完成/失败经 realtime.FeedManager.notify 推送前端事件（抓拍进度由 REST 查询
    list_assembling 获得，不用事件刷屏）。
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .publish import publish

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

DATA_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "data", "camera"))
INDEX_NAME = "index.json"
ASSEMBLE_TTL = 180.0          # 重组超时（秒）：超时缺片先补发，再判废
RESEND_MAX_ROUNDS = 2         # 缺片补发轮数上限（免重拍，依赖摄像头内部缓存）
SWEEP_INTERVAL = 10.0         # 超时扫描周期（秒）
RETAIN_MAX_IMAGES = 500       # 每设备保留图片数上限
RETAIN_MAX_AGE = 30 * 86400   # 每设备图片保留时长（30 天）

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _fs_safe(s: Any) -> str:
    return _SAFE.sub("_", str(s or ""))[:120]


def check_jpeg(jpeg: bytes) -> str:
    """JPEG 结构校验（与 camera_capture.py 同口径）。返回 "OK" 或问题描述。"""
    bad = []
    if not jpeg.startswith(JPEG_SOI):
        bad.append("缺 JPEG 头 FFD8")
    if not jpeg.endswith(JPEG_EOI):
        bad.append("缺 JPEG 尾 FFD9（可能未收完）")
    return "；".join(bad) if bad else "OK"


class _Assembler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bufs: Dict[str, Dict[str, Any]] = {}   # key = device + "/" + imageId

    # ---------------- 入口：ingest 的 image/# 分支 ----------------
    def handle_meta(self, box: str, device: str, data: Dict[str, Any]) -> None:
        image_id = str(data.get("imageId") or "").strip()
        if not image_id:
            return
        status = str(data.get("status") or "").lower()
        key = self._key(device, image_id)
        with self._lock:
            if status == "started":
                buf = self._bufs.get(key)
                if buf is None:
                    buf = self._new_buf(box, device, image_id)
                    self._bufs[key] = buf
                buf["total"] = int(data.get("totalPackets") or buf["total"] or 0)
                buf["totalSize"] = int(data.get("totalSize") or 0)
                buf["trigger"] = str(data.get("triggerSource") or "")
                buf["size"] = str(data.get("size") or "")
                buf["updated"] = time.time()
            elif status == "failed":
                self._bufs.pop(key, None)
                msg = str(data.get("message") or "盒子侧抓拍失败")
                self._index_append_locked(device, {
                    "imageId": image_id, "ts": time.time(), "status": "failed",
                    "message": msg, "trigger": str(data.get("triggerSource") or ""),
                })
                _notify("warn", "摄像头抓拍失败", "%s：%s" % (device, msg),
                        detail=json.dumps({"kind": "camera", "device": device,
                                           "imageId": image_id, "status": "failed"},
                                          ensure_ascii=False))
            # status=completed：分片齐套时由 _finalize 落盘（completed meta 仅作信息，
            # 盒子先发完分片再发 completed，时序上无需在此处理）

    def handle_fragment(self, box: str, device: str, data: Dict[str, Any]) -> None:
        image_id = str(data.get("imageId") or "").strip()
        if not image_id:
            return
        try:
            no = int(data.get("packetNo"))
            total = int(data.get("totalPackets"))
            raw = base64.b64decode(str(data.get("data") or ""), validate=False)
        except (TypeError, ValueError):
            return
        if not (1 <= no <= total) or not raw:
            return
        key = self._key(device, image_id)
        done = None
        with self._lock:
            buf = self._bufs.get(key)
            if buf is None:
                buf = self._new_buf(box, device, image_id)
                self._bufs[key] = buf
            if not buf["total"]:
                buf["total"] = total
            if no in buf["frags"]:
                return   # 重复片去重
            buf["frags"][no] = raw
            if not data.get("crcOk", True):
                buf["badCrc"] += 1
            buf["updated"] = time.time()
            if len(buf["frags"]) >= int(buf["total"] or 0) > 0:
                done = self._finalize_locked(buf)
        if done:
            _notify("success" if done.get("jpegOk") else "warn",
                    "摄像头抓拍完成" if done.get("jpegOk") else "图片校验异常",
                    "%s：%s（%d 字节 / %d 片%s）" % (
                        device, image_id, done["bytes"], done["packets"],
                        "" if done.get("jpegOk") else "，" + done.get("jpegNote", "")),
                    detail=json.dumps({"kind": "camera", "device": device,
                                       "imageId": image_id, "status": "completed",
                                       "jpegOk": done.get("jpegOk")}, ensure_ascii=False))

    # ---------------- 内部 ----------------
    @staticmethod
    def _key(device: str, image_id: str) -> str:
        return "%s/%s" % (device, image_id)

    @staticmethod
    def _new_buf(box: str, device: str, image_id: str) -> Dict[str, Any]:
        now = time.time()
        return {"box": box, "device": device, "imageId": image_id,
                "total": 0, "totalSize": 0, "frags": {}, "badCrc": 0,
                "trigger": "", "size": "", "created": now, "updated": now,
                "resend_rounds": 0}

    def _finalize_locked(self, buf: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        total = int(buf["total"])
        frags = buf["frags"]
        if any(no not in frags for no in range(1, total + 1)):
            return None   # 理论不到这里（len 检查兜底），防御
        jpeg = b"".join(frags[no] for no in range(1, total + 1))
        note = check_jpeg(jpeg)
        device, image_id = buf["device"], buf["imageId"]
        fdir = self._device_dir(device)
        os.makedirs(fdir, exist_ok=True)
        fname = _fs_safe(image_id) + ".jpg"
        with open(os.path.join(fdir, fname), "wb") as fp:
            fp.write(jpeg)
        entry = {
            "imageId": image_id, "ts": time.time(), "status": "completed",
            "bytes": len(jpeg), "packets": total, "badCrc": int(buf["badCrc"]),
            "trigger": buf.get("trigger") or "", "size": buf.get("size") or "",
            "jpegOk": note == "OK", "jpegNote": "" if note == "OK" else note,
            "file": fname,
        }
        self._index_append_locked(device, entry)
        self._bufs.pop(self._key(device, image_id), None)
        self._retention_locked(device)
        return entry

    def sweep(self) -> None:
        """周期扫描：超时未齐套的缓冲补发缺片（≤2 轮）或判废。"""
        now = time.time()
        expired_resend: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        with self._lock:
            for key, buf in list(self._bufs.items()):
                total = int(buf["total"] or 0)
                if total <= 0 or now - float(buf["updated"]) < ASSEMBLE_TTL:
                    continue
                missing = [no for no in range(1, total + 1) if no not in buf["frags"]]
                if not missing:
                    continue
                if int(buf["resend_rounds"]) < RESEND_MAX_ROUNDS:
                    buf["resend_rounds"] += 1
                    buf["updated"] = now
                    expired_resend.append({"box": buf["box"], "device": buf["device"],
                                           "imageId": buf["imageId"], "missing": missing,
                                           "round": buf["resend_rounds"]})
                else:
                    failed.append({"key": key, "device": buf["device"],
                                   "imageId": buf["imageId"], "missing": missing,
                                   "received": len(buf["frags"]), "total": total})
            for f in failed:
                self._bufs.pop(f["key"], None)
                self._index_append_locked(f["device"], {
                    "imageId": f["imageId"], "ts": now, "status": "failed",
                    "message": "缺片补发 %d 轮仍不齐（%d/%d 片），判废"
                               % (RESEND_MAX_ROUNDS, f["received"], f["total"]),
                })
        for r in expired_resend:
            res = publish("cmd/%s/camera" % r["box"], {
                "cmd": "resend", "device": r["device"], "imageId": r["imageId"],
                "packetNos": r["missing"], "request_id": uuid.uuid4().hex[:12]})
            print("[camera] %s 缺片 %d 片，第 %d 轮补发下发%s: %s" % (
                r["imageId"], len(r["missing"]), r["round"],
                "成功" if res.get("ok") else "失败", r["missing"][:20]))
        for f in failed:
            _notify("error", "摄像头图片判废",
                    "%s：%s 缺片补发 %d 轮仍不齐（%d/%d 片）" % (
                        f["device"], f["imageId"], RESEND_MAX_ROUNDS,
                        f["received"], f["total"]),
                    detail=json.dumps({"kind": "camera", "device": f["device"],
                                       "imageId": f["imageId"], "status": "failed"},
                                      ensure_ascii=False))

    # ---------------- 索引 / 保留策略 ----------------
    @staticmethod
    def _device_dir(device: str) -> str:
        return os.path.join(DATA_ROOT, _fs_safe(device))

    def _index_path(self, device: str) -> str:
        return os.path.join(self._device_dir(device), INDEX_NAME)

    def _index_read_locked(self, device: str) -> List[Dict[str, Any]]:
        try:
            with open(self._index_path(device), "r", encoding="utf-8") as fp:
                items = json.load(fp)
            return items if isinstance(items, list) else []
        except Exception:
            return []

    def _index_append_locked(self, device: str, entry: Dict[str, Any]) -> None:
        fdir = self._device_dir(device)
        os.makedirs(fdir, exist_ok=True)
        items = self._index_read_locked(device)
        # 同一 imageId 只保留最新一条（failed 后重拍同 id 不堆积）
        items = [x for x in items if x.get("imageId") != entry.get("imageId")]
        items.append(entry)
        items = items[-RETAIN_MAX_IMAGES:]
        try:
            tmp = self._index_path(device) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(items, fp, ensure_ascii=False, indent=1)
            os.replace(tmp, self._index_path(device))
        except Exception as e:  # noqa: BLE001
            print("[camera] 索引写入失败 %s: %s" % (device, e))

    def _retention_locked(self, device: str) -> None:
        """保留策略：每设备最多 RETAIN_MAX_IMAGES 张、最长 RETAIN_MAX_AGE 秒。"""
        fdir = self._device_dir(device)
        items = self._index_read_locked(device)
        now = time.time()
        keep: List[Dict[str, Any]] = []
        changed = False
        for x in items:
            too_old = now - float(x.get("ts") or 0) > RETAIN_MAX_AGE
            if too_old and x.get("file"):
                changed = True
                try:
                    os.remove(os.path.join(fdir, x["file"]))
                except OSError:
                    pass
                continue
            keep.append(x)
        overflow = [x for x in keep if x.get("file")][:-RETAIN_MAX_IMAGES]
        for x in overflow:
            changed = True
            try:
                os.remove(os.path.join(fdir, x["file"]))
            except OSError:
                pass
            keep.remove(x)
        if changed:
            try:
                tmp = self._index_path(device) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(keep, fp, ensure_ascii=False, indent=1)
                os.replace(tmp, self._index_path(device))
            except Exception:  # noqa: BLE001
                pass

    # ---------------- 查询接口（REST 路由用） ----------------
    def list_images(self, device: str) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._index_read_locked(device)
        return sorted(items, key=lambda x: float(x.get("ts") or 0), reverse=True)

    def image_path(self, device: str, image_id: str) -> Optional[str]:
        with self._lock:
            items = self._index_read_locked(device)
        ent = next((x for x in items
                    if x.get("imageId") == image_id and x.get("status") == "completed"
                    and x.get("file")), None)
        if not ent:
            return None
        path = os.path.join(self._device_dir(device), ent["file"])
        return path if os.path.isfile(path) else None

    def delete_image(self, device: str, image_id: str) -> bool:
        with self._lock:
            items = self._index_read_locked(device)
            ent = next((x for x in items if x.get("imageId") == image_id), None)
            if not ent:
                return False
            if ent.get("file"):
                try:
                    os.remove(os.path.join(self._device_dir(device), ent["file"]))
                except OSError:
                    pass
            items = [x for x in items if x.get("imageId") != image_id]
            try:
                tmp = self._index_path(device) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fp:
                    json.dump(items, fp, ensure_ascii=False, indent=1)
                os.replace(tmp, self._index_path(device))
            except Exception:  # noqa: BLE001
                pass
            self._bufs.pop(self._key(device, image_id), None)
        return True

    def list_assembling(self, device: Optional[str] = None) -> List[Dict[str, Any]]:
        """重组进行中的图片进度（前端抓拍进度条：已收/总包数）。"""
        with self._lock:
            out = []
            for buf in self._bufs.values():
                if device and buf["device"] != device:
                    continue
                total = int(buf["total"] or 0)
                out.append({"device": buf["device"], "imageId": buf["imageId"],
                            "received": len(buf["frags"]), "total": total,
                            "resendRounds": int(buf["resend_rounds"]),
                            "startedTs": buf["created"], "updatedTs": buf["updated"]})
            return sorted(out, key=lambda x: x["startedTs"], reverse=True)


_ASSEMBLER = _Assembler()
_SWEEP_STARTED = False
_SWEEP_LOCK = threading.Lock()


def _notify(level: str, title: str, body: str, detail: str = "") -> None:
    """经 FeedManager 推送前端事件（惰性导入，避免 mqtt_source <-> realtime 循环依赖）。"""
    try:
        from .. import realtime
        realtime.manager.notify(level, title, body, detail)
    except Exception:  # noqa: BLE001
        pass


def _ensure_sweeper() -> None:
    global _SWEEP_STARTED
    with _SWEEP_LOCK:
        if _SWEEP_STARTED:
            return
        _SWEEP_STARTED = True

    def _loop() -> None:
        while True:
            time.sleep(SWEEP_INTERVAL)
            try:
                _ASSEMBLER.sweep()
            except Exception as e:  # noqa: BLE001
                print("[camera] 重组器扫描异常: %s" % e)

    threading.Thread(target=_loop, daemon=True, name="camera-assembler-sweep").start()


def handle_image_message(topic: str, data: Dict[str, Any]) -> bool:
    """ingest 的 image/# 分支入口：topic = image/{box}/{device}/meta|fragment。"""
    parts = [p for p in str(topic or "").split("/") if p]
    if len(parts) < 4 or parts[0] != "image":
        return False
    _ensure_sweeper()
    box, device, part = parts[1], parts[2], parts[3]
    if part == "meta":
        _ASSEMBLER.handle_meta(box, device, data)
        return True
    if part == "fragment":
        _ASSEMBLER.handle_fragment(box, device, data)
        return True
    return False


# ---- REST 路由查询接口（box_router 用） ----
def list_images(device: str) -> List[Dict[str, Any]]:
    return _ASSEMBLER.list_images(device)


def image_path(device: str, image_id: str) -> Optional[str]:
    return _ASSEMBLER.image_path(device, image_id)


def delete_image(device: str, image_id: str) -> bool:
    return _ASSEMBLER.delete_image(device, image_id)


def list_assembling(device: Optional[str] = None) -> List[Dict[str, Any]]:
    return _ASSEMBLER.list_assembling(device)
