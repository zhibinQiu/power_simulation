"""配置变更广播中心（单一数据源 → 多客户端实时同步）。

设计前提：**配置文件只在服务端保存一份**（backend/config/*.json），客户端不持有副本、
不做本地持久化，界面数据一律来自后端接口。由此带来两个必须解决的问题：

1. 任一客户端经 API 改动配置后，其它已打开的客户端要能看到（不能各自停留在旧数据）；
2. 配置可能在别的进程被改动（uvicorn 多 worker、运维手工编辑 json、部署脚本 rsync），
   本进程收不到任何函数调用，也要能感知。

本模块同时解决两者：
- ``publish(scope, rev)``：写盘方主动广播（同步线程可安全调用，经 asyncio.Queue 分发）；
- ``watch_file(path, scope)``：按文件指纹（mtime_ns + size）轮询兜底，发现文件被别处
  改动即广播，覆盖跨进程与手工编辑场景。

消费方是 WebSocket 端点（见 box_router ``/api/ws/config``）；前端收到事件后重新拉取
对应接口即可，不需要把配置内容本身塞进推送消息（避免大包与越权暴露）。
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Dict, Set

# WebSocket 订阅者队列（asyncio.Queue；同步线程 put_nowait 线程安全）
_QUEUES: Set[Any] = set()
_LOCK = threading.Lock()

# 文件监听任务：key = f"{scope}::{path}"，引用计数式启停（最后一个订阅者断开才取消）
_WATCH_TASKS: Dict[str, asyncio.Task] = {}
_WATCH_REFS: Dict[str, int] = {}


# ------------------------- 订阅 / 广播 -------------------------

def subscribe(q: Any) -> None:
    with _LOCK:
        _QUEUES.add(q)


def unsubscribe(q: Any) -> None:
    with _LOCK:
        _QUEUES.discard(q)


def publish(scope: str, rev: Any, **extra: Any) -> None:
    """广播一次配置变更（scope 如 'devices'；rev 为文件版本号/指纹）。

    可从任意线程调用（写盘发生在请求线程或 MQTT 后台线程），无订阅者时直接返回。
    """
    with _LOCK:
        queues = list(_QUEUES)
    if not queues:
        return
    payload = {"kind": "config", "scope": scope, "rev": rev, "ts": time.time()}
    if extra:
        payload.update(extra)
    for q in queues:
        try:
            q.put_nowait(payload)
        except Exception:  # noqa: BLE001 —— 单个订阅者队列满/已关闭不影响其它订阅者
            pass


# ------------------------- 文件指纹（版本号） -------------------------

def rev_of(path: str) -> Any:
    """配置文件当前版本号 = 文件指纹；文件不存在返回 0（前端据此判定「配置为空」）。"""
    try:
        st = os.stat(path)
        return st.st_mtime_ns
    except OSError:
        return 0


# ------------------------- 跨进程兜底：文件指纹轮询 -------------------------

async def _watch_loop(path: str, scope: str, interval: float) -> None:
    last = rev_of(path)
    while True:
        await asyncio.sleep(interval)
        try:
            rev = rev_of(path)
            if rev != last:
                last = rev
                # source=file：变更来自「非本进程写盘」路径（多 worker / 手工编辑 / 部署同步）
                publish(scope, rev, source="file")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 —— 监听失败不影响连接本身
            pass


def acquire_watch(path: str, scope: str, interval: float = 2.0) -> None:
    """为当前事件循环登记一个文件监听（引用计数，重复调用只起一个任务）。

    必须在协程内调用（需要 running loop）；无事件循环时静默跳过（不影响业务）。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = f"{scope}::{path}"
    with _LOCK:
        _WATCH_REFS[key] = _WATCH_REFS.get(key, 0) + 1
        if key not in _WATCH_TASKS:
            _WATCH_TASKS[key] = loop.create_task(_watch_loop(path, scope, interval))


def release_watch(path: str, scope: str) -> None:
    """释放一个监听引用；归零时取消任务。"""
    key = f"{scope}::{path}"
    with _LOCK:
        left = _WATCH_REFS.get(key, 0) - 1
        if left > 0:
            _WATCH_REFS[key] = left
            return
        _WATCH_REFS.pop(key, None)
        task = _WATCH_TASKS.pop(key, None)
    if task is not None:
        task.cancel()


def _reset_for_test() -> None:
    """测试用：清空订阅者与监听任务。"""
    with _LOCK:
        _QUEUES.clear()
        tasks = list(_WATCH_TASKS.values())
        _WATCH_TASKS.clear()
        _WATCH_REFS.clear()
    for t in tasks:
        t.cancel()


def queue_count() -> int:
    """当前订阅者数量（测试/诊断用）。"""
    with _LOCK:
        return len(_QUEUES)


def watch_task_count() -> int:
    with _LOCK:
        return len(_WATCH_TASKS)


__all__ = [
    "subscribe", "unsubscribe", "publish", "rev_of",
    "acquire_watch", "release_watch", "queue_count", "watch_task_count",
    "_reset_for_test",
]
