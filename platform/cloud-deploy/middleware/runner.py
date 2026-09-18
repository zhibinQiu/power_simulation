#!/usr/bin/env python3
"""能碳数据中间件入口：适配器注册中心 + 管理 API + 数据输出桥。

只有一种输出形态（adapter 完全透明）：bridge 用 paho 直发 output.broker
（服务器上即同机云端 Broker :41883），与一体机上报同一 Broker、按前缀区分，
平台经云端端点统一订阅即可取数，无需单独订阅中间件端口。

  ┌──────────────────────── 能碳数据中间件（本进程）────────────────────────┐
  │  管理 API :42084  ← 平台在此注册/启停/删除数据源                        │
  │  注册中心 registry：数据源配置持久化 + 适配器热插拔                      │
  │  适配器 adapters：mqtt（外部 Broker，含独立模拟数据源）/ 可扩展            │
  │  输出桥 bridge：标准 MQTT 数据出口（paho 直发 output.broker）            │
  └────────────────────────────────────────────────────────────────────────┘

用法：
    python runner.py --config config.json          # 运行（管理 API + 输出桥）
    python runner.py --config config.json --check  # 自检（加载配置打印摘要后退出）
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict

# 兼容直接执行（python middleware/runner.py）与包方式（python -m middleware.runner）
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from middleware.api import ManagementApi  # noqa: E402
from middleware.bridge import OutputBridge  # noqa: E402
from middleware.registry import AdapterRegistry  # noqa: E402

DEFAULT_API_PORT = 42084


def _logger(level: str = "info"):
    def log(lv: str, msg: str) -> None:
        if lv in ("error", "warn") or level != "quiet":
            print(f"{time.strftime('%H:%M:%S')} [{lv}] {msg}", file=sys.stderr, flush=True)
    return log


def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise SystemExit(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise SystemExit(f"配置必须是 JSON 对象: {path}")
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="能碳数据中间件（外部数据注册接入 → 平台订阅）")
    ap.add_argument("--config", default="config.json", help="配置文件路径（默认 ./config.json）")
    ap.add_argument("--check", action="store_true", help="自检模式：加载配置、校验、打印摘要后退出")
    ap.add_argument("--api-port", type=int, default=0, help=f"覆盖管理 API 端口（默认 {DEFAULT_API_PORT}）")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    log = _logger(str(cfg.get("log_level") or "info").lower())
    srv_cfg = cfg.get("server") or {}

    print("=" * 66, file=sys.stderr, flush=True)
    print("能碳数据中间件（外部数据源注册接入服务）", file=sys.stderr, flush=True)
    print(f"配置文件 : {os.path.abspath(args.config)}", file=sys.stderr, flush=True)

    token = str(srv_cfg.get("token") or "")

    # 1) 输出桥：paho 直发 output.broker（服务器上即同机云端 Broker :41883）
    bridge = OutputBridge(dict(cfg.get("output") or {}), logger=log)
    bst = bridge.status()
    print(f"输出 Broker : {bst['broker']}（paho 直发，与一体机数据按前缀区分）",
          file=sys.stderr, flush=True)

    # 2) 注册中心：加载并启动已注册的数据源
    registry = AdapterRegistry(args.config, bridge, log)
    res = registry.start_all()
    sources = registry.list()
    print(f"数据源     : {len(sources)} 条注册 / 已启动 {len(res['started'])} 个",
          file=sys.stderr, flush=True)
    for s in sources:
        print(f"  - [{s.get('type')}] {s.get('id')}  name={s.get('name')}  "
              f"box={s.get('box')}  {'运行中' if s['status']['running'] else '已停用'}",
              file=sys.stderr, flush=True)
    for e in res["errors"]:
        log("error", e)

    if args.check:
        print("=" * 66, file=sys.stderr, flush=True)
        registry.stop_all()
        bridge.stop()
        return 0 if not res["errors"] else 1

    # 3) 管理 API：平台在此注册/管理数据源
    api = ManagementApi(
        registry, bridge,
        host=str(srv_cfg.get("host") or "0.0.0.0"),
        port=int(args.api_port or srv_cfg.get("port") or DEFAULT_API_PORT),
        token=token, logger=log,
    )
    try:
        api.start()
    except Exception as e:  # noqa: BLE001
        log("error", f"管理 API 启动失败：{e}")

    stop_flag = threading.Event()

    def _sig(*_):
        log("info", "收到退出信号，正在优雅停止…")
        stop_flag.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except ValueError:
            pass

    print("=" * 66, file=sys.stderr, flush=True)
    last = 0.0
    while not stop_flag.is_set():
        if time.time() - last >= 60:
            b = bridge.status()
            print(f"[bridge] broker={b['broker']} connected={b['connected']} "
                  f"ok={b['publish_ok']} fail={b['publish_fail']} "
                  f"{b['last_error'] or ''}".strip(), file=sys.stderr, flush=True)
            for s in registry.list():
                st = s["status"]
                print(f"[{s.get('id')}] running={st['running']} readings={st['readings']} "
                      f"last={st['last_prop']}", file=sys.stderr, flush=True)
            last = time.time()
        stop_flag.wait(2.0)

    registry.stop_all()
    api.stop()
    bridge.stop()
    log("info", "中间件已退出")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已退出", file=sys.stderr, flush=True)
        sys.exit(130)
