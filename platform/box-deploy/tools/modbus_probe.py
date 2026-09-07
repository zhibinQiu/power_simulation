#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS485 / Modbus RTU 现场排查工具（纯 Python3 标准库，无需 pyserial）——给能碳一体机盒子用。

解决的问题：现场插上一个 RS485 设备（如可变电压电源 / 电表 / 仪表）后，不知道
① 它落在哪个串口（/dev/ttyUSB? /dev/ttyS? /dev/ttyACM?）
② 波特率/校验是多少
③ 从站地址（slaveId）是几
④ 哪个寄存器是电压/电流/功率，数据怎么解析（float32? int16? 字节序? 量程 scale?）

用法（在盒子或本机执行，串口设备需有读写权限，一般 root）：
    python3 modbus_probe.py list                       # 列出所有串口 + USB 拓扑（看出哪个口是新插的）
    python3 modbus_probe.py scan                       # 全量扫描：端口 × 波特率 × 从站，找出有应答的组合
    python3 modbus_probe.py scan --ports /dev/ttyUSB0,/dev/ttyUSB1 --bauds 9600,19200
    python3 modbus_probe.py read  --port /dev/ttyUSB1 --baud 9600 --slave 1 --reg 0 --count 10
    python3 modbus_probe.py write --port /dev/ttyUSB1 --baud 9600 --slave 1 --reg 1 --value 500
    python3 modbus_probe.py dump  --port /dev/ttyUSB1 --baud 9600 --slave 1 --start 0 --end 40
                                                       # 逐个寄存器读并把各种解析结果都打出来（挑电压/电流用）

注意：
  * 扫描前请停掉占用该串口的服务，避免抢端口（systemctl stop box-mapper），扫完再 start
  * 底层读写与 box_mapper.py 的 SimpleSerial 保持一致（termios 直驱），参数可直接照搬进
    /opt/weight-bridge/config.json 的 devices[].serial / modbus 字段
"""
import os
import re
import sys
import time
import glob
import struct
import fcntl
import select
import termios
import argparse

BAUD_MAP = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800,
            9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
            57600: termios.B57600, 115200: termios.B115200}


# ---------------------------------------------------------------------------
# 串口底层（与 box_mapper.py 的 SimpleSerial 同实现）
# ---------------------------------------------------------------------------
class SimpleSerial:
    def __init__(self, port, baud=9600, data=8, parity="N", stop=1):
        self.port = port
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, fl & ~os.O_NONBLOCK)
        attr = termios.tcgetattr(self.fd)
        attr[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                     termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        attr[1] = 0
        attr[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        attr[4] = termios.CLOCAL | termios.CREAD
        attr[4] |= {5: termios.CS5, 6: termios.CS6, 7: termios.CS7}.get(data, termios.CS8)
        if parity == "E":
            attr[4] |= termios.PARENB
        elif parity == "O":
            attr[4] |= termios.PARENB | termios.PARODD
        if stop == 2:
            attr[4] |= termios.CSTOPB
        b = BAUD_MAP.get(int(baud), termios.B9600)
        attr[4] = b
        attr[5] = b
        attr[6][termios.VMIN] = 0
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        self._set_lines(False, False)
        time.sleep(0.05)
        self._set_lines(True, True)
        time.sleep(0.05)
        self._set_lines(False, False)
        time.sleep(0.05)

    def _set_lines(self, dtr, rts):
        try:
            status = termios.TIOCM_DTR if dtr else 0
            status |= termios.TIOCM_RTS if rts else 0
            fcntl.ioctl(self.fd, termios.TIOCMSET, struct.pack("I", status))
        except Exception:
            pass

    def write(self, data):
        self._set_lines(False, True)
        time.sleep(0.001)
        os.write(self.fd, data)
        termios.tcdrain(self.fd)
        time.sleep(0.001)
        self._set_lines(False, False)

    def drain(self):
        """丢弃接收缓冲里的残留字节（上一次查询/其他从站的迟到响应）。"""
        try:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass
        while True:
            r, _, _ = select.select([self.fd], [], [], 0.02)
            if not r:
                break
            try:
                if not os.read(self.fd, 512):
                    break
            except OSError:
                break

    def read(self, n, timeout):
        buf = b""
        deadline = time.time() + timeout
        while len(buf) < n and time.time() < deadline:
            r, _, _ = select.select([self.fd], [], [], max(0, deadline - time.time()))
            if r:
                chunk = os.read(self.fd, n - len(buf))
                if chunk:
                    buf += chunk
        return buf

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Modbus RTU 报文
# ---------------------------------------------------------------------------
def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def _frame_len(buf: bytes):
    """根据已收字节判断整帧长度；不足返回 None。"""
    if len(buf) < 3:
        return None
    fc = buf[1]
    if fc in (0x03, 0x04):
        return 5 + buf[2]
    if fc in (0x01, 0x02):
        return 5 + buf[2]
    if fc in (0x05, 0x06, 0x0F, 0x10):
        return 8
    if fc >= 0x80:
        return 5
    return None


def transact(ser: SimpleSerial, slave: int, req: bytes, timeout=0.3):
    """发一帧、收一帧，返回完整 bytes（含 CRC）；超时/无响应返回 b''。"""
    ser.drain()
    ser.write(req)
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _, _ = select.select([ser.fd], [], [], 0.02)
        if r:
            try:
                buf += os.read(ser.fd, 512)
            except OSError:
                break
            n = _frame_len(buf)
            if n and len(buf) >= n:
                time.sleep(0.02)  # 静默期，确认帧已收全
                r2, _, _ = select.select([ser.fd], [], [], 0.02)
                if not r2:
                    break
        elif buf and _frame_len(buf):
            break
    return buf


def read_regs(ser, slave, addr, count, fc=0x03, timeout=0.3):
    req = struct.pack(">BBHH", slave, fc, addr, count)
    req += struct.pack("<H", modbus_crc(req))
    resp = transact(ser, slave, req, timeout)
    if not resp:
        return None, "无响应"
    if len(resp) < 5:
        return None, "响应过短: %s" % resp.hex()
    if resp[0] != slave:
        return None, "从站号不符(%d)" % resp[0]
    if modbus_crc(resp[:-2]) != struct.unpack("<H", resp[-2:])[0]:
        return None, "CRC 校验失败"
    if resp[1] != fc:
        return None, "异常码 0x%02X(原因 %d)" % (resp[1], resp[2] if len(resp) > 2 else -1)
    data = resp[3:3 + resp[2]]
    if len(data) < count * 2:
        return None, "数据不足"
    return data, ""


def probe_slave(ser, slave, fc, addr, count, timeout=0.3):
    """探测单个从站。返回 (状态, 数据或None, 原始响应)。

    关键：只要线上有字节回来（哪怕 CRC 错、哪怕异常码 0x83 非法地址），都算"这个从站存在"，
    扫描时一律打印——很多传感器/电源对不支持的寄存器返回异常码，不能当没应答忽略。
    """
    req = struct.pack(">BBHH", slave, fc, addr, count)
    req += struct.pack("<H", modbus_crc(req))
    resp = transact(ser, slave, req, timeout)
    if not resp:
        return "无响应", None, resp
    if len(resp) < 5 or resp[0] != slave:
        return "帧异常(%s)" % resp.hex(), None, resp
    if modbus_crc(resp[:-2]) != struct.unpack("<H", resp[-2:])[0]:
        return "CRC错(%s)" % resp.hex(), None, resp
    if resp[1] & 0x80:
        return "异常码0x%02X(原因%d)" % (resp[1], resp[2]), None, resp
    if resp[1] != fc:
        return "功能码不符(%s)" % resp.hex(), None, resp
    data = resp[3:3 + resp[2]]
    if len(data) < count * 2:
        return "数据不足(%s)" % resp.hex(), None, resp
    return "OK", data, resp


def write_single(ser, slave, addr, value, timeout=0.5):
    """功能码 0x06 写单个保持寄存器。value 为 0-65535。"""
    req = struct.pack(">BBHH", slave, 0x06, addr, value & 0xFFFF)
    req += struct.pack("<H", modbus_crc(req))
    resp = transact(ser, slave, req, timeout)
    if len(resp) != 8:
        return False, "响应长度异常: %s" % resp.hex()
    if resp[0] != slave or resp[1] != 0x06:
        if resp[1] >= 0x80:
            return False, "异常码 0x%02X(原因 %d)" % (resp[1], resp[2])
        return False, "响应头异常: %s" % resp[:4].hex()
    return True, "OK 寄存器=%d 值=%d" % (struct.unpack(">H", resp[2:4])[0],
                                      struct.unpack(">H", resp[4:6])[0])


# ---------------------------------------------------------------------------
# 数据解析（与 box_mapper.decode_regs 一致）
# ---------------------------------------------------------------------------
def decode_regs(data: bytes, dtype: str, byte_order: str = "2143"):
    dtype = (dtype or "float32").lower()
    bo = (byte_order or "2143").upper()
    try:
        if dtype in ("float32", "float", "real"):
            b = data[0:4]
            if len(b) < 4:
                return None
            if bo == "2143":
                b = b[1:2] + b[0:1] + b[3:4] + b[2:3]
            elif bo == "3412":
                b = b[2:4] + b[0:2]
            elif bo == "4321":
                b = b[::-1]
            return struct.unpack(">f", b)[0]
        if dtype in ("int16", "short"):
            return struct.unpack(">h", data[0:2])[0]
        if dtype in ("uint16", "ushort", "word"):
            return struct.unpack(">H", data[0:2])[0]
        if dtype in ("int32", "int"):
            return struct.unpack(">i", data[0:4])[0]
        if dtype in ("uint32", "uint", "dword"):
            return struct.unpack(">I", data[0:4])[0]
        if dtype in ("int64", "long"):
            return struct.unpack(">q", data[0:8])[0]
        if dtype in ("uint64", "ulong"):
            return struct.unpack(">Q", data[0:8])[0]
    except Exception:
        return None
    return None


def candidate_views(data: bytes):
    """把一个寄存器块的所有可能解析都列出来，便于肉眼识别哪个像电压/电流。"""
    out = []
    for bo in ("2143", "1234", "3412", "4321"):
        v = decode_regs(data, "float32", bo)
        if v is not None and abs(v) < 1e10:
            out.append("f32/%s=%.4f" % (bo, v))
    out.append("u16=%d" % decode_regs(data, "uint16"))
    out.append("i16=%d" % decode_regs(data, "int16"))
    if len(data) >= 4:
        out.append("u32=%d" % decode_regs(data, "uint32"))
        out.append("i32=%d" % decode_regs(data, "int32"))
    return out


# ---------------------------------------------------------------------------
# 串口枚举
# ---------------------------------------------------------------------------
PORT_GLOBS = ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyXRUSB*", "/dev/ttyCH341USB*",
              "/dev/ttyS*", "/dev/ttyAMA*", "/dev/ttyO*", "/dev/ttymxc*", "/dev/ttySC*")


def _sys_attr(devname):
    """读取 USB 串口的厂商/产品/序列号（用于辨认刚插上的那个口）。"""
    info = {}
    base = "/sys/class/tty/%s" % devname
    if not os.path.isdir(base):
        return info
    try:
        real = os.path.realpath(base)
    except OSError:
        real = base
    for _ in range(6):
        real = os.path.dirname(real)
        if os.path.isdir(os.path.join(real, "subsystem")) or os.path.isfile(os.path.join(real, "idVendor")):
            pass
        if os.path.isfile(os.path.join(real, "idVendor")):
            try:
                vid = open(os.path.join(real, "idVendor")).read().strip()
                pid = open(os.path.join(real, "idProduct")).read().strip()
                info["usb"] = "%s:%s" % (vid, pid)
            except OSError:
                pass
            for k, f in (("vendor", "manufacturer"), ("product", "product"), ("serial", "serial")):
                try:
                    info[k] = open(os.path.join(real, f)).read().strip()
                except OSError:
                    pass
            break
    # 稳定的 by-id 软链接
    try:
        target = os.path.realpath("/dev/" + devname)
        for p in glob.glob("/dev/serial/by-id/*") + glob.glob("/dev/serial/by-path/*"):
            if os.path.realpath(p) == target:
                info["byid"] = p
                break
    except OSError:
        pass
    return info


def list_ports():
    ports = []
    for g in PORT_GLOBS:
        for p in glob.glob(g):
            if p not in ports and re.search(r"\d+$", p):
                ports.append(p)

    def key(p):
        m = re.search(r"(\d+)$", p)
        return (p.rstrip("0123456789"), int(m.group(1)) if m else 0)

    ports.sort(key=key)
    return ports


def cmd_list(args):
    ports = list_ports()
    print("发现串口设备 %d 个：\n" % len(ports))
    for p in ports:
        try:
            fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            os.close(fd)
            state = "可打开"
        except OSError as e:
            state = "打不开(%s)" % e.strerror
        info = _sys_attr(os.path.basename(p))
        extra = " ".join("%s=%s" % (k, v) for k, v in info.items() if v)
        print("  %-22s %-10s %s" % (p, state, extra))
    print("\n提示：刚接的那根 RS485 转换器一般是列表里最后出现的 ttyUSB/ttyACM；")
    print("      看 USB 厂商/序列号（CH340/FT232/CP210 等）能确认具体是哪根线。")
    print("      若上面都不确定，可拔掉转换器再 list 一次，消失的那个口就是它。")


def cmd_sniff(args):
    """只读监听：判断线上到底有没有数据、是什么协议（不少数控电源/仪表是 ASCII 协议）。"""
    ports = [p.strip() for p in args.ports.split(",")]
    for port in ports:
        for baud in [int(b) for b in args.bauds.split(",")]:
            try:
                ser = SimpleSerial(port, baud, 8, args.parity, args.stop)
            except OSError as e:
                print("%s@%d 打不开：%s" % (port, baud, e))
                continue
            ser.drain()
            buf = b""
            deadline = time.time() + args.seconds
            print("监听 %s @%d 8%s1 ... %s" % (port, baud, args.parity, "（换个电压/扭一下旋钮看有没有数据冒出来）" if args.interactive else ""))
            while time.time() < deadline:
                r, _, _ = select.select([ser.fd], [], [], 0.2)
                if r:
                    chunk = os.read(ser.fd, 512)
                    if chunk:
                        buf += chunk
                        print("  <- %s  |  %s" % (chunk.hex(),
                                                  "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)))
            ser.close()
            if not buf:
                print("  （静默，未收到任何字节）")


def cmd_selftest(args):
    """USB-485 转换器自检：发送一串字节，看能否被自己收回（回环）。

    结果解读：
      * 收回相同字节 -> CH340 与 485 收发芯片工作正常（该模块 RE 常开，会自回显），
                        线上没应答就是从站那侧的问题（接线/供电/参数）
      * 什么都没收回 -> 自动收发模块（发时关接收）属正常；也可能是 TX 没输出/模块坏，
                        此时把 A、B 两根线短接再测一次，能收回即模块完好
    """
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    try:
        payload = bytes([0x55, 0xAA, 0x01, 0x03, 0x00, 0x00, 0x00, 0x02])
        for attempt in (1, 2):
            ser.drain()
            ser.write(payload)
            got = b""
            deadline = time.time() + args.seconds
            while time.time() < deadline:
                r, _, _ = select.select([ser.fd], [], [], 0.1)
                if r:
                    got += os.read(ser.fd, 512)
            print("%s @%d 8%s1 第%d次：发 %s" % (args.port, args.baud, args.parity, attempt, payload.hex()))
            print("    收回：%s%s" % (got.hex() or "(空)", "  ✅ 自回显，模块收发路径正常" if got else "  ⚠️ 无回显"))
            if got:
                return
    finally:
        ser.close()
    print("  提示：把转换器的 A、B 短接后再跑一次本命令，能收回说明模块本身是好的，")
    print("        问题在从站（A/B 反接、未供电、未设 RTU 从站模式、总线被某个设备锁死）。")


def cmd_blast(args):
    """持续往总线发帧（调试用，配合万用表/短接 A-B 判断链路）。

    两种用法：
      ① 现场用万用表直流档量 A-B：原本空闲 0.05V，发帧时会看到电压明显跳动
         -> 有跳动说明转换器 TX 在驱动总线（模块是好的，问题在从站）
         -> 完全不动说明转换器没驱动总线，换线/换口
      ② 把 A、B 用一根导线短接后跑本命令：能收回自己发的帧 -> 收发全链路完好；
         收不回 -> 模块是"自动收发型"（发时关接收），此时用万用表法判断
    """
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    slaves = [int(x) for x in args.slaves.split(",")]
    total_rx = b""
    deadline = time.time() + args.seconds
    n = 0
    try:
        print("持续发送 %s @%d 8%s1 %.0f 秒（从站 %s）..." %
              (args.port, args.baud, args.parity, args.seconds, args.slaves))
        while time.time() < deadline:
            for sl in slaves:
                req = struct.pack(">BBHH", sl, args.fc, args.reg, args.count)
                req += struct.pack("<H", modbus_crc(req))
                ser.write(req)
                n += 1
                time.sleep(args.gap)
                r, _, _ = select.select([ser.fd], [], [], 0)
                if r:
                    got = os.read(ser.fd, 512)
                    if got:
                        total_rx += got
                        print("  <- %s | %s" % (got.hex(),
                                               "".join(chr(c) if 32 <= c < 127 else "." for c in got)))
    finally:
        ser.close()
    print("共发 %d 帧，收到 %d 字节 %s" % (n, len(total_rx), total_rx.hex() or "(空)"))


def cmd_watch(args):
    """盯梢模式：循环轮询，一旦有设备应答立刻报告。

    用法：现场接线/上电时开着它， instructor 改完线马上能看到结果，不用来回喊。
    默认按 B-T-RS50 出厂参数（9600 8N1 地址1）轮询，并顺带查 0xFF 广播地址。
    """
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    deadline = time.time() + args.seconds
    slaves = [int(x) for x in args.slaves.split(",")]
    hits = 0
    last = ""
    print("盯梢 %s @%d 8%s1 共 %.0f 秒，轮询从站 %s（Ctrl-C 退出）"
          % (args.port, args.baud, args.parity, args.seconds, args.slaves))
    try:
        while time.time() < deadline:
            line = []
            for sl in slaves:
                status, data, resp = probe_slave(ser, sl, 0x03, args.reg, args.count, args.timeout)
                if status != "无响应":
                    val = ""
                    if data:
                        raw = decode_regs(data, "int16")
                        val = " int16=%s 温度=%.1f℃" % (raw, raw / 10.0) if raw is not None else ""
                    print("  ✅ %s 从站=%d %s%s" % (time.strftime("%H:%M:%S"), sl, status, val))
                    hits += 1
                line.append("%d:%s" % (sl, "ok" if data else ("exc" if resp else "-")))
            cur = " ".join(line)
            if cur != last:
                print("  [%s] %s" % (time.strftime("%H:%M:%S"), cur))
                last = cur
            time.sleep(args.period)
    finally:
        ser.close()
    print("盯梢结束，共发现 %d 次应答" % hits)


# ---------------------------------------------------------------------------
# scan / read / dump / write
# ---------------------------------------------------------------------------
def _parse_range(s, lo, hi, default):
    if not s:
        return list(range(*default))
    if "," in s:
        return [int(x) for x in s.split(",") if x.strip()]
    if "-" in s:
        a, b = s.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s)]


def cmd_scan(args):
    ports = [p.strip() for p in args.ports.split(",")] if args.ports else list_ports()
    bauds = [int(b) for b in args.bauds.split(",")]
    parities = [p for p in args.parities.split(",")]
    slaves = _parse_range(args.slaves, 1, 247, (1, 33))
    found = []
    print("扫描：端口 %s | 波特率 %s | 校验 %s | 从站 %d-%d | 读保持寄存器 addr=%d count=%d\n"
          % (",".join(ports), ",".join(map(str, bauds)), ",".join(parities),
             slaves[0], slaves[-1], args.reg, args.count))
    for port in ports:
        try:
            fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            os.close(fd)
        except OSError as e:
            print("  [跳过] %s 打不开：%s" % (port, e))
            continue
        for baud in bauds:
            for par in parities:
                try:
                    ser = SimpleSerial(port, baud, 8, par, 1)
                except OSError as e:
                    print("  [跳过] %s@%d 无法打开：%s" % (port, baud, e))
                    break
                hit = []
                try:
                    for sl in slaves:
                        for fc in args.fc:
                            status, data, resp = probe_slave(ser, sl, fc, args.reg, args.count, args.timeout)
                            if status == "无响应":
                                continue
                            hit.append((sl, fc, status, data, resp))
                            if data:
                                print("  ✅ %s  %d 8%s1  从站=%d  FC=0x%02X  reg%d~%d 原始=%s" %
                                      (port, baud, par, sl, fc, args.reg, args.reg + args.count - 1, data.hex()))
                                print("       解析候选： %s" % "  ".join(candidate_views(data)))
                            else:
                                print("  ⚠️ %s  %d 8%s1  从站=%d  FC=0x%02X  %s  (设备有响应，但寄存器不可读)" %
                                      (port, baud, par, sl, fc, status))
                finally:
                    ser.close()
                found.extend([(port, baud, par, sl, fc, st, d) for sl, fc, st, d, _ in hit])
    if not found:
        print("\n❌ 没扫到任何应答设备。请检查：RS485 A/B 是否接反、转换器是否供电、")
        print("   串口是否被 box-mapper 占用（systemctl stop box-mapper 后再扫）、")
        print("   电源是否上电并处于 Modbus RTU 从站模式（有的要面板里设 Addr/Baud）。")
    else:
        print("\n汇总：")
        for port, baud, par, sl, fc, st, d in found:
            print("  %s | %d | 8%s1 | 从站 %d | FC=0x%02X | %s | %s" %
                  (port, baud, par, sl, fc, st, d.hex() if d else "-"))


def cmd_read(args):
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    try:
        for fc, name in ((0x03, "保持寄存器(0x03)"), (0x04, "输入寄存器(0x04)")):
            data, err = read_regs(ser, args.slave, args.reg, args.count, fc, args.timeout)
            if data is None:
                print("%s：失败 %s" % (name, err))
            else:
                print("%s addr=%d count=%d" % (name, args.reg, args.count))
                print("  原始字节：%s" % data.hex())
                for i in range(0, len(data), 2):
                    print("    [%02d] %s | %s" % (args.reg + i // 2, data[i:i + 2].hex(),
                                                 "  ".join(candidate_views(data[i:i + 2]))))
                print("  整块解析：%s" % "  ".join(candidate_views(data)))
    finally:
        ser.close()


def cmd_dump(args):
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    try:
        print("从站 %d 寄存器 %d~%d 逐个读取（一次读 1 个寄存器 2 字节 + 相邻两字节组合）\n" %
              (args.slave, args.start, args.end))
        for addr in range(args.start, args.end + 1):
            data, err = read_regs(ser, args.slave, addr, 1, args.fc, args.timeout)
            if data is None:
                print("  [%3d] %s" % (addr, err))
                continue
            print("  [%3d] hex=%s  u16=%d  i16=%d" %
                  (addr, data.hex(), decode_regs(data, "uint16"), decode_regs(data, "int16")))
    finally:
        ser.close()


def cmd_write(args):
    ser = SimpleSerial(args.port, args.baud, 8, args.parity, args.stop)
    try:
        ok, msg = write_single(ser, args.slave, args.reg, args.value, args.timeout)
        print(("✅ 写成功：" if ok else "❌ 写失败：") + msg)
    finally:
        ser.close()


def main():
    ap = argparse.ArgumentParser(description="RS485/Modbus RTU 串口排查工具")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="列出串口与 USB 拓扑")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("sniff", help="只读监听串口，看线上有没有自发数据/什么协议")
    p.add_argument("--ports", required=True, help="逗号分隔")
    p.add_argument("--bauds", default="9600,19200")
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--interactive", action="store_true")
    p.set_defaults(func=cmd_sniff)

    p = sub.add_parser("selftest", help="USB-485 转换器自检（发字节看能否自回显）")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--seconds", type=float, default=1.0)
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("blast", help="持续发帧，配合万用表/短接判断链路")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--slaves", default="1,2,3", help="轮询的从站号，逗号分隔")
    p.add_argument("--fc", type=lambda x: int(x, 0), default=0x03)
    p.add_argument("--reg", type=int, default=0)
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--gap", type=float, default=0.05, help="每帧间隔秒")
    p.set_defaults(func=cmd_blast)

    p = sub.add_parser("watch", help="盯梢：循环轮询，一有应答立刻报告")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--slaves", default="1,255")
    p.add_argument("--reg", type=int, default=0)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--seconds", type=float, default=300.0)
    p.add_argument("--period", type=float, default=1.0)
    p.add_argument("--timeout", type=float, default=0.3)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("scan", help="扫描端口/波特率/从站")
    p.add_argument("--ports", default="", help="逗号分隔，留空=全部串口")
    p.add_argument("--bauds", default="9600,19200", help="逗号分隔，默认 9600,19200")
    p.add_argument("--parities", default="N,E", help="校验位，默认 N,E")
    p.add_argument("--slaves", default="", help="从站范围，如 1-32 或 1,2,5；默认 1-32")
    p.add_argument("--fc", type=lambda x: int(x, 0), nargs="+", default=[0x03],
                   help="读功能码，可多个：3(保持寄存器) 4(输入寄存器) 1(线圈) 2(离散输入)")
    p.add_argument("--reg", type=int, default=0, help="起始寄存器地址，默认 0")
    p.add_argument("--count", type=int, default=2, help="读寄存器个数，默认 2")
    p.add_argument("--timeout", type=float, default=0.35, help="每帧等待秒数，默认 0.35")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("read", help="读一段寄存器并列出所有解析结果")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--reg", type=int, default=0)
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--timeout", type=float, default=0.5)
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("dump", help="逐个寄存器扫描，用于挑出电压/电流/功率")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=40)
    p.add_argument("--fc", type=lambda x: int(x, 0), default=0x03)
    p.add_argument("--timeout", type=float, default=0.5)
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("write", help="写单个保持寄存器(0x06)，用于设定电压等")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--parity", default="N")
    p.add_argument("--stop", type=int, default=1)
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--reg", type=int, required=True)
    p.add_argument("--value", type=lambda x: int(x, 0), required=True)
    p.add_argument("--timeout", type=float, default=0.8)
    p.set_defaults(func=cmd_write)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
