"""配置单一数据源 + 多客户端同步：仓储缓存失效 与 变更广播。

覆盖三条语义：
1. 磁盘文件是唯一真相：别的进程 / 运维手工改动 json 后，read() 必须看到新内容；
2. 写盘即广播：任一客户端改配置后，所有 WebSocket 订阅者收到 config 事件；
3. 跨进程兜底：文件指纹监听发现「非本进程写盘」的改动也要广播。
"""
import asyncio
import json
import os
import time

from app.core import config_events
from app.core.storage import JsonRepository


# ------------------------- 1. 仓储缓存以文件指纹失效 -------------------------

def test_repo_reads_external_file_change(tmp_path):
    """别的进程/手工编辑文件后，缓存必须自动失效（不是重启才生效）。"""
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"v": 1}), encoding="utf-8")
    repo = JsonRepository(str(p), default={})
    assert repo.read()["v"] == 1

    # 模拟「另一个进程写盘 / 运维手工编辑」
    p.write_text(json.dumps({"v": 2}), encoding="utf-8")
    os.utime(p, (time.time() + 1, time.time() + 1))
    assert repo.read()["v"] == 2, "外部改动文件后仍返回旧缓存 = 配置出现多份真相"


def test_repo_cache_hit_when_file_unchanged(tmp_path):
    """文件未变时走缓存（不重复读盘）：same object 身份相同。"""
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"v": 1}), encoding="utf-8")
    repo = JsonRepository(str(p), default={})
    first = repo.read()
    assert repo.read() is first


def test_repo_write_updates_fingerprint(tmp_path):
    """本进程写盘后缓存与指纹同步，读到刚写入的内容。"""
    p = tmp_path / "cfg.json"
    repo = JsonRepository(str(p), default={})
    repo.write({"v": 9})
    assert repo.read()["v"] == 9
    assert json.loads(p.read_text(encoding="utf-8"))["v"] == 9


# ------------------------- 2. 变更广播 -------------------------

def test_publish_fans_out_to_all_subscribers():
    config_events._reset_for_test()
    q1, q2 = asyncio.Queue(), asyncio.Queue()
    config_events.subscribe(q1)
    config_events.subscribe(q2)
    try:
        assert config_events.queue_count() == 2
        config_events.publish("devices", 123, source="api")
        for q in (q1, q2):
            msg = q.get_nowait()
            assert msg["kind"] == "config"
            assert msg["scope"] == "devices"
            assert msg["rev"] == 123
            assert msg["source"] == "api"
    finally:
        config_events.unsubscribe(q1)
        config_events.unsubscribe(q2)
        config_events._reset_for_test()


def test_publish_without_subscriber_is_noop():
    config_events._reset_for_test()
    config_events.publish("devices", 1)   # 不应抛异常


def test_rev_of_missing_file():
    assert config_events.rev_of("/nonexistent/path/cfg.json") == 0


def test_rev_tracks_file_change(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text("{}", encoding="utf-8")
    rev1 = config_events.rev_of(str(p))
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert config_events.rev_of(str(p)) != rev1


def test_save_devices_broadcasts(tmp_path, monkeypatch):
    """写盘路径（/api/box/devices 等）保存后必须广播，其它客户端才能同步。"""
    from app.box_console import _shared

    config_events._reset_for_test()
    q: asyncio.Queue = asyncio.Queue()
    config_events.subscribe(q)
    # 设备配置重定向到临时文件，避免污染真实 backend/config/box_devices.json
    monkeypatch.setattr(_shared, "_devices_repo",
                        JsonRepository(str(tmp_path / "box_devices.json"),
                                       default={"models": [], "devices": []}))
    monkeypatch.setattr(_shared, "DEVICES_FILE", tmp_path / "box_devices.json")
    try:
        _shared._save_devices({"models": [], "devices": [{"deviceName": "d1"}]})
        msg = q.get_nowait()
        assert msg["scope"] == "devices"
        assert msg["source"] == "api"
        assert isinstance(msg["rev"], int)
    finally:
        config_events._reset_for_test()


# ------------------------- 3. 跨进程兜底：文件指纹监听 -------------------------

def test_file_watch_broadcasts_external_change(tmp_path):
    """非本进程改动（多 worker / 手工编辑）也要被监听发现并广播。"""
    config_events._reset_for_test()
    p = tmp_path / "cfg.json"
    p.write_text("{}", encoding="utf-8")

    async def scenario():
        q: asyncio.Queue = asyncio.Queue()
        config_events.subscribe(q)
        config_events.acquire_watch(str(p), "devices", 0.05)
        try:
            assert config_events.watch_task_count() == 1
            # 引用计数：重复登记只起一个任务
            config_events.acquire_watch(str(p), "devices", 0.05)
            assert config_events.watch_task_count() == 1
            # 监听以「启动时刻的文件指纹」为基线：先让它跑一轮再改动文件
            await asyncio.sleep(0.1)
            os.utime(p, (time.time() + 10, time.time() + 10))
            msg = await asyncio.wait_for(q.get(), timeout=2.0)
            assert msg["scope"] == "devices"
            assert msg["source"] == "file"
        finally:
            config_events.release_watch(str(p), "devices")
            config_events.release_watch(str(p), "devices")
            config_events._reset_for_test()

    asyncio.run(scenario())
