"""云端 agent 时间解析回归测试（/api/history 的 t 字段）。

现场故障：平台「云端时序」曲线整体偏 8 小时（X 轴显示 8 小时前，数据本身没错）。
根因是 TDengine REST 返回的时间列是 RFC3339 UTC（'2026-09-11T08:21:56.719Z'），
而 agent 用 naive 的 strptime 解析 —— naive 会被当成本机时区，UTC+8 机器上就整体差
8 小时；同时 `_parse_ms` 把 10 位 epoch 秒直接当毫秒用（窗口静默变成"从 1970 年到现在"，
降采样间隔被撑到几千小时，接口不报错但曲线毫无意义）。

运行：cd platform/cloud-deploy/agent && python -m pytest tests -v
"""
import importlib.util
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parent.parent


def _load_agent():
    """按文件路径加载 cloud_agent.py（模块级会读 /opt/cloud-agent/config.json，
    无配置时走 DEFAULT_CONFIG，可在开发机直接导入）。"""
    spec = importlib.util.spec_from_file_location("nengtan_cloud_agent", AGENT_DIR / "cloud_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ag():
    return _load_agent()


def test_rfc3339_z_is_parsed_as_utc_not_local(ag):
    """'...Z' 是 UTC 标记，必须按 UTC 解析，与本机时区无关（这是 8 小时偏移的根因）。"""
    got = ag._td_ts_ms("2026-09-11T08:21:56.719Z")
    want = int(datetime(2026, 9, 11, 8, 21, 56, 719000, tzinfo=timezone.utc).timestamp() * 1000)
    assert got == want


def test_history_bucket_matches_real_epoch_not_shifted_by_tz(ag):
    """回归：曲线时间戳就是真实 epoch；旧实现会差正好一个本机时区偏移（UTC+8 即 8 小时）。"""
    now_ms = int(time.time() * 1000)
    s = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert abs(ag._td_ts_ms(s) - now_ms) < 2000

    # 复现旧实现：把 UTC 串 naive 解析成本机时间 → 偏移量恰等于本机时区偏移
    naive = int(datetime.strptime(s.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    local_offset_h = (datetime.fromtimestamp(now_ms / 1000)
                      - datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(tzinfo=None)
                      ).total_seconds() / 3600
    assert abs((now_ms - naive) / 3600000 - local_offset_h) < 0.01


def test_explicit_offset_is_respected(ag):
    """带 ±HH:MM 偏移的串按偏移解析（不依赖本机时区）。"""
    a = ag._td_ts_ms("2026-09-11T16:21:56+08:00")
    b = ag._td_ts_ms("2026-09-11T08:21:56Z")
    assert abs(a - b) < 1000


def test_naive_string_uses_local_timezone(ag):
    """无时区标记的串（历史格式）按本机时区解析，行为与旧版一致。"""
    got = ag._td_ts_ms("2026-09-11 16:21:56")
    want = int(datetime(2026, 9, 11, 16, 21, 56).timestamp() * 1000)
    assert got == want


def test_epoch_seconds_are_never_taken_as_milliseconds(ag):
    """10 位 epoch 秒必须归一化成毫秒：当毫秒用会让查询窗口变成"从 1970 到现在"。"""
    sec = "1789114541"
    assert ag._parse_ms(sec) == 1789114541000
    assert ag._td_ts_ms(sec) == 1789114541000
    assert ag._td_ts_ms(1789114541000) == 1789114541000        # 数字型毫秒原样
    assert ag._td_ts_ms("1789114541.0") == 1789114541000       # 数字字符串


def test_garbage_and_empty_are_zero_not_crash(ag):
    """空/非法时间一律归 0（前端据 0 显示占位），绝不抛异常打断查询。"""
    for bad in (None, "", "   ", "not-a-time", True, {}, "2026-13-45 99:99:99"):
        assert ag._td_ts_ms(bad) == 0
        assert ag._parse_ms(bad) == 0


def test_long_fraction_is_truncated_not_rejected(ag):
    """小数秒超过 6 位（部分 TDengine 版本会返回）不能整条丢弃成 0。"""
    got = ag._td_ts_ms("2026-09-11T08:21:56.123456789Z")
    assert got == ag._td_ts_ms("2026-09-11T08:21:56.123456Z")
