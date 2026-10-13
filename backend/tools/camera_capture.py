#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智景 SVL130w 串口摄像头使用脚本（双协议固件 XY-Y-01，Z 协议 + A 版全集）
======================================================================
协议来源：2026-09-28/29 两次抓包逆向（DMS + USR-VCOM relay 中间人），
详见《摄像头/摄像头补充材料/Z协议逆向笔记.md》《A版协议命令手册.md》。

本固件 = 双协议：
  ① Z 协议（产线调试）：5A×16 + 4A×16 + <参数> + 5A + 23
     无设备 ID 概念；拍图 100% 可靠（裸流，无握手）
  ② A 版协议子集（U/# 帧，**必须 ID=1**，非标称的 0）：
     H/R/E/F 拍图取包、Q 压缩率、K 补光灯、S OSD（只开不关）可用；
     B 查信息不支持（任意 ID 无应答）；D 改 ID / I 波特率未实测。
     A 版有设备 ID —— 多摄像头 485 总线寻址走这套。

Z 协议命令：
  拍图    01 <count> <size>  -> JPEG 裸流（连拍=多张连推）
  查版本  03                 -> "SVL130w_V,XY-Y-01,OK1"（0.03s，在线探测）
  波特率  00 <ascii code>    -> OK/OKRESET（⚠️设成同值=复位回115200）
A 版命令（U=0x55 头，#=0x23 尾，小端，本机 ID=1）：
  H 拍图（尺寸=ASCII '1'~'5' + 分包2B）-> R 帧报大小/包数 -> E 逐包取 -> F 数据帧(带校验)
  Q 压缩率 20~250（应答延迟，设完须静置 2~3s 再拍图）
  D 改 ID（⚠️未实测，组网前逐台验证）  K 补光灯 1/0  S OSD 水印（只开不关）
  size: 1=160x120 2=320x240 3=640x480 4=1280x720 5=1280x960

固件疲劳特性：连续密集命令后周期性失态，静置 10~15s 自愈。
  => 命令间隔 >=2s；拍图间隔 >=15s；A 版 9600 下取包 ~20 包后易失态（用 size=1 小图）。

零第三方依赖：有 pyserial 优先用，没有则 macOS/Linux 走内置 termios。

用法（macOS）：
  python3 camera_capture.py list
  python3 camera_capture.py -p /dev/cu.usbserial-1130 ver            # Z 在线探测
  python3 camera_capture.py -p /dev/cu.usbserial-1130 scan           # 扫波特率（零副作用）
  python3 camera_capture.py -p /dev/cu.usbserial-1130 snap           # Z 单拍 320x240
  python3 camera_capture.py -p /dev/cu.usbserial-1130 snap -n 4      # Z 连拍 4 张
  python3 camera_capture.py -p /dev/cu.usbserial-1130 baud 115200    # Z 提速
  --- A 版（多机寻址用，--id 默认 1）---
  python3 camera_capture.py -p /dev/cu.usbserial-1130 asnap --size 1        # A 版拍图取包
  python3 camera_capture.py -p /dev/cu.usbserial-1130 --id 2 asnap --size 1 # 拍 2 号机
  python3 camera_capture.py -p /dev/cu.usbserial-1130 quality 200    # 压缩率（设完静置）
  python3 camera_capture.py -p /dev/cu.usbserial-1130 led off        # 关补光灯
  python3 camera_capture.py -p /dev/cu.usbserial-1130 osd --text TEST
  python3 camera_capture.py -p /dev/cu.usbserial-1130 setid 2        # ⚠️未实测
"""

from __future__ import annotations

import argparse
import glob
import os
import platform
import select
import struct
import subprocess
import sys
import termios
import time

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

IOSSIOSPEED = 0x80045402   # macOS：设置任意波特率

# ===================== Z 协议 =====================
PREAMBLE = b"\x5A" * 16 + b"\x4A" * 16
SUFFIX = b"\x5A\x23"
SUB_BAUD, SUB_SNAP, SUB_VERSION = 0x00, 0x01, 0x03

SIZES = {1: "160x120", 2: "320x240", 3: "640x480", 4: "1280x720", 5: "1280x960"}
BAUD_CODES = {"0": 9600, "1": 19200, "2": 38400, "3": 57600, "4": 115200,
              "5": 2400, "6": 14400, "7": 230400, "8": 460800, "9": 921600}

# ===================== A 版协议 =====================
AU_HEAD, AU_TAIL, AU_ERR, AU_DATA = 0x55, 0x23, 0x3F, 0x46
AU_SIZES = {"1": "160x120", "2": "320x240", "3": "640x480",
            "4": "1280x720", "5": "1280x960"}


def z_frame(payload: bytes) -> bytes:
    return PREAMBLE + payload + SUFFIX


def build_snap_cmd(size_code: int, count: int = 1) -> bytes:
    return z_frame(bytes([SUB_SNAP, count & 0xFF, size_code]))


def build_version_cmd() -> bytes:
    return z_frame(bytes([SUB_VERSION]))


def build_baud_cmd(rate: int) -> bytes:
    code = next((k for k, v in BAUD_CODES.items() if v == rate), None)
    if code is None:
        raise PortError("波特率 %d 不支持，可选：%s" % (rate, sorted(BAUD_CODES.values())))
    return z_frame(bytes([SUB_BAUD]) + code.encode("ascii"))


def au_frame(cmd: str, cam_id: int, payload: bytes = b"") -> bytes:
    return bytes([AU_HEAD, ord(cmd), cam_id & 0xFF]) + payload + bytes([AU_TAIL])


# --------------------------------------------------------------------------- #
#  串口层：pyserial 优先，POSIX 回退 termios
# --------------------------------------------------------------------------- #
class PortError(Exception):
    pass


class RecvTimeout(Exception):
    pass


class _PySerialPort:
    def __init__(self, path, baud, timeout):
        import serial
        self.path, self.baud, self.timeout = path, baud, timeout
        try:
            self._s = serial.Serial(path, baudrate=baud, timeout=timeout,
                                    bytesize=8, parity="N", stopbits=1)
        except Exception as exc:
            raise PortError("打开串口失败 %s: %s" % (path, exc))

    def read(self, n, timeout=None):
        if timeout is not None:
            self._s.timeout = max(0.01, timeout)
        return self._s.read(n)

    def write(self, data):
        return self._s.write(data)

    def flush_input(self):
        try:
            self._s.reset_input_buffer()
        except Exception:
            pass

    def close(self):
        try:
            self._s.close()
        except Exception:
            pass


class _TermiosPort:
    """macOS / Linux 零依赖直驱串口。"""

    def __init__(self, path, baud, timeout):
        self.path, self.baud, self.timeout = path, baud, timeout
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise PortError("打开串口失败 %s: %s" % (path, exc))
        self._configure()

    def _configure(self):
        if sys.platform == "darwin":
            try:
                import fcntl
                fcntl.ioctl(self.fd, IOSSIOSPEED, struct.pack("I", self.baud))
            except Exception:
                pass
        try:
            attrs = termios.tcgetattr(self.fd)
        except termios.error as exc:
            raise PortError("%s 不是串口设备: %s" % (self.path, exc))
        const = getattr(termios, "B%d" % self.baud, None)
        if const is None:
            const = self.baud if sys.platform == "darwin" else None
        if const is None:
            raise PortError("系统不支持波特率 %d" % self.baud)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[4] = attrs[5] = const
        attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        except termios.error as exc:
            raise PortError("设置串口参数失败: %s" % exc)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def read(self, n, timeout=None):
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        buf = b""
        while len(buf) < n:
            left = deadline - time.time()
            if left <= 0:
                break
            r, _, _ = select.select([self.fd], [], [], min(left, 0.2))
            if r:
                chunk = os.read(self.fd, n - len(buf))
                if not chunk:
                    break
                buf += chunk
        return buf

    def write(self, data):
        view, done = memoryview(data), 0
        deadline = time.time() + 5.0
        while done < len(view):
            try:
                done += os.write(self.fd, view[done:])
            except BlockingIOError:
                left = deadline - time.time()
                if left <= 0:
                    raise PortError("发送超时：串口持续不可写")
                select.select([], [self.fd], [], min(left, 0.2))
        return done

    def flush_input(self):
        try:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass

    def close(self):
        if getattr(self, "fd", None) is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


def open_port(path, baud, timeout):
    try:
        import serial  # noqa: F401
    except ImportError:
        if platform.system() == "Windows":
            raise PortError("Windows 下请先 pip install pyserial")
        return _TermiosPort(path, baud, timeout)
    return _PySerialPort(path, baud, timeout)


# --------------------------------------------------------------------------- #
#  共用接收
# --------------------------------------------------------------------------- #
def read_window(port, seconds, idle_tail=0.3):
    """seconds 窗口内接收；每收到数据后续 idle_tail 秒静默即收尾。"""
    end = time.time() + seconds
    buf = bytearray()
    while time.time() < end:
        chunk = port.read(4096, timeout=0.2)
        if chunk:
            buf += chunk
            end = time.time() + idle_tail
    return bytes(buf)


# --------------------------------------------------------------------------- #
#  Z 协议操作
# --------------------------------------------------------------------------- #
def query_version(port, wait=1.5):
    """查版本：返回应答文本（容忍前导噪声，子串匹配）。无应答返回 None。"""
    port.flush_input()
    port.write(build_version_cmd())
    buf = read_window(port, wait)
    if not buf:
        return None
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in buf)
    if "SVL" in text or "XY-" in text or "OK" in text:
        return text
    return text or None


def count_jpegs(stream):
    n, pos = 0, 0
    while True:
        soi = stream.find(JPEG_SOI, pos)
        if soi < 0:
            return n
        eoi = stream.find(JPEG_EOI, soi + 2)
        if eoi < 0:
            return n
        n += 1
        pos = eoi + 2


def snapshot(port, size_code=2, count=1, idle_timeout=5.0,
             max_seconds=300.0, verbose=True):
    """Z 拍图：发 01 <count> <size>，收 count 段 JPEG 裸流。"""
    cmd = build_snap_cmd(size_code, count)
    port.flush_input()
    if verbose:
        print("  -> %d 字节：...%s（拍 %d 张 %s）"
              % (len(cmd), cmd[-5:].hex(" ").upper(), count, SIZES[size_code]))
    port.write(cmd)
    stream = bytearray()
    t0 = time.time()
    last_rx = t0
    while True:
        now = time.time()
        if now - t0 > max_seconds:
            break
        if stream and now - last_rx > idle_timeout:
            break
        if not stream and now - t0 > 15:
            raise RecvTimeout("15 秒内无任何返回：摄像头未接/未上电/波特率不符/固件疲劳")
        chunk = port.read(4096, timeout=0.2)
        if chunk:
            stream += chunk
            last_rx = now
            if verbose and len(stream) % 16384 < 4096:
                print("  已收 %d 字节（%.1f KB/s）"
                      % (len(stream), len(stream) / 1024.0 / max(now - t0, 0.001)))
        if count_jpegs(stream) >= count:
            break
    shots, pos = [], 0
    while len(shots) < count:
        soi = stream.find(JPEG_SOI, pos)
        if soi < 0:
            break
        eoi = stream.find(JPEG_EOI, soi + 2)
        if eoi < 0:
            shots.append(bytes(stream[soi:]))
            break
        shots.append(bytes(stream[soi:eoi + 2]))
        pos = eoi + 2
    return shots, time.time() - t0


def set_baud(port, rate, verbose=True):
    """Z 协议设波特率。⚠️ 设成同值 = 复位回 115200。"""
    port.flush_input()
    port.write(build_baud_cmd(rate))
    resp = read_window(port, 2.0)
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in resp)
    if verbose:
        print("  应答：%s |%s|" % (resp.hex(" ").upper() if resp else "(无)", text))
    if "OKRESET" in text:
        print("  ⚠️ 设为与当前相同的值 -> 摄像头复位回默认 115200！")
        return 115200
    if "OK" in text:
        if verbose:
            print("  摄像头复位中（3s）...")
        time.sleep(3)
        return rate
    raise PortError("设波特率无有效应答：%s" % text)


# --------------------------------------------------------------------------- #
#  A 版协议操作（U/# 帧，ID=1；多机寻址用）
# --------------------------------------------------------------------------- #
def _au_pop_ack(buf, cmd, cam_id):
    """缓冲头部切出 'U <cmd> <id> #' 应答（4 字节）。"""
    if len(buf) >= 4 and buf[0] == AU_HEAD and buf[1] == cmd \
            and buf[2] == cam_id and buf[3] == AU_TAIL:
        del buf[:4]
        return True
    return False


def _au_pop_err(buf, cam_id):
    if len(buf) >= 4 and buf[0] == AU_HEAD and buf[1] == AU_ERR \
            and buf[2] == cam_id and buf[3] == AU_TAIL:
        del buf[:4]
        return True
    return False


def _au_pop_rframe(buf, cam_id):
    """切出 R 帧（10 字节）：55 52 id <大小4B LE> <包数2B LE> 23。"""
    if len(buf) >= 10 and buf[0] == AU_HEAD and buf[1] == ord("R") \
            and buf[2] == cam_id and buf[9] == AU_TAIL:
        total = int.from_bytes(buf[3:7], "little")
        packs = int.from_bytes(buf[7:9], "little")
        del buf[:10]
        return total, packs
    return None


def _au_pop_dataframe(buf, cam_id):
    """切出 F 帧：55 46 id <包号2B> <包长2B> <数据N> <校验2B>（总长 9+N）。"""
    if len(buf) < 7:
        return None
    if not (buf[0] == AU_HEAD and buf[1] == AU_DATA and buf[2] == cam_id):
        return None
    pack_no = int.from_bytes(buf[3:5], "little")
    pack_len = int.from_bytes(buf[5:7], "little")
    total = 9 + pack_len
    if len(buf) < total:
        return None
    data = bytes(buf[7:7 + pack_len])
    chk = int.from_bytes(buf[7 + pack_len:total], "little")
    calc = sum(buf[:7 + pack_len]) & 0xFFFF
    del buf[:total]
    return pack_no, data, chk == calc


def _au_resync(buf, cam_id):
    """失同步时丢弃垃圾字节，但**保留头部疑似合法帧的部分**：
    若 buf 头部是 55 xx <id>（可能是未到齐的应答/F 帧），原样保留等更多数据。
    ⚠️ 不能无脑切到「下一个 0x55」——JPEG 数据里天然含 0x55，
    未到齐的 F 帧会被误切掉头，永远拼不齐（此 bug 曾致第 3 包必死）。"""
    if len(buf) < 3:
        return                      # 可能是帧头开头，保留
    if buf[0] == AU_HEAD and buf[2] == cam_id:
        return                      # 头部像合法帧，保留等到齐
    i = buf.find(bytes([AU_HEAD]), 1)
    if i > 0:
        del buf[:i]
    elif len(buf) > 4096:
        buf.clear()


def au_transact(port, cmd, cam_id, payload=b"", timeout=3.0, verbose=True):
    """发 A 版命令并等 'U cmd id #' 应答；错误应答/超时抛异常。"""
    raw = au_frame(cmd, cam_id, payload)
    if verbose:
        print("  -> %-24s %s" % (raw.hex(" ").upper(), _ascii(raw)))
    port.flush_input()
    port.write(raw)
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = port.read(256, timeout=0.2)
        if chunk:
            buf += chunk
            if verbose:
                print("  <- %s" % bytes(chunk).hex(" ").upper())
        if _au_pop_err(buf, cam_id):
            raise PortError("摄像头返回错误应答（命令 %s 无法执行）" % cmd)
        if _au_pop_ack(buf, ord(cmd), cam_id):
            return True
        _au_resync(buf, cam_id)
    raise RecvTimeout("命令 %s 等待应答超时（ID=%d 不对？固件疲劳？）" % (cmd, cam_id))


def au_snapshot(port, cam_id, size_char="1", packet=512, timeout=4.0, verbose=True):
    """A 版拍图取包全流程：H -> R -> E/F 逐包（含疲劳规避与断点续取）。
    返回 (jpeg_bytes, total_size, packs, 耗时)。"""
    t0 = time.time()
    # ---- 1. H 拍图 ----
    raw = au_frame("H", cam_id, size_char.encode() + struct.pack("<H", packet))
    if verbose:
        print("  -> %-24s UH 拍图 size=%s 分包=%d" % (raw.hex(" ").upper(), size_char, packet))
    port.flush_input()
    port.write(raw)
    buf = bytearray()
    deadline = time.time() + 8
    total_size = pack_count = None
    while time.time() < deadline:
        chunk = port.read(4096, timeout=0.3)
        if chunk:
            buf += chunk
        if _au_pop_ack(buf, ord("H"), cam_id) and verbose:
            print("  <- UH# 应答（拍照中，延时 Tp）")
        r = _au_pop_rframe(buf, cam_id)
        if r:
            total_size, pack_count = r
            if verbose:
                print("  <- UR 图片大小=%d 字节，共 %d 包" % (total_size, pack_count))
            break
        _au_resync(buf, cam_id)
    if pack_count is None:
        raise RecvTimeout("未收到 R 帧（ID/波特率/接线/疲劳，静置 15s 再试）")

    # ---- 2. E/F 逐包取 ----
    image = bytearray()
    bad_crc = 0
    for no in range(1, pack_count + 1):
        pkt = None
        for attempt in range(3):
            try:
                pkt = _au_fetch_packet(port, cam_id, no, timeout, verbose)
                break
            except RecvTimeout:
                if verbose:
                    print("  ⚠️ 第 %d 包超时（第 %d/3 次）" % (no, attempt + 1))
                if attempt < 2:
                    time.sleep(2)
        if pkt is None:
            if verbose:
                print("  固件疑似疲劳，静置 15s 后断点续取第 %d 包..." % no)
            time.sleep(15)
            port.flush_input()
            pkt = _au_fetch_packet(port, cam_id, no, timeout, verbose)
        image += pkt[0]
        if not pkt[1]:
            bad_crc += 1
        time.sleep(0.15)                      # 包间隔，防疲劳
        if no % 10 == 0 and no < pack_count:
            time.sleep(1.0)                   # 每 10 包小憩
    return bytes(image), total_size, pack_count, bad_crc, time.time() - t0


def _au_fetch_packet(port, cam_id, pack_no, timeout, verbose):
    """取一包：UE -> UE# 应答 + UF 数据帧。返回 (数据, 校验OK)。"""
    raw = au_frame("E", cam_id, struct.pack("<H", pack_no))
    if verbose:
        print("  -> %-24s UE 取第 %d 包" % (raw.hex(" ").upper(), pack_no))
    port.write(raw)
    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = port.read(4096, timeout=0.3)
        if chunk:
            buf += chunk
        _au_pop_ack(buf, ord("E"), cam_id)
        frame = _au_pop_dataframe(buf, cam_id)
        if frame:
            no, data, ok = frame
            if verbose:
                print("  <- UF 包号=%d 长度=%d 校验=%s" % (no, len(data),
                                                          "OK" if ok else "FAIL"))
            if no != pack_no:
                raise RecvTimeout("包号不符（期望 %d 实到 %d）" % (pack_no, no))
            return data, ok
        _au_resync(buf, cam_id)
    raise RecvTimeout("第 %d 包接收超时" % pack_no)


# --------------------------------------------------------------------------- #
#  工具
# --------------------------------------------------------------------------- #
def _ascii(raw):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in raw)


def check_jpeg(jpeg):
    bad = []
    if not jpeg.startswith(JPEG_SOI):
        bad.append("缺 JPEG 头 FFD8")
    if not jpeg.endswith(JPEG_EOI):
        bad.append("缺 JPEG 尾 FFD9（可能未收完）")
    return "；".join(bad) if bad else "JPEG 结构完整"


def save_jpeg(jpeg, outdir, cam_id=None, index=None):
    os.makedirs(outdir, exist_ok=True)
    stem = "cam%s_%s" % ("" if cam_id is None else str(cam_id),
                         time.strftime("%Y%m%d-%H%M%S"))
    if index is not None:
        stem += "_%d" % index
    path = os.path.join(outdir, stem + ".jpg")
    n = 1
    while os.path.exists(path):
        path = os.path.join(outdir, "%s_%d.jpg" % (stem, n))
        n += 1
    with open(path, "wb") as fp:
        fp.write(jpeg)
    return path


def system_open(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.startfile(path)  # noqa: S606
    except Exception:
        pass


def list_ports():
    pats = ["/dev/cu.*", "/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*"]
    found = []
    for p in pats:
        found.extend(sorted(glob.glob(p)))
    prefer = [x for x in found if any(k in x for k in ("usbserial", "usbmodem", "wch", "ttyACM"))]
    return prefer + [x for x in found if x not in prefer]


def scan_baud(path, rates, wait=1.2, verbose=True):
    """扫波特率：每档发 Z 查版本（0.03s 应答，零副作用）。"""
    hits = []
    for rate in rates:
        try:
            port = open_port(path, rate, 0.3)
        except (PortError, OSError) as exc:
            if verbose:
                print("  %-7d 无法打开（%s）" % (rate, exc))
            continue
        try:
            resp = query_version(port, wait=wait)
            if resp:
                if verbose:
                    print("  %-7d ★ 有应答：|%s|" % (rate, resp))
                hits.append(rate)
            elif verbose:
                print("  %-7d 无应答" % rate)
        finally:
            port.close()
        time.sleep(0.3)
    return hits


def selftest():
    print("自检：Z 协议 + A 版组帧（与抓包/说明书逐一比对）")
    fails = []
    # Z 1. 单拍 37 字节
    if build_snap_cmd(2, 1) == PREAMBLE + bytes([1, 1, 2]) + SUFFIX:
        print("  [OK] Z 单拍命令（01 子命令/01 张数/02 尺寸）")
    else:
        fails.append("Z 拍图组帧错误")
    # Z 2. 连拍第 34 字节=张数
    if build_snap_cmd(2, 4) == PREAMBLE + bytes([1, 4, 2]) + SUFFIX:
        print("  [OK] Z 连拍命令（第 34 字节=张数）")
    else:
        fails.append("Z 连拍组帧错误")
    # Z 3. 查版本 / 波特率
    if build_version_cmd() == PREAMBLE + bytes([3]) + SUFFIX \
            and build_baud_cmd(9600) == PREAMBLE + bytes([0]) + b"0" + SUFFIX:
        print("  [OK] Z 查版本 35B / 设波特率 36B（code=ASCII）")
    else:
        fails.append("Z 查版本/波特率组帧错误")
    # A 4. H 命令 = 说明书示例 55 48 01 32 00 02 23
    if au_frame("H", 1, b"2" + struct.pack("<H", 512)) == bytes.fromhex("5548013200022 3".replace(" ", "")):
        print("  [OK] A 版 H 命令与说明书示例一致 55 48 01 32 00 02 23")
    else:
        fails.append("A 版 H 组帧错误")
    # A 5. F 帧解析 + 校验
    body = bytes([AU_HEAD, AU_DATA, 1]) + struct.pack("<H", 3) + struct.pack("<H", 4) + b"ABCD"
    fbuf = bytearray(body + struct.pack("<H", sum(body) & 0xFFFF))
    fr = _au_pop_dataframe(fbuf, 1)
    if fr and fr[0] == 3 and fr[1] == b"ABCD" and fr[2] and not fbuf:
        print("  [OK] A 版 F 帧解析与校验和正确")
    else:
        fails.append("A 版 F 帧解析错误")
    # A 6. R 帧解析（18358B/36包，来自实测抓包）
    rbuf = bytearray(bytes.fromhex("55 52 01 B6 47 00 00 24 00 23".replace(" ", "")))
    rr = _au_pop_rframe(rbuf, 1)
    if rr == (18358, 36):
        print("  [OK] A 版 R 帧解析正确（18358 字节 / 36 包）")
    else:
        fails.append("A 版 R 帧解析错误")
    print("\n自检结果：%s" % ("全部通过" if not fails else "失败：" + "；".join(fails)))
    return 0 if not fails else 1


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="camera_capture.py",
        description="智景 SVL130w 串口摄像头（双协议固件 XY-Y-01）：Z 协议 + A 版全集",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", "-p", help="串口，如 /dev/cu.usbserial-1130（macOS 用 cu.*）")
    ap.add_argument("--baud", "-b", type=int, default=9600,
                    help="摄像头当前波特率，默认 9600（改过则须对应）")
    ap.add_argument("--id", type=int, default=1,
                    help="A 版命令用的设备 ID，默认 1（本机实测值；Z 命令忽略此参数）")
    ap.add_argument("--quiet", "-q", action="store_true", help="减少日志输出")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出本机串口")
    sub.add_parser("selftest", help="不接硬件自检（Z + A 版组帧）")
    sub.add_parser("ver", help="[Z] 查询版本/在线探测（0.03s 应答）")

    p = sub.add_parser("scan", help="[Z] 扫波特率（发查版本，零副作用不拍照片）")
    p.add_argument("--rates", default="9600,115200,57600,38400,19200,14400,2400")
    p.add_argument("--wait", type=float, default=1.2)

    p = sub.add_parser("snap", help="[Z] 拍图（裸流，100%% 可靠）")
    p.add_argument("--size", type=int, default=2, choices=sorted(SIZES))
    p.add_argument("--count", "-n", type=int, default=1, help="单命令连拍张数")
    p.add_argument("--out", "-o", default="photos")
    p.add_argument("--max-wait", type=float, default=300.0)
    p.add_argument("--no-open", action="store_true")

    p = sub.add_parser("baud", help="[Z] 设波特率（⚠️设成同值=复位回115200）")
    p.add_argument("rate", type=int, choices=sorted(BAUD_CODES.values()))

    p = sub.add_parser("asnap", help="[A版] 拍图取包（H/R/E/F，多机寻址用 --id）")
    p.add_argument("--size", default="1", choices=list(AU_SIZES),
                   help="1=160x120(默认,最稳) 2=320x240 3=640x480 4=1280x720 5=1280x960")
    p.add_argument("--packet", type=int, default=512, help="分包大小，默认 512")
    p.add_argument("--timeout", type=float, default=4.0, help="每包超时秒数")
    p.add_argument("--out", "-o", default="photos")
    p.add_argument("--no-open", action="store_true")

    p = sub.add_parser("quality", help="[A版] 设压缩率 20~250（应答延迟，设完静置 2~3s）")
    p.add_argument("value", type=int)

    p = sub.add_parser("setid", help="[A版] 改设备 ID（⚠️本固件未实测，组网前逐台验证）")
    p.add_argument("new_id", type=int)

    p = sub.add_parser("led", help="[A版] 补光灯开关（断电恢复默认开）")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("osd", help="[A版] OSD 水印（只开不关；仅英文 ASCII ≤80 字符）")
    p.add_argument("--text", required=True)
    p.add_argument("--line", type=int, default=0)
    p.add_argument("--x", type=int, default=0)
    p.add_argument("--y", type=int, default=0)

    p = sub.add_parser("raw", help="发任意十六进制字节并打印返回（协议探测用）")
    p.add_argument("--hex", required=True)
    p.add_argument("--seconds", type=float, default=3.0)

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 1
    if args.cmd == "list":
        ports = list_ports()
        if not ports:
            print("未发现串口：请确认 USB 转串口已插入")
            return 1
        print("发现串口（推荐用前面的）：")
        for x in ports:
            print("  " + x)
        return 0
    if args.cmd == "selftest":
        return selftest()
    if not args.port:
        print("错误：请用 --port 指定串口（先跑 list 查看）")
        return 1
    if args.cmd == "scan":
        rates = [int(x) for x in args.rates.split(",") if x.strip()]
        print("扫描 %s：逐档发查版本帧（每档 %.1fs，零副作用）..." % (args.port, args.wait))
        hits = scan_baud(args.port, rates, wait=args.wait)
        if not hits:
            print("\n全部波特率无应答。检查：① 接线与供电（上电满 2~3s）"
                  " ② 485 A/B 极性 ③ 固件疲劳中（静置 15s 再试）")
            return 1
        print("\n命中：摄像头当前波特率 = %d" % hits[0])
        print("建议命令：")
        print("  python3 %s -p %s -b %d snap" % (os.path.basename(__file__), args.port, hits[0]))
        return 0

    port = None
    try:
        port = open_port(args.port, args.baud, 0.5)
        verbose = not args.quiet

        if args.cmd == "ver":
            resp = query_version(port)
            if resp:
                print("摄像头在线：|%s|" % resp)
                return 0
            print("[失败] 无应答（波特率 %d 不对？先跑 scan）" % args.baud)
            return 2

        if args.cmd == "baud":
            effective = set_baud(port, args.rate, verbose=verbose)
            print("生效波特率：%d（后续命令请加 -b %d）" % (effective, effective))
            return 0

        if args.cmd == "raw":
            clean = "".join(c for c in args.hex if c in "0123456789abcdefABCDEF")
            data = bytes.fromhex(clean)
            port.flush_input()
            print("发送 %d 字节：%s" % (len(data), data.hex(" ").upper()))
            port.write(data)
            buf = read_window(port, args.seconds)
            print("返回 %d 字节：%s" % (len(buf), buf.hex(" ").upper() if buf else "(无)"))
            if buf:
                print("  ASCII：|%s|" % _ascii(buf[:80]))
            return 0 if buf else 1

        if args.cmd == "snap":
            print("拍图：%d 张 %s @ %d" % (args.count, SIZES[args.size], args.baud))
            shots, cost = snapshot(port, size_code=args.size, count=args.count,
                                   max_seconds=args.max_wait, verbose=verbose)
            if not shots:
                print("[失败] 未收到 JPEG 流")
                return 2
            for i, jpeg in enumerate(shots, 1):
                path = save_jpeg(jpeg, args.out, index=i if len(shots) > 1 else None)
                print("  [%d/%d] %s（%d 字节，%s）"
                      % (i, len(shots), path, len(jpeg), check_jpeg(jpeg)))
                if not args.no_open:
                    system_open(path)
            print("共 %d 张，耗时 %.1fs" % (len(shots), cost))
            if len(shots) < args.count:
                print("⚠️ 只收到 %d/%d 张（固件疲劳？静置 15s 重试）" % (len(shots), args.count))
            return 0

        # ---------------- A 版命令 ----------------
        if args.cmd == "asnap":
            print("[A版] 拍图：ID=%d size=%s（%s）分包=%d @ %d"
                  % (args.id, args.size, AU_SIZES[args.size], args.packet, args.baud))
            jpeg, total, packs, bad, cost = au_snapshot(
                port, args.id, size_char=args.size, packet=args.packet,
                timeout=args.timeout, verbose=verbose)
            note = check_jpeg(jpeg)
            path = save_jpeg(jpeg, args.out, cam_id=args.id)
            print("  已保存：%s（%d 字节/R 帧报 %d，%d 包，校验失败 %d，%.1fs，%s）"
                  % (path, len(jpeg), total, packs, bad, cost, note))
            if not args.no_open:
                system_open(path)
            return 0 if note == "JPEG 结构完整" else 1

        if args.cmd == "quality":
            au_transact(port, "Q", args.id, bytes([args.value]), verbose=verbose)
            print("压缩率已设置为 %d（⚠️ 应答可能延迟，静置 2~3s 再拍图）" % args.value)
            time.sleep(2)
            return 0

        if args.cmd == "setid":
            print("⚠️ 注意：D 改 ID 在本固件（XY-Y-01）上尚未实测验证。")
            au_transact(port, "D", args.id, bytes([args.new_id]), verbose=verbose)
            print("ID 已改为 %d（后续 A 版命令请加 --id %d）" % (args.new_id, args.new_id))
            return 0

        if args.cmd == "led":
            au_transact(port, "K", args.id, bytes([1 if args.state == "on" else 0]),
                        verbose=verbose)
            print("补光灯已%s" % ("开启" if args.state == "on" else "关闭"))
            return 0

        if args.cmd == "osd":
            body = args.text.encode("ascii", "replace")[:80]
            payload = (bytes([1, args.line & 0xFF, 2])
                       + struct.pack(">H", args.x) + struct.pack(">H", args.y)
                       + struct.pack(">H", 0x7C) + struct.pack(">H", 0xFFFE)
                       + bytes([len(body)]) + body)
            au_transact(port, "S", args.id, payload, verbose=verbose)
            print("OSD 已设置：|%s|（⚠️ 本固件只开不关，断电恢复）" % args.text)
            return 0
    except (PortError, RecvTimeout, OSError) as exc:
        msg = str(exc)
        print("\n[失败] %s" % msg)
        if "Resource busy" in msg or "Errno 16" in msg:
            print("串口被占用：关闭其它串口程序后重试")
        else:
            print("排查：① 波特率（先跑 scan）② A 版 ID 是否为 1 ③ 上电满 2~3s"
                  " ④ 固件疲劳（静置 15s）")
        return 2
    finally:
        if port is not None:
            port.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
