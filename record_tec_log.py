#!/usr/bin/env python3
"""TEC 试验台运行数据定时采样记录脚本（周期可指定，CSV 落盘）。

采样对象（全部来自能碳一体机 nt001 上报的实时读数，经平台 /api/box/devices/realtime
聚合，该接口不可用时回退 /api/data-sources/signals）：
  - zhileng-power  / fengshan-power：电流设定值 current_set(A)、电压设定值 voltage_set(V)、
    电流实际值 current(A)、电压实际值 voltage(V)、功率实际值 power(W)
  - env-temp / shuitong-temp / zhileng-temp / servers-temp：temperature(℃)

用法（数据源默认走服务器 36.151.146.71:40014，加 --local 才用本地 8010）：
    python3 record_tec_log.py                          # 服务器数据源，默认 1s 一次，直到 Ctrl+C
    python3 record_tec_log.py -i 10                    # 指定采样周期 10s（--interval / --period 同义）
    python3 record_tec_log.py -i 2 --duration 600      # 2s 一次，共采 10 分钟后自动停
    python3 record_tec_log.py --local                  # 切到本地平台 127.0.0.1:8010
    python3 record_tec_log.py --out /tmp/tec.csv       # 指定落盘文件（默认 ./logs/tec_<时间戳>.csv）

采样周期：-i/--interval/--period 指定，支持小数（如 0.5），下限 0.5s（再快受单次 HTTP
拉取耗时限制，脚本会按「补齐周期」对齐，即实际间隔 = 周期，不叠加请求耗时）。
**周期必须小于最快通道的上报周期**：实测电源约 2.2s 一报、温度 15~40s 一报，
若周期（如 5s）大于设备上报周期，两次采样之间的上报就被漏掉了，
「设备上报时刻」的步进会退化成采样周期看着像「设备每 5s 一报」——那是采样假象。

CSV 表头为中文，前三列是「相对启动时刻的秒数」，不写绝对时间：
  - 采样时刻(s)    本行采样时刻（0.0 / 1.0 / 2.0 …，按 --interval 递增）
  - 设备上报时刻(s) 本行这些读数里**最新**的那次真实上报时刻（点位自己的时间戳，
    不是平台收到时间），相对启动时刻；通常为负一点点或略小于采样时刻
  - 最旧上报时刻(s) 本行这些读数里**最旧**的那次上报时刻 —— 这一行数据到底有多旧，
    看它：与「采样时刻」的差就是本行最陈旧通道的滞后；数据冻结时它不动、滞后持续增大
    绝对起始时刻见终端首行 [start] 与输出文件名中的时间戳。

说明：
  - 只读，不下发任何指令，不影响现场设备运行。
  - 读数缺失（设备停报/本次快照没带该字段）时写空值，并在终端告警，保证时间序列连续。
  - 每通道有独立的新鲜度上限（power 30s、温度 600s），超过即视为停报记空。
  - 时间戳来源：平台 /api/box/devices/realtime 的 twins[].timestamp（点位级真实上报时刻），
    并用该接口返回的服务器时钟 time 与本机时钟对齐（消除两台机器时钟偏差带来的假年龄）；
    该接口不可用时回退到 /api/data-sources/signals（只有设备级 last_seen，精度降级）。
  - Ctrl+C 优雅退出：flush 落盘并打印汇总。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# 设备中文名（表头用）
DEV_CN = {
    "zhileng-power": "制冷电源",
    "fengshan-power": "风扇电源",
    "env-temp": "环境",
    "shuitong-temp": "冷却水",
    "zhileng-temp": "制冷风口",
    "servers-temp": "服务器",
}
# 电源通道：(点位名, 中文标签, 单位)
POWER_FIELDS = [
    ("current_set", "电流设定", "A"),
    ("voltage_set", "电压设定", "V"),
    ("current", "电流", "A"),
    ("voltage", "电压", "V"),
    ("power", "功率", "W"),
]
# 数据源默认走服务器（生产平台 40014：一体机上报的数据直接落在这儿，设备齐全且不停机）；
# --local 切到本地开发实例 8010。
SERVER_BASE = "http://36.151.146.71:40014"
LOCAL_BASE = "http://127.0.0.1:8010"

POWER_DEVICES = ["zhileng-power", "fengshan-power"]
TEMP_DEVICES = ["env-temp", "shuitong-temp", "zhileng-temp", "servers-temp"]
POWER_MAX_AGE = 30.0     # 电源实测约 2.2s 一报，30s 无更新即判停报
TEMP_MAX_AGE = 600.0     # LoRa 温度应答率低（实测 15~40s），允许较长间隔
DEFAULT_INTERVAL = 1.0   # 默认 1s 采样：快于电源 2.2s 的上报周期，才不会漏采


def build_channels():
    """返回通道列表 [(表头中文名, 设备名, 点位名, 新鲜度上限)]。

    前三列是时间列（设备名 None）：
      - 采样时刻(s)     本行采样时刻，相对启动时刻的秒数
      - 设备上报时刻(s) 本行所有有效读数里**最新**的真实上报时刻（点位级 timestamp）
      - 最旧上报时刻(s) 本行所有有效读数里**最旧**的真实上报时刻（= 本行数据的新鲜度下界）
    """
    ch = [("采样时刻(s)", None, None, 0.0),
          ("设备上报时刻(s)", None, None, 0.0),
          ("最旧上报时刻(s)", None, None, 0.0)]
    for dev in POWER_DEVICES:
        for field, label, unit in POWER_FIELDS:
            ch.append((f"{DEV_CN.get(dev, dev)}-{label}({unit})", dev, field, POWER_MAX_AGE))
    for dev in TEMP_DEVICES:
        ch.append((f"{DEV_CN.get(dev, dev)}温度(℃)", dev, "temperature", TEMP_MAX_AGE))
    return ch


def _get_json(base: str, path: str, timeout: float):
    """GET 一个 JSON 接口，返回 (数据, 本次请求中点的本机时刻)。"""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data, (t0 + time.time()) / 2.0


def fetch_realtime(base: str, timeout: float = 8.0):
    """点位级真实上报时刻：返回 ({(device, field): (value, ts)}, 服务器时钟偏移)。

    /api/box/devices/realtime 的 twins[].timestamp 是**点位自己的**上报时刻（区别于
    signals 的设备级 last_seen「平台收到时刻」）；响应里的 time 是服务器时钟，
    用它算出 off = 服务器时间 - 本机时间，之后所有年龄/上报时刻都换算到服务器时钟上，
    避免两台机器时钟不一致导致年龄整体偏移（偏快=永远新鲜、偏慢=永远停报）。
    """
    data, mid = _get_json(base, "/api/box/devices/realtime", timeout)
    out = {}
    for dev in (data.get("devices") or []):
        name = dev.get("name") or dev.get("id")
        for t in (dev.get("twins") or []):
            if t.get("invalid"):
                continue
            v, ts = t.get("reported"), t.get("timestamp")
            if v is None or not ts:
                continue
            out[(name, t.get("propertyName"))] = (round(float(v), 4), float(ts))
    srv = float(data.get("time") or 0)
    return out, (srv - mid if srv else 0.0)


def fetch_signals(base: str, timeout: float = 8.0):
    """兜底数据源：返回 ({(device, field): (value, ts)}, None)。

    只有设备级 last_seen（平台收到时刻），无服务器时钟字段，故偏移返回 None
    （调用方沿用已校准的偏移）。
    """
    data, _ = _get_json(base, "/api/data-sources/signals", timeout)
    out = {}
    for src in (data.get("sources") or []):
        for dev in (src.get("devices") or []):
            name = dev.get("device") or dev.get("id")
            seen = float(dev.get("last_seen") or 0)
            for v in (dev.get("values") or []):
                if v.get("invalid"):
                    continue
                out[(name, v.get("field"))] = (v.get("value"), seen)
    return out, None


def sample(channels, sig, now):
    """按通道顺序取一行数据；缺失/过期返回空字符串。

    返回 (row, stale, newest, oldest)：newest/oldest 为本行所有有效读数里最新/最旧的
    上报时刻（epoch 秒），无有效读数时 newest=0、oldest=None；
    row 已含前三列时间占位（由调用方填）。
    """
    row, stale, newest, oldest = ["", "", ""], [], 0.0, None
    for _, dev, field, max_age in channels[3:]:
        item = sig.get((dev, field))
        val = ""
        if item and item[0] is not None and item[1]:
            age = now - item[1]
            if age <= max_age:
                val = item[0]
                newest = max(newest, item[1])
                oldest = item[1] if oldest is None else min(oldest, item[1])
            else:
                stale.append(f"{dev}.{field}({age:.0f}s未更新)")
        else:
            stale.append(f"{dev}.{field}(无数据)")
        row.append(val)
    return row, stale, newest, oldest


def main():
    ap = argparse.ArgumentParser(description="TEC 试验台数据定时采样记录")
    ap.add_argument("--base", default=SERVER_BASE,
                    help=f"平台地址（默认服务器 {SERVER_BASE}）")
    ap.add_argument("--local", action="store_true",
                    help=f"用本地开发实例 {LOCAL_BASE}（等价于 --base {LOCAL_BASE}）")
    ap.add_argument("-i", "--interval", "--period", dest="interval", type=float,
                    default=DEFAULT_INTERVAL,
                    help=f"采样周期秒，支持小数（默认 {DEFAULT_INTERVAL}，下限 0.5；"
                         "须小于设备上报周期，否则会漏采且上报时刻被周期量化）")
    ap.add_argument("--duration", type=float, default=0, help="总时长秒，0=一直采到 Ctrl+C")
    ap.add_argument("--out", default="", help="输出 CSV 路径（默认 <脚本目录>/logs/tec_<时间戳>.csv）")
    ap.add_argument("--timeout", type=float, default=8.0, help="单次 HTTP 超时秒")
    args = ap.parse_args()
    if args.local:
        args.base = LOCAL_BASE
    if args.interval < 0.5:
        ap.error(f"采样周期不能小于 0.5s（当前 {args.interval}）")

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logs",
        "tec_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    channels = build_channels()
    cols = [c[0] for c in channels]
    new_file = not os.path.exists(out_path) or os.path.getsize(out_path) == 0
    fp = open(out_path, "a", newline="", encoding="utf-8-sig")   # utf-8-sig：Excel 直接打开不乱码
    writer = csv.writer(fp)
    if new_file:
        writer.writerow(cols)
        fp.flush()

    started_dt = datetime.now()
    print(f"[start] {started_dt:%Y-%m-%d %H:%M:%S} 起，采样周期 {args.interval}s -> {out_path}")
    print(f"        数据源: {args.base}")
    print("        通道: " + " | ".join(cols[3:]))
    if args.interval > 2.0:
        print(f"[warn] 采样周期 {args.interval}s 大于电源上报周期（约 2.2s），会漏采，"
              "「设备上报时刻」的步进将退化成采样周期（看不出设备真实节奏）")
    started, count, errs = time.time(), 0, 0
    off, off_done = 0.0, False      # 服务器时钟 - 本机时钟，首次成功拉取时校准一次
    try:
        while True:
            t0 = time.time()
            if args.duration and t0 - started >= args.duration:
                break
            try:
                try:
                    sig, o = fetch_realtime(args.base, args.timeout)
                    if o is not None and not off_done:
                        off, off_done = o, True
                except (urllib.error.URLError, OSError, ValueError):
                    sig, _ = fetch_signals(args.base, args.timeout)   # 兜底：设备级 last_seen
                now_svr = time.time() + off        # 换算到服务器时钟（与点位时间戳同一时钟）
                row, stale, newest, oldest = sample(channels, sig, now_svr)
                errs = 0
            except (urllib.error.URLError, OSError, ValueError) as e:
                errs += 1
                row, stale, newest, oldest = (["", "", ""] + [""] * (len(cols) - 3),
                                              [f"拉取失败: {e}"], 0.0, None)
            now_svr = time.time() + off
            start_svr = started + off
            row[0] = f"{now_svr - start_svr:.1f}"
            row[1] = f"{newest - start_svr:.1f}" if newest else ""
            row[2] = f"{oldest - start_svr:.1f}" if oldest else ""
            writer.writerow(row)
            fp.flush()
            count += 1
            lag = f" | 滞后 {now_svr - oldest:.1f}s" if oldest else ""
            mark = " | 缺失: " + ", ".join(stale) if stale else ""
            print(f"[{count:05d}] 采样 {row[0]}s | 最新上报 {row[1] or '-'}s"
                  f" | 最旧上报 {row[2] or '-'}s{lag} | "
                  + " ".join(f"{c}={v}" if v != "" else f"{c}=-" for c, v in zip(cols[3:], row[3:]))
                  + mark)
            if errs >= 5:
                print("[error] 连续 5 次拉取失败，退出", file=sys.stderr)
                break
            time.sleep(max(0.2, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        print("\n[stop] 用户中断")
    finally:
        fp.close()
        print(f"[done] {count} 行已写入 {out_path}（时长 {time.time() - started:.0f}s）")


if __name__ == "__main__":
    main()
