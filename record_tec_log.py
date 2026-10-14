#!/usr/bin/env python3
"""TEC 试验台运行数据定时采样记录脚本（周期可指定，CSV 落盘）。

采样对象（全部来自能碳一体机 nt001 上报的实时读数，经平台 /api/data-sources/signals 聚合）：
  - zhileng-power  / fengshan-power：电流设定值 current_set(A)、电压设定值 voltage_set(V)、
    电流实际值 current(A)、电压实际值 voltage(V)、功率实际值 power(W)
  - env-temp / shuitong-temp / zhileng-temp / servers-temp：temperature(℃)

用法：
    python3 record_tec_log.py                          # 本地平台 8010，默认 5s 一次，直到 Ctrl+C
    python3 record_tec_log.py -i 10                    # 指定采样周期 10s（--interval / --period 同义）
    python3 record_tec_log.py -i 2 --duration 600      # 2s 一次，共采 10 分钟后自动停
    python3 record_tec_log.py --base http://127.0.0.1:40014      # 打生产实例
    python3 record_tec_log.py --out /tmp/tec.csv       # 指定落盘文件（默认 ./logs/tec_<时间戳>.csv）

采样周期：-i/--interval/--period 指定，支持小数（如 0.5），下限 0.5s（再快受单次 HTTP
拉取耗时限制，脚本会按「补齐周期」对齐，即实际间隔 = 周期，不叠加请求耗时）。

CSV 表头为中文，前两列是「相对启动时刻的秒数」，不写绝对时间：
  - 采样时刻(s)    本行采样时刻（0.0 / 5.0 / 10.0 …，按 --interval 递增）
  - 设备上报时刻(s) 本行这些读数在设备侧的上报时刻（last_seen），同样相对启动时刻；
    取本行所有有效通道里最新的一次上报（power 1~2s 一报、温度 5~10s 一报，
    所以该值通常略小于「采样时刻」，差值就是读数的新鲜度）
    绝对起始时刻见终端首行 [start] 与输出文件名中的时间戳。

说明：
  - 只读，不下发任何指令，不影响现场设备运行。
  - 读数缺失（设备停报/本次快照没带该字段）时写空值，并在终端告警，保证时间序列连续。
  - 每通道有独立的新鲜度上限（power 30s、温度 600s），超过即视为停报记空。
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
POWER_DEVICES = ["zhileng-power", "fengshan-power"]
TEMP_DEVICES = ["env-temp", "shuitong-temp", "zhileng-temp", "servers-temp"]
POWER_MAX_AGE = 30.0     # power 采集周期 1~2s，30s 无更新即判停报
TEMP_MAX_AGE = 600.0     # LoRa 温度应答率低，允许较长间隔


def build_channels():
    """返回通道列表 [(表头中文名, 设备名, 点位名, 新鲜度上限)]。

    前两列是时间列（设备名 None）：
      - 采样时刻(s)   本行采样时刻，相对启动时刻的秒数（0.0 / 5.0 / 10.0 …）
      - 设备上报时刻(s) 本行读数的设备上报时刻（last_seen），同样相对启动时刻；
        取本行所有有效通道里最新的一次上报
    """
    ch = [("采样时刻(s)", None, None, 0.0), ("设备上报时刻(s)", None, None, 0.0)]
    for dev in POWER_DEVICES:
        for field, label, unit in POWER_FIELDS:
            ch.append((f"{DEV_CN.get(dev, dev)}-{label}({unit})", dev, field, POWER_MAX_AGE))
    for dev in TEMP_DEVICES:
        ch.append((f"{DEV_CN.get(dev, dev)}温度(℃)", dev, "temperature", TEMP_MAX_AGE))
    return ch


def fetch_signals(base: str, timeout: float = 8.0):
    """拉取信号目录，返回 {(device, field): (value, last_seen)}。"""
    url = base.rstrip("/") + "/api/data-sources/signals"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = {}
    for src in (data.get("sources") or []):
        for dev in (src.get("devices") or []):
            name = dev.get("device") or dev.get("id")
            seen = float(dev.get("last_seen") or 0)
            for v in (dev.get("values") or []):
                if v.get("invalid"):
                    continue
                out[(name, v.get("field"))] = (v.get("value"), seen)
    return out


def sample(channels, sig, now):
    """按通道顺序取一行数据；缺失/过期返回空字符串。

    返回 (row, stale, newest)：newest 为本行所有有效读数的设备上报时刻（epoch 秒，取最大值），
    无有效读数时为 0；row 已含前两列时间占位（由调用方填）。
    """
    row, stale, newest = ["", ""], [], 0.0
    for _, dev, field, max_age in channels[2:]:
        item = sig.get((dev, field))
        val = ""
        if item and item[0] is not None:
            age = now - item[1]
            if age <= max_age:
                val = item[0]
                newest = max(newest, item[1])
            else:
                stale.append(f"{dev}.{field}({age:.0f}s未更新)")
        else:
            stale.append(f"{dev}.{field}(无数据)")
        row.append(val)
    return row, stale, newest


def main():
    ap = argparse.ArgumentParser(description="TEC 试验台数据定时采样记录")
    ap.add_argument("--base", default="http://127.0.0.1:8010", help="平台地址（默认本地 8010）")
    ap.add_argument("-i", "--interval", "--period", dest="interval", type=float, default=5.0,
                    help="采样周期秒，支持小数（默认 5，下限 0.5）")
    ap.add_argument("--duration", type=float, default=0, help="总时长秒，0=一直采到 Ctrl+C")
    ap.add_argument("--out", default="", help="输出 CSV 路径（默认 <脚本目录>/logs/tec_<时间戳>.csv）")
    ap.add_argument("--timeout", type=float, default=8.0, help="单次 HTTP 超时秒")
    args = ap.parse_args()
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
    print("        通道: " + " | ".join(cols[2:]))
    started, count, errs = time.time(), 0, 0
    try:
        while True:
            t0 = time.time()
            if args.duration and t0 - started >= args.duration:
                break
            now = time.time()
            try:
                sig = fetch_signals(args.base, args.timeout)
                row, stale, newest = sample(channels, sig, now)
                errs = 0
            except (urllib.error.URLError, OSError, ValueError) as e:
                errs += 1
                row, stale, newest = ["", ""] + [""] * (len(cols) - 2), [f"拉取失败: {e}"], 0.0
            row[0] = f"{now - started:.1f}"
            row[1] = f"{newest - started:.1f}" if newest else ""
            writer.writerow(row)
            fp.flush()
            count += 1
            mark = " | 缺失: " + ", ".join(stale) if stale else ""
            print(f"[{count:05d}] {row[0]}s(上报 {row[1] or '-'}s) "
                  + " ".join(f"{c}={v}" if v != "" else f"{c}=-" for c, v in zip(cols[2:], row[2:]))
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
