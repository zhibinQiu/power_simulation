#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智景科技 JZ-CAM / SV130 / JZ460 系列「RS232/RS485 串口摄像头」A 版协议工具
======================================================================
功能：配置摄像头参数（波特率 / 压缩率 / ID / 补光灯 / OSD 水印）+ 抓拍照片并保存为 JPEG + 自动生成网页预览。

协议要点（摘自《智景科技通讯协议(130万波特率921600).doc》）
----------------------------------------------------------------------
物理层：RS232 / RS485 / TTL，8N1，波特率 9600~921600（本型号 130 万像素默认 921600）

三种帧（所有多字节字段均为小端，低字节在前）：

  1) 命令帧（上位机 -> 摄像头）
     'U'(0x55) + 命令字(1) + 设备ID(1) + 命令内容(0..n) + '#'(0x23)

  2) 应答帧（摄像头 -> 上位机）
     正确：'U' + 原命令字(1) + 设备ID(1) + '#'
     错误：'U' + '?'(0x3F)     + 设备ID(1) + '#'

  3) 数据帧（摄像头 -> 上位机，仅取图片包时）
     'U' + 'F'(0x46) + 设备ID(1) + 包号(2) + 包长度(2) + 图片数据(n) + 校验和(2)
     校验和 = 从 'U' 起、到校验和之前所有字节的累加和（& 0xFFFF，小端存放）

命令字表：
  H 拍图：内容 = 图像尺寸(1字节 ASCII '1'~'5') + 分包大小(2字节小端)
          '1'=160x128  '2'=320x240  '3'=640x480  '4'=1280x720  '5'=1280x960(130万)
  R 图片信息（摄像头主动上报）：内容 = 图片总字节(4) + 分包数量(2)，整帧固定 10 字节
  E 取包：内容 = 包号(2字节小端，从 1 开始)；随后摄像头回 E 应答 + F 数据帧
  F 数据包（见上）
  D 改 ID：内容 = 新ID(1)
  I 改波特率：'0'=9600 '1'=19200 '2'=38400 '3'=57600 '4'=115200
              '5'=2400 '6'=14400 '7'=230400 '8'=460800 '9'=921600
  Q 改压缩率：内容 = 压缩率(1字节，20~250，出厂默认 150/160，越大越小越糊)
  B 查信息：内容 = 0x02；应答 = ID(1) + 主版本(1) + 次版本(1) + FWName1 + FWName2
  K 补光灯：内容 = 1开/0关（摄像头断电重启后恢复默认开启）
  S OSD 水印：启用(1) + 行号(1) + 字号(1) + X(2,大端,偶数) + Y(2,大端,偶数)
              + 前景色(2,大端) + 背景色(2,大端,0xFFFE=透明) + 文本长度(1) + 文本(ASCII)

拍图交互时序：
  上位机 --U H ID 尺寸 包大小 #-->  摄像头
  上位机 <--U H ID #--------------  摄像头（命令已收到）
  上位机 <--U R ID 总长度 包数 #---  摄像头（拍图耗时 Tp，最短 200ms，最坏可达 5~6s）
  上位机 --U E ID 包号 #---------->  摄像头（逐包索取）
  上位机 <--U E ID #--------------  摄像头
  上位机 <--U F ID 包号 长度 数据 校验和#-- 摄像头
  拼接全部包数据即为一张完整 JPEG（FFD8 ... FFD9）

注意事项：
  * 232/TTL 摄像头 ID 默认恒为 0；RS485 总线上多台时 ID 取 1~33，0xFF 为广播。
  * 130 万系统上电启动需 2~3s，上电后立刻通讯会无应答。
  * 高于 115200 的波特率需要摄像头与上位机接口芯片同时支持（TTL 口可直接 921600）。

零第三方依赖：优先使用 pyserial（如已安装），否则使用内置 termios 直驱串口。
自检：  python3 serial_camera.py selftest     （不接硬件即可验证帧解析/校验/拼图逻辑）
"""

from __future__ import annotations

import argparse
import base64
import glob
import html as _html
import os
import platform
import select
import struct
import subprocess
import sys
import termios
import time

HEAD = 0x55          # 'U'
TAIL = 0x23          # '#'
CMD_ERROR = 0x3F     # '?'
CMD_DATA = 0x46      # 'F'

# 图像尺寸代码 -> (宽, 高)
SIZES = {
    "1": (160, 128),
    "2": (320, 240),
    "3": (640, 480),
    "4": (1280, 720),
    "5": (1280, 960),   # 130 万
}

# 波特率代码 <-> 波特率
BAUD_CODES = {
    "0": 9600,
    "1": 19200,
    "2": 38400,
    "3": 57600,
    "4": 115200,
    "5": 2400,
    "6": 14400,
    "7": 230400,
    "8": 460800,
    "9": 921600,
}

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

# macOS 专用：设置任意波特率（普通 tcsetattr 对非标准速率会失败）
IOSSIOSPEED = 0x80045402


# --------------------------------------------------------------------------- #
#  串口底层：pyserial 优先，回退 termios
# --------------------------------------------------------------------------- #
class PortError(Exception):
    pass


class TimeoutError_(Exception):
    pass


class _PySerialPort:
    """已安装 pyserial 时使用（Windows 也只能走这条路）。"""

    def __init__(self, path: str, baud: int, timeout: float):
        import serial  # noqa: WPS433  (延迟导入，保持零依赖)

        self.path = path
        self.baud = baud
        self.timeout = timeout
        try:
            self._s = serial.Serial(path, baudrate=baud, timeout=timeout, bytesize=8,
                                    parity="N", stopbits=1, rtscts=False, dsrdtr=False)
        except Exception as exc:  # noqa: BLE001
            raise PortError("打开串口失败 %s: %s" % (path, exc))

    def read(self, n: int, timeout: float | None = None) -> bytes:
        if timeout is not None:
            self._s.timeout = max(0.01, timeout)
        data = self._s.read(n)
        if len(data) < n:
            raise TimeoutError_("读取超时：期望 %d 字节，实到 %d 字节" % (n, len(data)))
        return data

    def write(self, data: bytes) -> int:
        return self._s.write(data)

    def flush_input(self) -> None:
        try:
            self._s.reset_input_buffer()
        except Exception:  # noqa: BLE001
            pass

    def drain(self) -> None:
        try:
            self._s.flush()
        except Exception:  # noqa: BLE001
            pass

    def set_rts(self, on: bool) -> bool:
        try:
            self._s.rts = on
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:  # noqa: BLE001
            pass


# RS485 方向控制：切换 RTS 电平。POSIX 下 TIOCMGET/TIOCMSET 的常量并非每个平台都暴露。
_TIOCMGET = getattr(termios, "TIOCMGET", 0x4004746A if sys.platform == "darwin" else 0x5415)
_TIOCMSET = getattr(termios, "TIOCMSET", 0x8004746D if sys.platform == "darwin" else 0x5418)
_TIOCM_RTS = getattr(termios, "TIOCM_RTS", 0x004)
_TIOCM_DTR = getattr(termios, "TIOCM_DTR", 0x002)


class _TermiosPort:
    """POSIX 直驱串口（macOS / Linux），零依赖。"""

    def __init__(self, path: str, baud: int, timeout: float):
        self.path = path
        self.baud = baud
        self.timeout = timeout
        self.fd = None
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise PortError("打开串口失败 %s: %s" % (path, exc))
        self._configure()

    @staticmethod
    def _baud_const(rate: int) -> int:
        const = getattr(termios, "B%d" % rate, None)
        if const is not None:
            return const
        if sys.platform == "darwin":
            # BSD/macOS：波特率常量在 termios 模块中可能缺失，其数值就等于速率本身
            return rate
        raise PortError("当前系统不支持波特率 %d" % rate)

    def _configure(self) -> None:
        fd = self.fd
        # macOS：优先用 IOSSIOSPEED 设任意波特率（CH34x/FTDI/CP210x 驱动均支持）
        if sys.platform == "darwin":
            try:
                import fcntl

                fcntl.ioctl(fd, IOSSIOSPEED, struct.pack("I", self.baud))
            except Exception:  # noqa: BLE001
                pass
        try:
            attrs = termios.tcgetattr(fd)
        except termios.error as exc:
            raise PortError("%s 不是可用的串口设备: %s" % (self.path, exc))
        const = self._baud_const(self.baud)
        attrs[0] = 0                                        # iflag: 原始输入
        attrs[1] = 0                                        # oflag: 原始输出
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0                                        # lflag: 非规范模式
        attrs[4] = const                                    # ispeed
        attrs[5] = const                                    # ospeed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        try:
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except termios.error as exc:
            raise PortError("设置串口参数失败（波特率 %d 可能不被该串口芯片支持）: %s"
                            % (self.baud, exc))
        termios.tcflush(fd, termios.TCIOFLUSH)

    def read(self, n: int, timeout: float | None = None) -> bytes:
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        buf = b""
        while len(buf) < n:
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError_("读取超时：期望 %d 字节，实到 %d 字节" % (n, len(buf)))
            r, _, _ = select.select([self.fd], [], [], min(left, 0.2))
            if not r:
                continue
            chunk = os.read(self.fd, n - len(buf))
            if not chunk:
                raise TimeoutError_("串口已断开")
            buf += chunk
        return buf

    def write(self, data: bytes) -> int:
        """fd 是 O_NONBLOCK 的，缓冲区满时 os.write 直接抛 BlockingIOError(EAGAIN)。
        若不重试，数据会被静默丢弃——表现为「发若干次后再也发不出去」的假死。
        这里 select 等可写后重试，超时才判失败。"""
        view = memoryview(data)
        done = 0
        deadline = time.time() + 5.0
        while done < len(view):
            try:
                done += os.write(self.fd, view[done:])
            except BlockingIOError:
                left = deadline - time.time()
                if left <= 0:
                    raise PortError("发送超时：串口持续不可写，设备可能已掉线")
                select.select([], [self.fd], [], min(left, 0.2))
        return done

    def flush_input(self) -> None:
        try:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:  # noqa: BLE001
            pass
        deadline = time.time() + 0.15
        while time.time() < deadline:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                break
            try:
                if not os.read(self.fd, 4096):
                    break
            except OSError:
                break

    def drain(self) -> None:
        if self.fd is not None:
            try:
                termios.tcdrain(self.fd)
            except Exception:  # noqa: BLE001
                pass

    def set_rts(self, on: bool) -> bool:
        """RS485 收发换向：切换 RTS 电平。驱动不支持时返回 False。"""
        if self.fd is None:
            return False
        try:
            import fcntl

            res = fcntl.ioctl(self.fd, _TIOCMGET, struct.pack("I", 0))
            cur = struct.unpack("I", res)[0] if isinstance(res, (bytes, bytearray)) else int(res)
            cur = (cur | _TIOCM_RTS) if on else (cur & ~_TIOCM_RTS)
            fcntl.ioctl(self.fd, _TIOCMSET, struct.pack("I", cur))
            return True
        except Exception:  # noqa: BLE001  (驱动不实现 modem 控制位)
            return False

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


def open_port(path: str, baud: int, timeout: float):
    try:
        import serial  # noqa: F401
    except ImportError:
        if platform.system() == "Windows":
            raise PortError("Windows 下请先安装 pyserial：pip install pyserial")
        return _TermiosPort(path, baud, timeout)
    return _PySerialPort(path, baud, timeout)


# --------------------------------------------------------------------------- #
#  协议帧
# --------------------------------------------------------------------------- #
class Frame:
    """一帧数据。非数据帧用 payload，数据帧(F)额外有 pack_no / data / checksum。"""

    def __init__(self, cmd: int, cam_id: int, payload: bytes = b"",
                 pack_no: int = 0, pack_len: int = 0,
                 data: bytes = b"", checksum: int = 0, raw: bytes = b""):
        self.cmd = cmd
        self.cam_id = cam_id
        self.payload = payload
        self.pack_no = pack_no
        self.pack_len = pack_len
        self.data = data
        self.checksum = checksum
        self.raw = raw

    @property
    def cmd_char(self) -> str:
        return chr(self.cmd)

    @property
    def is_error(self) -> bool:
        return self.cmd == CMD_ERROR

    @property
    def is_data(self) -> bool:
        return self.cmd == CMD_DATA

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        if self.is_data:
            return "<Frame F id=%d pack=%d len=%d chk=0x%04X>" % (
                self.cam_id, self.pack_no, self.pack_len, self.checksum)
        return "<Frame %s id=%d payload=%s>" % (
            self.cmd_char, self.cam_id, self.payload.hex(" "))


# --------------------------------------------------------------------------- #
#  摄像头
# --------------------------------------------------------------------------- #
class SerialCamera:
    def __init__(self, port, cam_id: int = 0, timeout: float = 3.0,
                 snap_timeout: float = 15.0, retries: int = 3, verbose: bool = True,
                 rs485_dir: str | None = None):
        """rs485_dir：RTS 换向型 RS485 模块用。"high"=发送时拉高 RTS，"low"=发送时拉低，
        None（默认）= 自动换向模块，完全不管 RTS。"""
        self.port = port
        self.cam_id = cam_id
        self.timeout = timeout
        self.snap_timeout = snap_timeout
        self.retries = retries
        self.verbose = verbose
        self.rs485_dir = rs485_dir
        self._rts_ok = True

    # ---------- 基础 IO ----------
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    @staticmethod
    def build_cmd(cmd: str, cam_id: int, payload: bytes = b"") -> bytes:
        return bytes([HEAD, ord(cmd), cam_id & 0xFF]) + payload + bytes([TAIL])

    def set_rx(self) -> None:
        """把 RS485 置于接收态（RTS 换向型模块必需）。"""
        if self.rs485_dir and self._rts_ok:
            self._rts_ok = self.port.set_rts(self.rs485_dir != "high")

    def send(self, cmd: str, payload: bytes = b"", cam_id: int | None = None) -> bytes:
        raw = self.build_cmd(cmd, self.cam_id if cam_id is None else cam_id, payload)
        self._log("  -> %-28s %s" % (raw.hex(" ").upper(), _ascii(raw)))
        if self.rs485_dir and self._rts_ok:
            tx_level = self.rs485_dir == "high"
            self._rts_ok = self.port.set_rts(tx_level)
            time.sleep(0.001)
            try:
                self.port.write(raw)
                self.port.drain()          # 等最后一个字节真正送出总线
                # 换向余量只留 2 个字符时间。原先固定 2ms，在 115200 下相当于 23 个字节，
                # 会把摄像头紧随其后的应答开头（帧头 0x55）整个吃掉，表现为「永远收不到」。
                time.sleep(max(0.0002, 20.0 / (getattr(self, "baud", 0) or 115200)))
            finally:
                self.port.set_rts(not tx_level)
        else:
            self.port.write(raw)
        return raw

    def read_frame(self, timeout: float | None = None) -> Frame:
        """从字节流中解出一帧：同步到 0x55，数据帧按长度收，其余收到 0x23 为止。"""
        deadline = time.time() + (self.timeout if timeout is None else timeout)
        while True:
            b = self.port.read(1, max(0.01, deadline - time.time()))
            if b[0] == HEAD:
                break
        head = bytes(b)
        cmd_b = self.port.read(1, max(0.01, deadline - time.time()))
        id_b = self.port.read(1, max(0.01, deadline - time.time()))
        cmd, cam_id = cmd_b[0], id_b[0]

        if cmd == CMD_DATA:
            rest = self.port.read(4, max(0.01, deadline - time.time()))
            pack_no = int.from_bytes(rest[0:2], "little")
            pack_len = int.from_bytes(rest[2:4], "little")
            data = self.port.read(pack_len, max(0.01, deadline - time.time())) \
                if pack_len else b""
            chk_b = self.port.read(2, max(0.01, deadline - time.time()))
            raw = head + cmd_b + id_b + rest + data + chk_b
            frame = Frame(cmd, cam_id, b"", pack_no, pack_len, data,
                          int.from_bytes(chk_b, "little"), raw)
            self._log("  <- F 包号=%d 长度=%d 校验=0x%04X" % (pack_no, pack_len, frame.checksum))
            return frame

        payload = bytearray()
        while True:
            c = self.port.read(1, max(0.01, deadline - time.time()))
            if c[0] == TAIL:
                break
            payload.append(c[0])
            if len(payload) > 4096:
                raise PortError("应答帧超长且未收到帧尾 '#'，请检查波特率/接线")
        raw = head + cmd_b + id_b + bytes(payload) + bytes([TAIL])
        frame = Frame(cmd, cam_id, bytes(payload), raw=raw)
        self._log("  <- %-26s %s" % (raw.hex(" ").upper(), _ascii(raw)))
        return frame

    def transact(self, cmd: str, payload: bytes = b"", timeout: float | None = None,
                 cam_id: int | None = None) -> Frame:
        """发命令并读应答，自动识别 '?' 错误应答。"""
        self.send(cmd, payload, cam_id)
        frame = self.read_frame(timeout)
        if frame.is_error:
            raise PortError("摄像头返回错误应答（命令 %s 无法执行）" % cmd)
        if frame.cmd_char != cmd:
            raise PortError("应答命令字不匹配：期望 %s，实到 %s" % (cmd, frame.cmd_char))
        return frame

    # ---------- 配置命令 ----------
    def set_baud(self, rate: int) -> int:
        """设置波特率。成功后摄像头立即以新波特率通讯（含本次应答）。"""
        code = next((k for k, v in BAUD_CODES.items() if v == rate), None)
        if code is None:
            raise PortError("不支持的波特率 %d，可选：%s"
                            % (rate, sorted(BAUD_CODES.values())))
        self.send("I", code.encode())
        # 应答在新波特率下返回，需要重开串口
        self.port.close()
        self.port = reopen(self.port, rate)
        frame = self.read_frame()
        if frame.is_error or frame.cmd_char != "I":
            raise PortError("波特率设置失败：%r" % frame)
        return rate

    def set_quality(self, value: int, as_ascii: bool = False) -> None:
        """压缩率 20~250，数值越大图片越小、质量越差（出厂默认 150/160）。"""
        if not 20 <= value <= 250:
            raise PortError("压缩率需在 20~250 之间")
        payload = ("%d" % value).encode() if as_ascii else bytes([value])
        self.transact("Q", payload)

    def set_id(self, new_id: int, broadcast: bool = False) -> None:
        if not 0 <= new_id <= 33:
            raise PortError("ID 需在 0~33 之间")
        self.transact("D", bytes([new_id]), cam_id=0xFF if broadcast else None)
        self.cam_id = new_id

    def set_led(self, on: bool) -> None:
        self.transact("K", bytes([1 if on else 0]))

    def get_info(self) -> dict:
        self.port.flush_input()
        frame = self.transact("B", b"\x02")
        p = frame.payload
        if len(p) < 5:
            raise PortError("信息帧长度不足：%s" % p.hex(" "))
        return {
            "id": p[0],
            "fw_major": p[1],
            "fw_minor": p[2],
            "fw_name": p[3:5].decode("ascii", "replace"),
            "raw": p.hex(" "),
        }

    def set_osd(self, text: str | None, line: int = 0, font: int = 2,
                x: int = 0, y: int = 0, fg: int = 0x7C, bg: int = 0xFFFE) -> None:
        """OSD 水印；text 为空则关闭。坐标必须偶数，X<=1918，Y<=1278。"""
        if x % 2 or y % 2:
            raise PortError("X/Y 坐标必须为偶数")
        if not text:
            payload = bytes([0]) + bytes(14)      # 关闭 OSD：其余字段全 0
        else:
            body = text.encode("ascii", "replace")[:80]
            payload = (bytes([1, line & 0xFF, font & 0xFF])
                       + struct.pack(">H", x) + struct.pack(">H", y)
                       + struct.pack(">H", fg) + struct.pack(">H", bg)
                       + bytes([len(body)]) + body)
        frame = self.transact("S", payload)
        err = frame.payload[0] if frame.payload else 0
        if err:
            raise PortError("OSD 设置失败，错误码 0x%02X（1行号越界 2字号越界 "
                            "3坐标非偶数 4坐标越界 5文本超长）" % err)

    # ---------- 抓拍 ----------
    def snapshot(self, size_code: str = "5", packet_size: int = 512) -> dict:
        """拍一张图并返回 JPEG 数据与元信息。"""
        if size_code not in SIZES:
            raise PortError("尺寸代码需为 '1'~'5'")
        if not 16 <= packet_size <= 1024:
            raise PortError("分包大小需在 16~1024 之间（建议 512）")

        self.port.flush_input()
        t0 = time.time()
        self.transact("H", size_code.encode() + struct.pack("<H", packet_size))

        # 等 R 帧（拍图耗时 Tp，短则 200ms，切换分辨率时可能 5~6s）
        info = self.read_frame(self.snap_timeout)
        if info.cmd_char != "R":
            raise PortError("未收到图片信息帧 R，实到 %r" % info)
        total = int.from_bytes(info.payload[0:4], "little")
        packs = int.from_bytes(info.payload[4:6], "little")
        w, h = SIZES[size_code]
        self._log("  图片 %dx%d，共 %d 字节 / %d 包（拍图耗时 %.2fs）"
                  % (w, h, total, packs, time.time() - t0))

        buf = bytearray()
        bad_crc = 0
        for i in range(1, packs + 1):
            data, ok = self._fetch_packet(i)
            if not ok:
                bad_crc += 1
            buf += data
            if i % 10 == 0 or i == packs:
                self._log("  已收 %d/%d 包（%.1f%%）" % (i, packs, 100.0 * i / packs))

        jpeg = bytes(buf)[:total] if total and total < len(buf) else bytes(buf)
        cost = time.time() - t0
        self._log("  完成：%d 字节，耗时 %.2fs，平均 %.1f KB/s，校验失败 %d 包"
                  % (len(jpeg), cost, len(jpeg) / 1024.0 / max(cost, 0.001), bad_crc))
        return {
            "jpeg": jpeg, "width": w, "height": h, "total": total, "packs": packs,
            "size_code": size_code, "packet_size": packet_size, "cost": cost,
            "bad_crc": bad_crc,
        }

    def _fetch_packet(self, pack_no: int) -> tuple[bytes, bool]:
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                self.transact("E", struct.pack("<H", pack_no))
                frame = self.read_frame(self.timeout)
                if not frame.is_data:
                    raise PortError("期望数据包 F，实到 %r" % frame)
                if frame.pack_no != pack_no:
                    raise PortError("包号不匹配：期望 %d，实到 %d" % (pack_no, frame.pack_no))
                ok = verify_checksum(frame)
                if not ok and attempt < self.retries:
                    self._log("    第 %d 包校验失败，重试（%d/%d）"
                              % (pack_no, attempt, self.retries))
                    continue
                return frame.data, ok
            except (TimeoutError_, PortError) as exc:
                last_err = exc
                self._log("    第 %d 包取包失败（%d/%d）：%s"
                          % (pack_no, attempt, self.retries, exc))
        raise PortError("第 %d 包重试 %d 次仍失败：%s" % (pack_no, self.retries, last_err))


def verify_checksum(frame: Frame) -> bool:
    """校验和 = 'U' 起至校验和之前所有字节累加和（小端）。"""
    body = frame.raw[:-2]
    return (sum(body) & 0xFFFF) == frame.checksum


def _ascii(raw: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in raw)


def reopen(port, baud: int):
    """以新波特率重开同一个串口。"""
    path, timeout = port.path, port.timeout
    try:
        port.close()
    except Exception:  # noqa: BLE001
        pass
    return open_port(path, baud, timeout)


# --------------------------------------------------------------------------- #
#  结果落盘 + 网页预览
# --------------------------------------------------------------------------- #
def save_jpeg(jpeg: bytes, outdir: str, cam_id: int) -> str:
    os.makedirs(outdir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(outdir, "cam%s_%s.jpg" % (cam_id, ts))
    n = 1
    while os.path.exists(path):
        path = os.path.join(outdir, "cam%s_%s_%d.jpg" % (cam_id, ts, n))
        n += 1
    with open(path, "wb") as fp:
        fp.write(jpeg)
    return path


def check_jpeg(jpeg: bytes) -> str:
    tips = []
    if not jpeg.startswith(JPEG_SOI):
        tips.append("缺少 JPEG 头 FFD8")
    if not jpeg.endswith(JPEG_EOI):
        tips.append("缺少 JPEG 尾 FFD9（最后一包可能未收全）")
    return "；".join(tips) if tips else "JPEG 结构完整"


def build_preview(outdir: str, shots: list, meta: dict) -> str:
    """生成内嵌 base64 的网页，直接在浏览器里看照片。"""
    cards = []
    for i, s in enumerate(shots, 1):
        b64 = base64.b64encode(s["jpeg"]).decode()
        note = check_jpeg(s["jpeg"])
        cards.append(
            '<figure class="card">'
            '<div class="ph"><img src="data:image/jpeg;base64,%s" alt="shot%d"></div>'
            '<figcaption><b>#%d</b> %dx%d · %d 字节 · %d 包 · %.2fs<br>'
            '<span class="dim">%s · %s</span></figcaption></figure>'
            % (b64, i, i, s["width"], s["height"], len(s["jpeg"]), s["packs"],
               s["cost"], _html.escape(note), _html.escape(s["path"]))
        )
    rows = "".join(
        "<tr><th>%s</th><td>%s</td></tr>" % (_html.escape(k), _html.escape(str(v)))
        for k, v in meta.items()
    )
    tpl = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>串口摄像头抓拍预览</title><style>
body{margin:0;padding:24px;background:#0f172a;color:#e2e8f0;font:14px/1.6 -apple-system,"PingFang SC",sans-serif}
h1{font-size:20px;margin:0 0 4px}.dim{color:#94a3b8;font-size:12px}
table{border-collapse:collapse;margin:12px 0 24px;font-size:13px}
th,td{border:1px solid #334155;padding:4px 10px;text-align:left}th{background:#1e293b;color:#94a3b8;font-weight:500}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}
.card{margin:0;background:#1e293b;border:1px solid #334155;border-radius:10px;overflow:hidden}
.ph{background:#000;display:flex;align-items:center;justify-content:center;min-height:200px}
img{max-width:100%;display:block}
figcaption{padding:10px 12px;font-size:13px}
</style></head><body>
<h1>串口摄像头抓拍预览</h1>
<div class="dim">{{TIME}}</div>
<table>{{ROWS}}</table>
<div class="grid">{{CARDS}}</div>
</body></html>"""
    doc = (tpl.replace("{{TIME}}", time.strftime("%Y-%m-%d %H:%M:%S"))
              .replace("{{ROWS}}", rows).replace("{{CARDS}}", "".join(cards)))

    path = os.path.join(outdir, "preview.html")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(doc)
    return path


def system_open(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.startfile(path)  # noqa: S606  (Windows)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
#  自动扫描：波特率 × ID（用「查询摄像头信息 B」探测，只读无副作用）
# --------------------------------------------------------------------------- #
DEFAULT_SCAN_RATES = [115200, 921600, 57600, 38400, 19200, 9600, 460800, 230400, 14400, 2400]
DEFAULT_SCAN_IDS = [0, 1, 0xFF, 2, 3]


def scan_camera(path: str, rates=None, ids=None, wait: float = 0.8,
                verbose: bool = True, stop_first: bool = False,
                rs485_dir: str | None = None) -> list[tuple[int, int, Frame]]:
    """遍历波特率×ID 发 B 命令，返回 [(波特率, ID, 应答帧), ...]。"""
    rates = rates or DEFAULT_SCAN_RATES
    ids = ids or DEFAULT_SCAN_IDS
    hits = []
    for rate in rates:
        try:
            port = open_port(path, rate, wait)
        except (PortError, OSError) as exc:
            if verbose:
                print("  %-7d 无法打开（%s）" % (rate, exc))
            continue
        try:
            for cid in ids:
                cam = SerialCamera(port, cam_id=cid, timeout=wait, verbose=False,
                                  rs485_dir=rs485_dir)
                cam.set_rx()
                try:
                    port.flush_input()
                    cam.send("B", b"\x02")
                    frame = cam.read_frame(wait)
                except (TimeoutError_, PortError, OSError):
                    if verbose:
                        print("  %-7d ID=%-3d 无应答" % (rate, cid))
                    continue
                if verbose:
                    print("  %-7d ID=%-3d ★ 有应答：cmd=%s payload=%s"
                          % (rate, cid, frame.cmd_char, frame.payload.hex(" ")))
                hits.append((rate, cid, frame))
                if stop_first:
                    return hits
        finally:
            port.close()
    return hits


def scan_once(path: str, wait: float = 0.8, rs485_dir: str | None = None) -> tuple[int, int] | None:
    """返回第一个命中的 (波特率, ID)，静默扫描。"""
    hits = scan_camera(path, wait=wait, verbose=False, stop_first=True, rs485_dir=rs485_dir)
    return (hits[0][0], hits[0][1]) if hits else None


def do_loopback(path: str, rates: list[int], rounds: int = 3) -> int:
    """回环自检：短接转换器的 TX 与 RX，发什么应收到什么。
    用途：① 确认串口号/转换器可用 ② 确认该芯片在 macOS 下是否真能跑某个波特率
    （CH340 等常「打开成功但实际速率不对」，属静默失败，只有回环能测出来）。"""
    print("回环自检 %s" % path)
    print("正确接法：短接转换器 TTL 侧的 TXD 与 RXD（RS232 线则短接 DB9 的 2、3 脚）。")
    print("注意：RS485 模块短接 A、B 无效——差分短路后接收器输出恒定，永远等不到起始位。")
    summary = []
    for baud in rates:
        try:
            port = open_port(path, baud, 0.5)
        except (PortError, OSError) as exc:
            print("  %-7d 打开失败：%s" % (baud, exc))
            summary.append((baud, 0, rounds))
            continue
        ok = 0
        samples = []
        try:
            for _ in range(rounds):
                msg = bytes([HEAD, ord("B"), 0x00, 0x02, TAIL])
                port.flush_input()
                port.write(msg)
                try:
                    got = port.read(len(msg), 0.5)
                except (TimeoutError_, OSError):
                    got = b""
                samples.append(got)
                if got == msg:
                    ok += 1
        finally:
            port.close()
        first = next((s for s in samples if s), b"")
        print("  %-7d %d/%d 成功 %s" % (baud, ok, rounds,
                                        "OK" if ok == rounds else "不通" if ok == 0 else "不稳定"))
        print("        发 %s / 收 %s" % (bytes([HEAD, ord("B"), 0x00, 0x02, TAIL]).hex(" "),
                                        first.hex(" ") if first else "(空)"))
        summary.append((baud, ok, rounds))
    print("\n结论：")
    good = [b for b, ok, n in summary if ok == n]
    bad = [b for b, ok, n in summary if ok == 0]
    if good:
        print("  该串口可正常收发的波特率：%s" % ", ".join(str(x) for x in good))
    if bad and good:
        print("  该串口跑不了的波特率：%s —— 芯片/驱动不支持（CH340 在 macOS 常见），"
              "若摄像头正处在这个速率上，就必须换 FTDI/CH343/CP210x 转换器。"
              % ", ".join(str(x) for x in bad))
    if not good:
        print("  所有波特率都不通：串口号选错 / 转换器未插好或损坏 / "
              "RS485 模块发送态不回环（属正常，请换 RS232 口或摘掉 485 模块再测）")
    else:
        print("  串口与转换器本身正常，问题在摄像头侧：供电、TX/RX 是否交叉、GND 共地、电平匹配")
    return 0 if good else 1


def read_all(port, seconds: float) -> bytes:
    """在 seconds 秒内把串口上出现的字节全部收下来，不做帧解析——乱码同样是有用的信息。"""
    buf = bytearray()
    end = time.time() + seconds
    while time.time() < end:
        try:
            chunk = port.read(256, min(0.05, max(0.01, end - time.time())))
        except (TimeoutError_, OSError):
            continue
        if chunk:
            buf += chunk
        else:
            time.sleep(0.005)
    return bytes(buf)


def do_hold(path: str, baud: int, rs485_dir: str | None, seconds: float = 30.0) -> int:
    """把 RTS 钉在某一电平并保持若干秒，期间一个字节都不发。

    用万用表对比 high / low 两次的 A-B 电压，即可判定：
    RTS 有没有真的驱动到模块的 DE（macOS 的 CH340 驱动常常静默忽略 TIOCMSET），
    以及总线空闲电平到底由谁决定（主机模块还是摄像头）。
    """
    if not rs485_dir or rs485_dir == "auto":
        print("hold 需要明确指定 --rts high 或 --rts low")
        return 2
    port = open_port(path, baud, 0.5)
    ok = port.set_rts(rs485_dir == "high")
    print("RTS 设为 %s：%s" % (rs485_dir,
                              "调用成功" if ok else "调用失败（驱动不支持 modem 控制位）"))
    fd = getattr(port, "fd", None)
    if fd is not None:
        try:
            import fcntl

            st = struct.unpack("I", fcntl.ioctl(fd, _TIOCMGET, struct.pack("I", 0)))[0]
            print("  TIOCMGET 回读：RTS=%d DTR=%d（能反映 ioctl 是否被驱动真的采纳）"
                  % (bool(st & _TIOCM_RTS), bool(st & _TIOCM_DTR)))
        except Exception as exc:  # noqa: BLE001
            print("  TIOCMGET 回读失败：%s" % exc)
    print("保持 %.0f 秒不发任何数据 —— 现在请量 A-B 电压..." % seconds)
    try:
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.2)
    finally:
        port.close()
    print("\n请把这次读到的值记为 V(%s)。" % rs485_dir)
    if not ok:
        print("注意：驱动拒绝设置 RTS → 该模块若是「RTS 换向型」，在本机将无法收发，"
              "必须改用自动换向模块，或用万用表确认 RTS 引脚实际电平。")
    return 0


def do_raw(path: str, baud: int, hexstr: str, seconds: float = 1.5,
           rs485_dir: str | None = None) -> int:
    """把十六进制字节原样发到总线，并原样打印返回。

    用于对接协议文档里给定的命令：绕开工具内置协议的假设，
    避免「协议不对导致摄像头根本不认识命令、自然不应答」的误判。
    """
    clean = "".join(c for c in hexstr if c in "0123456789abcdefABCDEF")
    try:
        data = bytes.fromhex(clean)
    except ValueError:
        print("十六进制解析失败（hex 字符数应为偶数），收到：%r" % hexstr)
        return 2
    if not data:
        print("没有解析出有效字节，示例：--hex '55 01 00 00 00 AA'")
        return 2

    port = open_port(path, baud, 0.5)
    print("发送 %d 字节：%s" % (len(data), data.hex(" ").upper()))
    try:
        if rs485_dir and rs485_dir != "auto":
            tx_level = rs485_dir == "high"
            port.set_rts(tx_level)
            time.sleep(0.001)
            try:
                port.write(data)
                port.drain()
                time.sleep(max(0.0002, 20.0 / baud))
            finally:
                port.set_rts(not tx_level)
        else:
            port.write(data)
            port.drain()
        got = read_all(port, seconds)
    finally:
        port.close()
    print("返回 %d 字节：%s" % (len(got), got.hex(" ").upper() if got else "(无)"))
    if got:
        print("  ASCII：|%s|" % _ascii(got))
    return 0 if got else 1


def do_ping(path: str, baud: int, cam_id: int, seconds: float = 10.0,
            interval: float = 0.08, rs485_dir: str | None = None,
            dense: bool = False) -> int:
    """以固定波特率持续发 B 命令：配合万用表/示波器观察 A/B 有无电平跳变，
    判断「主机到底有没有把字节送到总线」——这是 485 分段排查时区分
    「模块/接线问题」与「摄像头问题」的硬证据。"""
    port = open_port(path, baud, 0.5 if dense else max(0.05, interval))
    cam = SerialCamera(port, cam_id=cam_id, timeout=0.5 if dense else max(0.05, interval),
                       verbose=False, rs485_dir=rs485_dir)
    cam.set_rx()
    print("持续探测 %s @ %d，ID=%d，共 %.0f 秒%s"
          % (path, baud, cam_id, seconds,
             "（全速连发模式，万用表量 A-B 会看到明显偏移）" if dense
             else "（期间可用万用表量 A-B 电压）"))
    sent = recv = errs = 0
    last = b""
    end = time.time() + seconds
    try:
        while time.time() < end:
            try:
                cam.send("B", b"\x02")
                sent += 1
                if dense:          # 全速连发：不读回、不等待，把总线占满
                    continue
                # 关键：原始字节全收。合法帧之外也要看——乱码同样是有价值的信息，
                # 它说明数据真的回来了，只是波特率/极性/换向延时对不上。
                raw = read_all(port, max(0.05, interval))
            except (PortError, OSError) as exc:
                errs += 1
                if errs <= 3:
                    print("  ✗ 发送/接收异常：%s: %s" % (type(exc).__name__, exc))
                continue
            if raw:
                recv += 1
                last = raw
                print("  ★ 收到 %d 字节：%s  |%s|"
                      % (len(raw), raw.hex(" ").upper(), _ascii(raw)))
    finally:
        port.close()
    print("\n发送 %d 次，有数据的 %d 次，异常 %d 次，最后一次：%s"
          % (sent, recv, errs, last.hex(" ").upper() if last else "(无)"))
    if dense:
        print("全速连发模式只发不收，接收统计无意义——请对比「未发时」与「发送中」的 A-B 电压。")
        return 0
    if recv:
        print("判定：总线上有数据回来，但解不出合法帧 → 属于「收到了但不对」，"
              "查波特率偏差、A/B 极性、自动换向模块的切换延时（会吃掉开头几个字节）。")
    else:
        print("判定：总线上一个字节都没有。若此时万用表量到 A-B 有跳变 → 主机在发、摄像头没回"
              "（查摄像头供电/TTL 口/是否真是 485 版）；若 A-B 完全无跳变 → 字节没上总线"
              "（查模块接线/换向/模块本身）。")
    return 0 if recv else 1


def do_sniff(path: str, rates: list[int], seconds: float) -> int:
    """纯监听：在多个波特率下各听一段时间，打印摄像头/总线上的任何原始字节。"""
    for rate in rates:
        try:
            port = open_port(path, rate, 1.0)
        except (PortError, OSError) as exc:
            print("  %-7d 打开失败：%s" % (rate, exc))
            continue
        buf = bytearray()
        end = time.time() + seconds
        try:
            while time.time() < end:
                try:
                    buf += port.read(1, min(0.2, max(0.01, end - time.time())))
                except (TimeoutError_, OSError):
                    continue
        finally:
            port.close()
        if buf:
            text = "".join(chr(c) if 32 <= c < 127 else "." for c in buf[:64])
            print("  %-7d 收到 %d 字节：%s  |%s|"
                  % (rate, len(buf), bytes(buf[:64]).hex(" "), text))
        else:
            print("  %-7d 静默（%d 秒内无任何数据）" % (rate, int(seconds)))
    print("\n说明：全部静默属正常（摄像头只在收到命令后才应答）；"
          "某波特率下出现可辨识文本/55 开头帧，说明该波特率就是当前值。")
    return 0


def list_ports() -> list[str]:
    pats = ["/dev/cu.*", "/dev/tty.*", "/dev/ttyUSB*", "/dev/ttyS*", "/dev/ttyAMA*", "/dev/ttyACM*"]
    found = []
    for p in pats:
        found.extend(sorted(glob.glob(p)))
    # mac 上 /dev/tty.* 里包含大量蓝牙/系统口，优先推荐 cu.usb* / usbserial / usbmodem
    prefer = [x for x in found if any(k in x for k in ("usbserial", "usbmodem", "USB", "ttyACM", "ttyAMA"))]
    rest = [x for x in found if x not in prefer]
    return prefer + rest


# --------------------------------------------------------------------------- #
#  自检（不接硬件即可验证解析逻辑）
# --------------------------------------------------------------------------- #
class _FakePort:
    """用于自检的假串口：write(E 取包命令) 时会把对应应答+数据包重新追加到输入流，
    模拟真实摄像头「重发同一包」的行为。"""

    def __init__(self, stream: bytes, on_write=None):
        self.buf = bytearray(stream)
        self.pos = 0
        self.on_write = on_write
        self.path = "fake://"
        self.timeout = 1.0
        self.written = []
        self.baud = 921600

    def read(self, n, timeout=None):
        if self.pos + n > len(self.buf):
            raise TimeoutError_("假端口数据耗尽（剩余 %d 字节，需要 %d）"
                                % (len(self.buf) - self.pos, n))
        out = bytes(self.buf[self.pos:self.pos + n])
        self.pos += n
        return out

    def write(self, data):
        self.written.append(bytes(data))
        if self.on_write:
            self.on_write(self, bytes(data))
        return len(data)

    def flush_input(self):
        pass

    def close(self):
        pass


def _mk_frame(cmd: str, cam_id: int, payload: bytes) -> bytes:
    return SerialCamera.build_cmd(cmd, cam_id, payload)


def _mk_data_frame(cam_id: int, pack_no: int, data: bytes, corrupt: bool = False) -> bytes:
    body = (bytes([HEAD, CMD_DATA, cam_id])
            + struct.pack("<H", pack_no) + struct.pack("<H", len(data)) + data)
    chk = sum(body) & 0xFFFF
    if corrupt:
        chk = (chk + 1) & 0xFFFF
    return body + struct.pack("<H", chk)


def selftest() -> int:
    print("自检：不接硬件，验证命令组帧 / 帧解析 / 校验和 / 多包拼图")
    ok = 0
    fail = []

    # 1. 命令组帧
    raw = SerialCamera.build_cmd("H", 1, b"2" + struct.pack("<H", 512))
    assert raw == bytes.fromhex("55480132000223"), raw.hex()
    print("  [OK] 拍图命令与文档示例一致 55 48 01 32 00 02 23")
    ok += 1

    # 2. 构造一次完整抓拍字节流：H 应答 + R 帧 +（E 应答 + F 数据帧）×N
    payload = (JPEG_SOI + b"\xff\xe0\x00\x10JFIF\x00" + bytes(range(256)) * 4 + JPEG_EOI)
    pack = 512
    packs = (len(payload) + pack - 1) // pack
    stream = _mk_frame("H", 0, b"")
    stream += _mk_frame("R", 0, struct.pack("<I", len(payload)) + struct.pack("<H", packs))
    chunks = [payload[i * pack:(i + 1) * pack] for i in range(packs)]
    corrupt = {2}   # 第 2 包始终校验错，用于验证「重试后仍失败则告警但保留数据」

    def on_write(port: _FakePort, data: bytes):
        if len(data) >= 5 and data[1] == ord("E"):
            no = int.from_bytes(data[3:5], "little")
            port.buf += _mk_frame("E", 0, b"")
            port.buf += _mk_data_frame(0, no, chunks[no - 1], corrupt=(no in corrupt))

    cam = SerialCamera(_FakePort(stream, on_write), cam_id=0, verbose=False, retries=2)
    shot = cam.snapshot(size_code="5", packet_size=pack)
    if shot["jpeg"] == payload:
        print("  [OK] %d 包拼图与原始数据完全一致（%d 字节）" % (packs, len(payload)))
        ok += 1
    else:
        fail.append("拼图结果不一致")
    if shot["packs"] == packs and shot["total"] == len(payload):
        print("  [OK] R 帧解析正确：总长 %d / 包数 %d" % (shot["total"], shot["packs"]))
        ok += 1
    else:
        fail.append("R 帧解析错误")
    if shot["bad_crc"] == 1:
        print("  [OK] 校验和错误被识别（第 2 包）")
        ok += 1
    else:
        fail.append("校验和检测失效")

    # 3. 错误应答识别
    cam2 = SerialCamera(_FakePort(_mk_frame("?", 0, b"")), cam_id=0, verbose=False)
    try:
        cam2.transact("Q", b"\x96")
        fail.append("错误应答未抛异常")
    except PortError:
        print("  [OK] '?' 错误应答正确识别为失败")
        ok += 1

    # 4. 波特率 / 尺寸 / 压缩率参数映射
    if BAUD_CODES["9"] == 921600 and SIZES["5"] == (1280, 960):
        print("  [OK] 130 万像素(1280x960) + 921600 波特率映射正确")
        ok += 1
    else:
        fail.append("参数映射错误")

    # 5. JPEG 完整性检查
    if check_jpeg(payload) == "JPEG 结构完整" and check_jpeg(b"\x00\x01") != "JPEG 结构完整":
        print("  [OK] JPEG 头尾检查正常")
        ok += 1
    else:
        fail.append("JPEG 检查异常")

    print("\n自检结果：%d 项通过，%d 项失败" % (ok, len(fail)))
    for f in fail:
        print("  [FAIL] %s" % f)
    return 0 if not fail else 1


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="serial_camera.py",
        description="智景科技 RS232/RS485 串口摄像头（A 版协议）配置与抓拍工具",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", "-p", help="串口设备，如 /dev/cu.usbserial-1420（macOS 推荐 cu.*）")
    ap.add_argument("--baud", "-b", type=int, default=921600,
                    help="波特率，默认 921600（130万型号）。不确定可先试 115200")
    ap.add_argument("--id", type=int, default=0,
                    help="摄像头 ID，232/TTL 默认 0；RS485 多机 1~33；0xFF 广播")
    ap.add_argument("--timeout", type=float, default=3.0, help="单帧超时秒数，默认 3")
    ap.add_argument("--snap-timeout", type=float, default=15.0,
                    help="等待图片信息帧 R 的超时秒数，默认 15")
    ap.add_argument("--retries", type=int, default=3, help="单包取包失败重试次数，默认 3")
    ap.add_argument("--quiet", "-q", action="store_true", help="不打印逐帧日志")
    ap.add_argument("--rts", choices=["auto", "high", "low"], default="auto",
                    help="RS485 收发换向方式：auto=自动换向模块（默认，不管 RTS）；\n"
                         "high/low=RTS 换向型模块，发送时把 RTS 拉高/拉低，发完立刻切回接收")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出本机可用串口")

    sub.add_parser("info", help="读取摄像头 ID / 固件版本 / FW 名称（B 命令）")

    p = sub.add_parser("loopback", help="串口回环自检（短接 TX-RX，验证串口与芯片真正支持的波特率）")
    p.add_argument("--rounds", type=int, default=3, help="每个波特率测试轮数，默认 3")
    p.add_argument("--rates", default="921600,115200,57600,9600", help="要测的波特率，逗号分隔")

    p = sub.add_parser("ping", help="固定波特率持续探测（配合万用表看 A/B 有无电平跳变）")
    p.add_argument("--seconds", type=float, default=10.0, help="持续探测秒数，默认 10")
    p.add_argument("--interval", type=float, default=0.08, help="每次探测间隔秒数，默认 0.08")
    p.add_argument("--dense", action="store_true",
                   help="全速连续发送（不读回），把总线占满，便于万用表测到稳定的电平偏移")

    p = sub.add_parser("raw", help="按协议文档原样发送十六进制字节并打印原始返回")
    p.add_argument("--hex", required=True, help="要发送的字节，如 '55 01 00 00 00 AA'")
    p.add_argument("--seconds", type=float, default=1.5, help="等待返回的秒数，默认 1.5")

    p = sub.add_parser("hold", help="把 RTS 钉在高/低电平保持若干秒（配合万用表判断换向是否生效）")
    p.add_argument("--seconds", type=float, default=30.0, help="保持秒数，默认 30")

    p = sub.add_parser("sniff", help="纯监听：在多个波特率下听一段时间，看摄像头/总线有无数据")
    p.add_argument("--seconds", type=float, default=3.0, help="每个波特率监听秒数，默认 3")
    p.add_argument("--rates", default="921600,115200,57600,38400,19200,9600",
                   help="要监听的波特率，逗号分隔")

    p = sub.add_parser("scan", help="自动扫描波特率与 ID（用「查信息 B」探测，只读无副作用）")
    p.add_argument("--rates", default="", help="要试的波特率，逗号分隔，默认按常用顺序全试")
    p.add_argument("--ids", default="0,1,255,2,3", help="要试的 ID，逗号分隔，255=广播")
    p.add_argument("--wait", type=float, default=0.8, help="每个组合等待应答的秒数，默认 0.8")

    p = sub.add_parser("snap", help="抓拍照片并生成网页预览（H/E/F 命令）")
    p.add_argument("--size", default="5", choices=list(SIZES),
                   help="分辨率：1=160x128 2=320x240 3=640x480 4=1280x720 5=1280x960(默认,130万)")
    p.add_argument("--packet", type=int, default=512, help="分包大小 16~1024，默认 512")
    p.add_argument("--count", "-n", type=int, default=1, help="连拍张数，默认 1")
    p.add_argument("--interval", type=float, default=1.0, help="连拍间隔秒数，默认 1")
    p.add_argument("--out", "-o", default="photos", help="输出目录，默认 ./photos")
    p.add_argument("--no-open", action="store_true", help="不自动打开预览网页")
    p.add_argument("--quality", type=int, default=None, help="抓拍前先设置压缩率 20~250")
    p.add_argument("--auto", action="store_true",
                   help="抓拍前先自动扫描波特率/ID（不知道摄像头当前参数时用）")

    p = sub.add_parser("baud", help="设置摄像头波特率（I 命令，设置后自动以新波特率重连）")
    p.add_argument("rate", type=int, choices=sorted(BAUD_CODES.values()))

    p = sub.add_parser("quality", help="设置压缩率（Q 命令，越大图越小越糊）")
    p.add_argument("value", type=int)
    p.add_argument("--ascii", action="store_true",
                   help="按十进制 ASCII 发送（文档示例含糊，两种口径都提供）")

    p = sub.add_parser("setid", help="修改摄像头 ID（D 命令）")
    p.add_argument("new_id", type=int)
    p.add_argument("--broadcast", action="store_true", help="对总线上所有摄像头广播改 ID")

    p = sub.add_parser("led", help="补光灯开关（K 命令，断电重启后恢复默认开启）")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("osd", help="OSD 水印（S 命令，仅英文 ASCII，最多 80 字符）")
    p.add_argument("--text", default="", help="水印文字；留空表示关闭 OSD")
    p.add_argument("--line", type=int, default=0, help="行号 0~2，默认 0")
    p.add_argument("--x", type=int, default=0, help="X 坐标，偶数，0~1918")
    p.add_argument("--y", type=int, default=0, help="Y 坐标，偶数，0~1278；多行需按字号偏移")

    sub.add_parser("selftest", help="不接硬件自检（验证帧解析/校验/拼图逻辑）")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 1
    rts_mode = args.rts if args.rts != "auto" else None

    if args.cmd == "list":
        ports = list_ports()
        if not ports:
            print("未发现串口设备，请确认 USB 转串口已插入且驱动已安装")
            return 1
        print("发现串口（推荐用前面的 cu.* / usb* 设备）：")
        for x in ports:
            print("  " + x)
        return 0

    if args.cmd == "selftest":
        return selftest()

    if not args.port:
        print("错误：请用 --port 指定串口，例如：\n"
              "  python3 %s --port /dev/cu.usbserial-1420 snap\n"
              "可用串口列表：python3 %s list" % (os.path.basename(__file__), os.path.basename(__file__)))
        return 1

    if args.cmd == "loopback":
        rates = [int(x) for x in args.rates.split(",") if x.strip()]
        return do_loopback(args.port, rates, args.rounds)

    if args.cmd == "ping":
        return do_ping(args.port, args.baud, args.id, args.seconds, args.interval,
                       rts_mode, args.dense)

    if args.cmd == "hold":
        return do_hold(args.port, args.baud, rts_mode, args.seconds)

    if args.cmd == "raw":
        return do_raw(args.port, args.baud, args.hex, args.seconds, rts_mode)

    if args.cmd == "sniff":
        rates = [int(x) for x in args.rates.split(",") if x.strip()]
        print("监听 %s，每个波特率 %.0f 秒（期间可给摄像头重新上电）..." % (args.port, args.seconds))
        return do_sniff(args.port, rates, args.seconds)

    if args.cmd == "scan":
        rates = [int(x) for x in args.rates.split(",") if x.strip()] or None
        ids = [int(x) for x in args.ids.split(",") if x.strip()] or None
        print("扫描 %s（波特率 × ID），每个组合等待 %.1fs，请稍候..." % (args.port, args.wait))
        hits = scan_camera(args.port, rates, ids, args.wait, rs485_dir=rts_mode)
        if not hits:
            print("\n全部组合均无应答。请检查：")
            print("  ① 摄像头是否供电（130 万型号 5V 需 200mA 以上，拍照瞬间更大）且上电满 2~3s")
            print("  ② TX/RX 是否交叉（摄像头 TX 接转换器 RX，RX 接 TX），GND 是否共地")
            print("  ③ 电平是否匹配（摄像头 RS232 口接 RS232 转换器；TTL 口不能直接接 RS232）")
            print("  ④ 若经 RS485：A/B 是否接反（把两根线对调后再扫一次即可验证）")
            print("  ⑤ 若转换器是 RTS 换向型而非自动换向：加 --rts high 或 --rts low 再扫")
            print("  ⑥ 转换器本身是否正常：短接其 TTL 侧 TXD 与 RXD（RS232 线为 DB9 的 2、3 脚）\n"
                  "     做回环自检；注意 RS485 模块短接 A、B 是无效的（差分短路，收不到起始位）")
            return 1
        print("\n命中 %d 个组合（按可靠性排序）：" % len(hits))
        for rate, cid, frame in hits:
            extra = ""
            if frame.cmd_char == "B" and len(frame.payload) >= 5:
                extra = " → ID=%d 固件 v%d.%d FW=%s" % (
                    frame.payload[0], frame.payload[1], frame.payload[2],
                    frame.payload[3:5].decode("ascii", "replace"))
            print("  波特率 %-7d ID=%-3d%s" % (rate, cid, extra))
        rate, cid, _ = hits[0]
        print("\n建议直接用：")
        print("  python3 %s --port %s --baud %d --id %d snap"
              % (os.path.basename(__file__), args.port, rate, cid))
        print("或让脚本自己找：")
        print("  python3 %s --port %s snap --auto" % (os.path.basename(__file__), args.port))
        return 0

    verbose = not args.quiet
    port = None
    cam = None
    try:
        port = open_port(args.port, args.baud, args.timeout)
        cam = SerialCamera(port, cam_id=args.id, timeout=args.timeout,
                           snap_timeout=args.snap_timeout, retries=args.retries,
                           verbose=verbose, rs485_dir=rts_mode)
        cam.set_rx()
        if rts_mode and not cam._rts_ok:
            print("注意：该串口驱动不支持 RTS 控制，--rts 无效（请换自动换向的 RS485 模块）")
        if args.cmd == "info":
            info = cam.get_info()
            print("摄像头信息：ID=%d  固件 v%d.%d  FW=%s  原始=%s"
                  % (info["id"], info["fw_major"], info["fw_minor"], info["fw_name"], info["raw"]))
            return 0

        if args.cmd == "baud":
            cam.set_baud(args.rate)
            print("波特率已切换为 %d（摄像头掉电后保持）" % args.rate)
            return 0

        if args.cmd == "quality":
            cam.set_quality(args.value, as_ascii=args.ascii)
            print("压缩率已设置为 %d" % args.value)
            return 0

        if args.cmd == "setid":
            cam.set_id(args.new_id, broadcast=args.broadcast)
            print("ID 已改为 %d" % args.new_id)
            return 0

        if args.cmd == "led":
            cam.set_led(args.state == "on")
            print("补光灯已%s" % ("开启" if args.state == "on" else "关闭"))
            return 0

        if args.cmd == "osd":
            cam.set_osd(args.text or None, line=args.line, x=args.x, y=args.y)
            print("OSD 已%s" % ("设置为：%s" % args.text if args.text else "关闭"))
            return 0

        if args.cmd == "snap":
            outdir = os.path.abspath(args.out)
            if args.auto:
                print("自动扫描波特率与 ID（每个组合 0.8s）...")
                hit = scan_once(args.port, wait=0.8, rs485_dir=rts_mode)
                if not hit:
                    raise PortError("未发现摄像头，请先跑 scan 子命令排查接线与供电")
                rate, args.id = hit[0], hit[1]
                print("  命中：波特率 %d / ID %d" % (rate, args.id))
                if rate != args.baud:
                    args.baud = rate
                    port.close()
                    port = open_port(args.port, args.baud, args.timeout)
                cam = SerialCamera(port, cam_id=args.id, timeout=args.timeout,
                                   snap_timeout=args.snap_timeout, retries=args.retries,
                                   verbose=verbose)
            if args.quality is not None:
                cam.set_quality(args.quality)
            shots = []
            for i in range(1, args.count + 1):
                print("[%d/%d] 抓拍中..." % (i, args.count))
                s = cam.snapshot(size_code=args.size, packet_size=args.packet)
                s["path"] = save_jpeg(s["jpeg"], outdir, args.id)
                print("  已保存：%s（%s）" % (s["path"], check_jpeg(s["jpeg"])))
                shots.append(s)
                if i < args.count:
                    time.sleep(max(0.0, args.interval))
            meta = {
                "串口": args.port, "波特率": args.baud, "摄像头 ID": args.id,
                "分辨率": "%dx%d" % SIZES[args.size], "分包大小": args.packet,
                "压缩率": args.quality if args.quality is not None else "未修改（沿用摄像头当前值）",
                "张数": len(shots),
                "输出目录": outdir,
            }
            page = build_preview(outdir, shots, meta)
            print("\n预览网页：%s" % page)
            if not args.no_open:
                system_open(page)
                print("已在默认浏览器中打开；也可直接双击打开上面的 html / jpg。")
            return 0
    except (PortError, TimeoutError_, OSError) as exc:
        msg = str(exc)
        print("\n[失败] %s" % msg)
        if "Resource busy" in msg or "Errno 16" in msg:
            print("串口被其它程序占用：请先关闭串口调试助手/未退出的脚本进程再重试")
        else:
            print("排查：① 波特率是否正确 ② 串口号是否选对（macOS 用 /dev/cu.*）"
                  " ③ 摄像头上电是否满 2~3s ④ ID 是否为 0（232/TTL 默认为 0）")
        return 2
    finally:
        seen = set()
        for p in (port, getattr(cam, "port", None)):
            if p is None or id(p) in seen:
                continue
            seen.add(id(p))
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
