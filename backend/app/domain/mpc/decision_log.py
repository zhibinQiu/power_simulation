"""决策日志：把每一次「收到反馈温度 → 判定可行性 → 下发什么档位 → 预计到多少度」落盘并回显。

为什么要单独一个模块
--------------------
MPC 的结论（16 V → 18 V、0.178 Wh）在页面上只是最终结果，中间那句「为什么不是 15 V」
「余量还剩多少」在求助时最有用，但原来完全没有留痕 —— uvicorn 只会打一行
`POST /api/mpc/plan 200`。这里把一次决策展开成几条人读的流水，同时：

- 追加写入 `backend/logs/mpc.log`（JSONL，一行一条决策，超 1 MB 滚动成 `.1`）；
- 用 `app.mpc` logger 打到进程标准输出，终端里跟着 uvicorn 日志一起滚动；
- 通过 `tail()` 回读，页面「决策日志」面板直接展示（刷新后仍在）。

日志只记「决策」，不记原始采样序列：温度曲线在数据模块里，重复记一遍只会让这里变成垃圾场。
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional

from app.core.config import APP_DIR

LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "mpc.log")
# 单文件上限：一条决策约 1~2 KB，1 MB ≈ 600~1000 次求解，够现场排查用
MAX_BYTES = 1_000_000
# 回读上限（防止前端一次要 10 万条把页面拖死）
MAX_TAIL = 500

_LOGGER = "app.mpc"


def _logger() -> logging.Logger:
    """进程内日志器：只装一个 StreamHandler，避免 --reload 反复加载时重复打印。"""
    lg = logging.getLogger(_LOGGER)
    if not getattr(lg, "_mpc_ready", False):
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
        lg.setLevel(logging.INFO)
        lg.propagate = False
        lg._mpc_ready = True  # type: ignore[attr-defined]
    return lg


def _rotate() -> None:
    try:
        if os.path.getsize(LOG_PATH) > MAX_BYTES:
            bak = LOG_PATH + ".1"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(LOG_PATH, bak)
    except OSError:
        pass


def write(kind: str, title: str, lines: List[str],
          extra: Optional[dict] = None) -> dict:
    """追加一条决策日志；返回可直接回给前端的记录（含 ts）。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    rec = {"ts": ts, "kind": kind, "title": title, "lines": [str(x) for x in lines]}
    if extra:
        rec["extra"] = extra
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _rotate()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 —— 日志写不进去绝不能影响求解
        pass
    lg = _logger()
    lg.info("[MPC %s] %s %s", kind, ts, title)
    for ln in rec["lines"]:
        lg.info("           %s", ln)
    return rec


def tail(limit: int = 100) -> List[dict]:
    """回读最近 limit 条（新→旧）。文件不存在或行损坏都安静跳过。"""
    n = max(1, min(int(limit or 100), MAX_TAIL))
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            raw = f.readlines()[-n:]
    except OSError:
        return []
    out: List[dict] = []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(rec, dict):
            out.append(rec)
    out.reverse()
    return out


def clear() -> int:
    """清空日志（页面上的「清空」按钮）；返回清掉的条数。"""
    cnt = 0
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            cnt = sum(1 for ln in f if ln.strip())
    except OSError:
        return 0
    try:
        os.remove(LOG_PATH)
    except OSError:
        pass
    return cnt


__all__ = ["LOG_PATH", "write", "tail", "clear"]
