#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEC 制冷片 PRBS 采集数据 —— 实时可视化（matplotlib，逐列分屏画图）。

【用途】
    在辨识采集脚本（prbs_tec_ident.py）运行的同时（或跑完之后），把 CSV 里的
    【所有列】实时画出来，用于现场盯进度、第一时间发现异常：
      电流没跟上设定 / 输出被关 / 电压顶到限压 / 温度掉线（缺测）/ 读数陈旧（age 大）。

【画的列与分组】（x 轴 = t，按分钟显示）
    ① 电流(A)   ：current_set（设定，阶梯）+ current（实际）
    ② 电压(V)   ：voltage（恒流模式下由负载决定，不是设定值）
    ③ 功率(W)   ：power
    ④ 温度(℃)   ：shuitong_temp 热端冷却水 / servers_temp 目标水杯
                   env_temp 环境室温 / zhileng_temp 冷端风口（电流越大越低）
    ⑤ 测量滞后  ：temp_age（s，读数比名义时刻滞后多少）+ temp_new（0/1，本拍是否新值，右轴）

【实时机制】
    - 增量读取：记录上次读到的字节偏移，每拍只读新增部分，不整文件重读；
    - 半行保护：没读到结尾换行的最后一行留到下一拍，不会解析出半行脏数据；
    - 文件被截断/重写（size 变小）时自动从头重读；
    - CSV 还不存在时会等待，不会报错退出（可以先开绘图、再启动采集）。

【怎么看图】
    - ①里 current 明显偏离 current_set → 恒流环异常/被限压；
    - ②贴着 24V → 被电压上限卡住；
    - ④某路出现断点 → 该温度缺测（age 超 --max-age 被丢弃）；
    - ⑤temp_age 长时间抬升 → LoRa 应答率下降，这段数据的时刻要按 (t - temp_age) 还原。

【用法】
    # 实时盯采集（CSV 不存在也会等；每 2s 刷新）
    python3 backend/tools/plot_tec_live.py tec_prbs_20260922_160000.csv

    # 自动挑当前目录下最新的 tec_prbs_*.csv
    python3 backend/tools/plot_tec_live.py --latest

    # 只看最近 20 分钟、每 5s 刷新
    python3 backend/tools/plot_tec_live.py --latest --window 20 --refresh 5

    # 无 GUI / 远程服务器上出一张静态图就退出
    python3 backend/tools/plot_tec_live.py --latest --static --save /tmp/tec_run1.png

    # 实时模式同时定期把快照写到文件（每 30s 覆盖一次），随时可看
    python3 backend/tools/plot_tec_live.py --latest --save /tmp/tec_live.png

依赖：matplotlib、pandas（仅本绘图脚本需要；采集脚本本身仍是纯标准库）。
"""

from __future__ import annotations

import argparse
import csv as _csv
import datetime as _dt
import glob
import os
import sys
import time

import pandas as pd

# ---- 默认参数 ----
REFRESH_SEC = 2.0                    # 实时刷新间隔（秒）
SAVE_EVERY_SEC = 30.0                # 实时模式下快照保存的最小间隔（秒）
DEFAULT_GLOB = "tec_prbs_*.csv"      # --latest 时用于挑最新文件的模式
DPI = 130

# ---- 列的分组与中文标签 ----
# 每个分组一个子图：(标题, 左轴列, 右轴列)
GROUPS = [
    ("电流 (A)", ["current_set", "current"], []),
    ("输出电压 (V)", ["voltage"], []),
    ("功率 (W)", ["power"], []),
    ("温度 (℃)", ["shuitong_temp", "servers_temp", "env_temp", "zhileng_temp"], []),
    ("读数滞后 (s)", ["temp_age"], ["temp_new"]),
]
LABELS = {
    "current_set": "设定电流", "current": "实际电流",
    "voltage": "输出电压", "power": "功率",
    "shuitong_temp": "热端冷却水", "servers_temp": "目标水杯",
    "env_temp": "环境室温", "zhileng_temp": "冷端风口",
    "temp_age": "读数滞后 age", "temp_new": "新值标记",
}
COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]


def setup_font():
    """中文字体：macOS/Windows/Linux 常见字体逐个试，避免标题变方框。"""
    import matplotlib
    fonts = ["PingFang SC", "PingFang HK", "Heiti TC", "Arial Unicode MS",
             "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
    matplotlib.rcParams["font.sans-serif"] = fonts + ["DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False


class CsvTailer:
    """增量读取正在被写入的 CSV：只解析新增字节，未写完的半行留到下一拍。"""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.cols = None
        self.rows = []
        self.size = 0

    def _reset(self):
        self.offset, self.cols, self.rows = 0, None, []

    def poll(self):
        """读一次新增内容；返回 (是否有新行, 文件是否存在)。"""
        try:
            st = os.stat(self.path)
        except OSError:
            return False, False
        if st.st_size < self.offset:      # 文件被截断或重新创建
            self._reset()
        if st.st_size == self.size:
            return False, True
        self.size = st.st_size
        with open(self.path, "r", encoding="utf-8", newline="") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        if not chunk:
            return False, True
        if not chunk.endswith("\n"):      # 最后一行可能只写了一半，退回等下一拍
            cut = chunk.rfind("\n")
            if cut < 0:
                self.offset -= len(chunk)
                return False, True
            self.offset -= len(chunk) - (cut + 1)
            chunk = chunk[:cut + 1]
        lines = [r for r in _csv.reader(chunk.splitlines()) if r]
        if self.cols is None:
            if not lines:
                return False, True
            self.cols = [c.strip() for c in lines[0]]
            lines = lines[1:]
        self.rows.extend(lines)
        return bool(lines), True

    def frame(self):
        """当前已读到的全部数据（DataFrame，空值→NaN）；还没有表头时返回 None。"""
        if not self.cols or not self.rows:
            return None
        df = pd.DataFrame(self.rows, columns=self.cols)
        for c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df


def last_valid(df, col):
    """取该列最后一个非空值；全空返回 None。"""
    if df is None or col not in df.columns:
        return None
    s = df[col].dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def make_figure():
    """建图：每个分组一个子图，共享 x 轴；带右轴的分组额外建 twinx。"""
    import matplotlib.pyplot as plt
    n = len(GROUPS)
    fig, axes = plt.subplots(n, 1, figsize=(12, 2.4 * n), sharex=True,
                             layout="constrained")
    twins = []
    for ax, (title, cols, alt) in zip(axes, GROUPS):
        twins.append(ax.twinx() if alt else None)
    return fig, axes, twins


def draw(fig, axes, twins, df, window_min, tailer, exists, stale_note):
    """把当前 DataFrame 画到各子图；df 为空/文件未出现时显示等待提示。"""
    x = None
    if df is not None and not df.empty:
        x = (df["t"].values / 60.0) if "t" in df.columns else None
        if x is None:
            x = pd.RangeIndex(len(df)).values / 60.0
    mask = None
    if x is not None and len(x) and window_min > 0:
        mask = x >= (x[-1] - window_min)

    for i, (title, cols, alt) in enumerate(GROUPS):
        ax, ax2 = axes[i], twins[i]
        ax.clear()
        if ax2 is not None:
            ax2.clear()
        ax.set_ylabel(title, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=9)

        if x is None:
            if i == 0:
                tip = ("等待数据…（CSV：%s）" % os.path.basename(tailer.path)) if exists \
                    else ("等待 CSV 出现：%s" % tailer.path)
                ax.text(0.5, 0.5, tip, ha="center", va="center",
                        transform=ax.transAxes, fontsize=12, color="#888888")
            continue

        for j, col in enumerate(cols):                    # 左轴列
            if col not in df.columns:
                continue
            y = df[col].values
            xx, yy = (x[mask], y[mask]) if mask is not None else (x, y)
            if col == "current_set":
                ax.step(xx, yy, where="post", label=LABELS.get(col, col),
                        color=COLORS[j % len(COLORS)], lw=1.4)
            else:
                ax.plot(xx, yy, label=LABELS.get(col, col),
                        color=COLORS[j % len(COLORS)], lw=1.2,
                        marker="." if len(xx) <= 120 else None, ms=3)

        if ax2 is not None:                               # 右轴列（temp_new）
            for j, col in enumerate(alt):
                if col not in df.columns:
                    continue
                y = df[col].values
                xx, yy = (x[mask], y[mask]) if mask is not None else (x, y)
                ax2.step(xx, yy, where="post", label=LABELS.get(col, col),
                         color="#7f7f7f", lw=1.0, alpha=0.8)
            ax2.set_ylim(-0.15, 1.15)
            ax2.set_yticks([0, 1])
            ax2.set_ylabel("新值?", fontsize=9)
            ax2.tick_params(labelsize=9)

        if cols or alt:
            h1, l1 = ax.get_legend_handles_labels()
            if ax2 is not None:
                h2, l2 = ax2.get_legend_handles_labels()
                h1, l1 = h1 + h2, l1 + l2
            if h1:
                ax.legend(h1, l1, loc="upper left", fontsize=8, ncol=3, framealpha=0.6)

    axes[-1].set_xlabel("时间 (min)", fontsize=10)
    if x is not None and len(x):
        axes[-1].set_xlim(max(0.0, x[0]), max(x[-1], x[0] + 1e-6))
        fig.suptitle(status_line(df, tailer, exists, stale_note), fontsize=10)
    else:
        fig.suptitle("TEC PRBS 实时监视 —— %s%s" % (os.path.basename(tailer.path), stale_note),
                     fontsize=10)


def status_line(df, tailer, exists, stale_note):
    """顶部状态行：样本数、时刻、最新关键读数（缺测显示 --）。"""
    def g(col, fmt="%.2f"):
        v = last_valid(df, col)
        return "--" if v is None else (fmt % v)

    tsec = last_valid(df, "t")
    parts = [
        "样本 %d" % (0 if df is None else len(df)),
        "t=%s min" % ("--" if tsec is None else "%.1f" % (tsec / 60.0)),
        "set=%sA cur=%sA" % (g("current_set"), g("current")),
        "V=%s P=%sW" % (g("voltage"), g("power")),
        "水杯=%s℃" % g("servers_temp"),
        "冷却水=%s℃" % g("shuitong_temp"),
        "风口=%s℃" % g("zhileng_temp"),
        "age=%ss" % g("temp_age", "%.0f"),
    ]
    return "TEC PRBS 实时监视 | " + " | ".join(parts) + stale_note


def pick_path(args):
    """确定要监视的 CSV 路径：显式给出 / --latest 自动挑最新。"""
    if args.csv:
        return os.path.abspath(args.csv)
    pattern = os.path.join(os.path.abspath(args.dir), args.glob)
    hits = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if not hits:
        raise SystemExit("在 %s 下没找到匹配 %s 的文件（可直接给出 CSV 路径）"
                         % (os.path.abspath(args.dir), args.glob))
    return max(hits, key=os.path.getmtime)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="TEC PRBS 采集数据实时可视化（所有列分屏画图）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("csv", nargs="?", default=None,
                   help="要监视的 CSV 路径（不给则用 --latest 自动挑最新的）")
    p.add_argument("--latest", action="store_true",
                   help="自动挑 --dir 下匹配 --glob 的最新文件")
    p.add_argument("--dir", default=".", help="--latest 时搜索的目录")
    p.add_argument("--glob", default=DEFAULT_GLOB, help="--latest 时匹配的文件名模式")
    p.add_argument("--refresh", type=float, default=REFRESH_SEC, help="实时刷新间隔（秒）")
    p.add_argument("--window", type=float, default=0.0,
                   help="只显示最近 N 分钟（0=显示全部）")
    p.add_argument("--save", default=None,
                   help="图片输出路径：--static 时保存后退出；实时模式每 %.0fs 覆盖一次" % SAVE_EVERY_SEC)
    p.add_argument("--static", action="store_true",
                   help="静态模式：画一帧存盘后退出（无 GUI / 远程服务器用）")
    p.add_argument("--dpi", type=int, default=DPI, help="存图分辨率")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.refresh <= 0:
        raise SystemExit("参数错误：--refresh 必须 > 0")

    import matplotlib
    if args.static:
        matplotlib.use("Agg")          # 无显示环境也能出图
    setup_font()
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    path = pick_path(args)
    tailer = CsvTailer(path)
    fig, axes, twins = make_figure()
    state = {"last_change": time.time(), "last_save": 0.0}

    log = lambda m: print("[%s] %s" % (_dt.datetime.now().strftime("%H:%M:%S"), m), flush=True)
    log("监视 CSV：%s（%s）" % (path, "静态" if args.static else "每 %.1fs 刷新" % args.refresh))
    if args.save:
        log("图片输出：%s" % os.path.abspath(args.save))

    def update(_frame):
        new, exists = tailer.poll()
        now = time.time()
        if new:
            state["last_change"] = now
        idle = now - state["last_change"]
        stale_note = ""
        if exists and idle > max(30.0, 5.0 * args.refresh):
            stale_note = "  ⚠ %.0fs 无新数据" % idle
        draw(fig, axes, twins, tailer.frame(), args.window, tailer, exists, stale_note)
        if args.save and (args.static or now - state["last_save"] >= SAVE_EVERY_SEC):
            try:
                fig.savefig(args.save, dpi=args.dpi)
                state["last_save"] = now
            except Exception as e:  # noqa: BLE001
                log("存图失败：%s" % e)
        return axes

    if args.static:
        update(0)
        if not args.save:
            raise SystemExit("--static 需要同时给出 --save（否则图没地方去）")
        log("已保存静态图：%s" % os.path.abspath(args.save))
        return 0

    anim = FuncAnimation(fig, update, interval=args.refresh * 1000,  # noqa: F841
                         blit=False, cache_frame_data=False)
    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    log("已退出监视")
    return 0


if __name__ == "__main__":
    sys.exit(main())
