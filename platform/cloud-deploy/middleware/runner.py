#!/usr/bin/env python3
"""能碳数据中间件入口：适配器注册中心 + 管理 API + 数据输出桥。

两种部署形态（output.mode 决定，适配器对两种形态完全透明）：
  ┌──────────────────────── 能碳数据中间件（本进程）────────────────────────┐
  │  管理 API :42084  ← 平台在此注册/启停/删除数据源                        │
  │  注册中心 registry：数据源配置持久化 + 适配器热插拔                      │
  │  适配器 adapters：mqtt（外部 Broker，含独立模拟数据源）/ 可扩展            │
  │  输出桥 bridge：标准 MQTT 数据出口                                     │
  └────────────────────────────────────────────────────────────────────────┘
  · mode=local    —— 内置 Broker(:41884) 随本进程启动，bridge 进程内直投；
                     平台单独订阅中间件端口取外部数据（默认，零网络跳）。
  · mode=external —— 不起内置 Broker，bridge 用 paho 直发外部 Broker
                     （如与服务器原云端 Broker 同机 :41883），与一体机数据
                     同一 Broker 上按前缀区分；平台无需单独订阅中间件。
  server.broker.enabled 可显式开关内置 Broker（local 模式必启）。

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
from middleware.broker import MiniBroker  # noqa: E402
from middleware.bridge import OutputBridge  # noqa: E402
from middleware.registry import AdapterRegistry  # noqa: E402

DEFAULT_BROKER_PORT = 41884
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
    ap.add_argument("--broker-port", type=int, default=0, help=f"覆盖内置 Broker 端口（默认 {DEFAULT_BROKER_PORT}）")
    ap.add_argument("--api-port", type=int, default=0, help=f"覆盖管理 API 端口（默认 {DEFAULT_API_PORT}）")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    log = _logger(str(cfg.get("log_level") or "info").lower())
    srv_cfg = cfg.get("server") or {}
    bkr_cfg = srv_cfg.get("broker") or {}

    print("=" * 66, file=sys.stderr, flush=True)
    print("能碳数据中间件（外部数据源注册接入服务）", file=sys.stderr, flush=True)
    print(f"配置文件 : {os.path.abspath(args.config)}", file=sys.stderr, flush=True)

    # 1) 输出模式：local=进程内直投内置 Broker；external=直发外部 Broker（如云端 41883）
    out_cfg = dict(cfg.get("output") or {})
    if not out_cfg.get("mode"):
        out_cfg["mode"] = "local"
    mode = out_cfg["mode"]

    # 2) 内置 Broker（可选）：local 模式必须启用；external 模式默认不启用，
    #    可经 server.broker.enabled 显式覆盖（少见）
    token = str(srv_cfg.get("token") or "")
    if mode == "local":
        broker_enabled = True
    elif bkr_cfg.get("enabled") is not None:
        broker_enabled = bool(bkr_cfg.get("enabled"))
    else:
        broker_enabled = False
    broker = None
    if broker_enabled:
        broker = MiniBroker(
            host=str(bkr_cfg.get("host") or "0.0.0.0"),
            port=int(args.broker_port or bkr_cfg.get("port") or DEFAULT_BROKER_PORT),
            token=str(bkr_cfg.get("token") or token),
            logger=log,
        )
        broker.start()
        bst = broker.status()
        print(f"内置 Broker : {bst['host']}:{bst['port']} "
              f"{'已监听' if bst['running'] else '启动失败 - ' + str(bst['last_error'])}",
              file=sys.stderr, flush=True)
    else:
        print(f"内置 Broker : 未启用（output.mode={mode}，转换数据直发外部 Broker）",
              file=sys.stderr, flush=True)

    # 3) 输出桥：local 模式进程内直投内置 Broker；external 模式用 paho 直发外部 Broker
    bridge = OutputBridge(out_cfg, local_broker=broker if mode == "local" else None,
                          logger=log)

    # 4) 注册中心：加载并启动已注册的数据源
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
        if broker is not None:
            broker.stop()
        return 0 if not res["errors"] else 1

    # 5) 管理 API：平台在此注册/管理数据源
    api = ManagementApi(
        registry, broker, bridge,
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
            print(f"[bridge] mode={b['mode']} ok={b['publish_ok']} fail={b['publish_fail']} "
                  f"{b['last_error'] or ''}".strip(), file=sys.stderr, flush=True)
            if broker is not None:
                bk = broker.status()
                print(f"[broker] clients={bk['clients']} subs={bk['subscriptions']} "
                      f"published={bk['published']}", file=sys.stderr, flush=True)
            for s in registry.list():
                st = s["status"]
                print(f"[{s.get('id')}] running={st['running']} readings={st['readings']} "
                      f"last={st['last_prop']}", file=sys.stderr, flush=True)
            last = time.time()
        stop_flag.wait(2.0)

    registry.stop_all()
    api.stop()
    if broker is not None:
        broker.stop()
    log("info", "中间件已退出")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已退出", file=sys.stderr, flush=True)
        sys.exit(130)
