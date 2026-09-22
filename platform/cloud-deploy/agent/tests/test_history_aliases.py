"""云端 agent「历史查询名称等价写法」回归测试（/api/history → TDengine）。

覆盖坑：K8s 资源名会把下划线规范成中划线（flow_meter → flow-meter），而 MQTT 主题用的是
原始设备名，于是时序库里同一个设备可能同时存在 `flow_meter` / `flow-meter` 两种 tag。
历史查询原来只按请求里的那一种名字拼 `device='flow_meter'`，查不到就静默返回 count=0，
表现为「这台设备没有历史数据」，实际数据一直在写（实测 device=flow_meter → 0 点，
device=flow-meter → 有数据）。

锁定行为：
1. device/instance/property 一律按 '-'↔'_' 等价变体做 IN 匹配；
2. 逗号分隔多别名（设备改名后拼接历史，如 env-temp,DR206-temp-1）；
3. 名称里的单引号转义（防注入）；
4. 返回体带 matched 字段，便于界面/日志看到实际匹配了哪些名字；
5. 缺 box 仍返回友好错误（不发 SQL）。

运行：python -m pytest platform/cloud-deploy/agent/tests/test_history_aliases.py -v
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

_AGENT_PATH = Path(__file__).resolve().parents[1] / "cloud_agent.py"
_spec = importlib.util.spec_from_file_location("cloud_agent_history_under_test", _AGENT_PATH)
agent = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = agent
_spec.loader.exec_module(agent)


class _Resp:
    """urlopen 返回对象替身：read() 返回 TDengine REST 结果。"""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def captured_sql(monkeypatch):
    """拦截 TDengine REST 调用，返回捕获到的 SQL 文本列表。"""
    sqls = []

    def _open(req, data=None, timeout=None):
        # TDengine 查询走 POST，SQL 放在 Request(data=...)（不在 urlopen 的 data 参数）
        sqls.append(((getattr(req, "data", None) or data) or b"").decode("utf-8"))
        body = {"code": 0, "desc": "", "column_meta": [["t", "TIMESTAMP", 8], ["v", "DOUBLE", 8]],
                "data": [[1789862400000, 1.5]], "rows": 1}
        return _Resp(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(agent.urllib.request, "urlopen", _open)
    return sqls


# ---------------------------------------------------------------------------
# 名称变体
# ---------------------------------------------------------------------------
def test_name_variants_swaps_dash_and_underscore():
    assert agent._name_variants("flow_meter") == ["flow_meter", "flow-meter"]
    assert agent._name_variants("flow-meter") == ["flow-meter", "flow_meter"]
    assert agent._name_variants("nt001") == ["nt001"]


def test_name_variants_comma_aliases_and_dedup():
    assert agent._name_variants("env-temp, DR206-temp-1") == ["env-temp", "env_temp", "DR206-temp-1", "DR206_temp_1"]
    # 别名与变体重叠时去重
    assert agent._name_variants("a_b,a-b") == ["a_b", "a-b"]


def test_sql_list_escapes_quote():
    assert agent._sql_list(["a'b"]) == "'a''b'"


# ---------------------------------------------------------------------------
# SQL 生成
# ---------------------------------------------------------------------------
def test_history_sql_matches_both_name_spellings(captured_sql):
    out = agent._tsdb_history(box="nt001", device="flow_meter", prop="flow_rate")
    assert out["ok"] is True and out["count"] == 1
    sql = captured_sql[-1]
    assert "device IN ('flow_meter', 'flow-meter')" in sql, sql
    assert "property IN ('flow_rate', 'flow-rate')" in sql, sql
    assert "box IN ('nt001')" in sql, sql
    assert out["matched"]["device"] == ["flow_meter", "flow-meter"]


def test_history_sql_supports_multi_alias(captured_sql):
    out = agent._tsdb_history(box="nt001", device="env-temp,DR206-temp-1")
    sql = captured_sql[-1]
    assert "device IN ('env-temp', 'env_temp', 'DR206-temp-1', 'DR206_temp_1')" in sql, sql
    assert out["matched"]["device"] == ["env-temp", "env_temp", "DR206-temp-1", "DR206_temp_1"]


def test_history_sql_escapes_quote(captured_sql):
    agent._tsdb_history(box="nt001", device="a'b")
    sql = captured_sql[-1]
    assert "device IN ('a''b', 'a''_b')" in sql or "device IN ('a''b'" in sql, sql


def test_history_default_window_is_24h_and_interval_follows_points(captured_sql):
    before = int(time.time() * 1000)
    out = agent._tsdb_history(box="nt001", points=24)
    after = int(time.time() * 1000)
    assert out["end"] >= before and out["end"] <= after
    assert abs((out["end"] - out["start"]) - 24 * 3600 * 1000) < 5000, out
    assert out["interval"] == "1h", out


def test_history_requires_box(captured_sql):
    out = agent._tsdb_history(box="")
    assert out["ok"] is False and "box" in out["error"]
    assert captured_sql == [], "缺 box 时不该发起 SQL 查询"


def test_history_points_clamped(captured_sql):
    out = agent._tsdb_history(box="nt001", points=999999)
    assert out["ok"] is True
    # points 上限 2000：24h / 2000 ≈ 43s → 按秒粒度输出
    assert out["interval"].endswith("s"), out["interval"]
