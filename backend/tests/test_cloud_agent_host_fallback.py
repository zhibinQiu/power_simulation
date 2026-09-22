"""云端 agent「候选地址回退」回归测试（backend）。

覆盖坑：平台与云端不同机时，cloud.host=172.18.0.1（docker 网关语义，仅平台容器与云端
同机时成立）在开发机上必然 Connection refused，于是历史查询 / 一键下发全部报
「云端 agent 不可达（172.18.0.1:42083）」；而 broker.host 指向的云端地址同端口的 agent
其实完全可达（MQTT 实时数据正是经它进来的）。

锁定行为：
1. 候选顺序 = 记忆的生效地址 → cloud.host → broker.host → 默认（去重）；
2. 首选失败自动回退到下一个候选，成功者被记忆（后续请求直接命中，不再吃一次失败连接）；
3. 失败候选进冷却，避免每个请求都在不可达地址上重复等待超时；
4. 全部失败时错误信息汇总各候选原因；未配置 token 时不发请求；
5. health() 暴露 active_host / candidates 便于诊断。

运行：cd backend && python -m pytest tests/test_cloud_agent_host_fallback.py -v
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations import cloud_agent  # noqa: E402

DOCKER_GW = "172.18.0.1"       # 生产容器内由 core/netinfo.gateway_host() 推导出的 docker 网关
PUBLIC = "36.151.146.71"       # 配置里的公网地址（cloud.host / broker.host）


class _Resp:
    """urlopen 返回对象的最小替身（上下文管理器 + read）。"""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _cfg(host: str = DOCKER_GW, token: str = "t0ken") -> dict:
    return {"host": host, "agent_port": 42083, "agent_token": token, "namespace": "default"}


def _fake_urlopen(calls, fail_hosts, payload=b'{"ok": true}'):
    """构造 urlopen 替身：命中 fail_hosts 的地址抛 Connection refused，其余返回 payload。"""

    def _open(req, data=None, timeout=None):
        url = getattr(req, "full_url", str(req))
        calls.append(url)
        for h in fail_hosts:
            if f"://{h}:" in url:
                raise ConnectionRefusedError(f"[Errno 61] Connection refused ({h})")
        return _Resp(payload)

    return _open


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """每个用例重置「生效地址 / 冷却」状态，并把 broker.host 固定为公网地址。"""
    monkeypatch.setattr(cloud_agent, "_active_host", {"host": "", "ts": 0.0})
    monkeypatch.setattr(cloud_agent, "_fail_until", {})
    monkeypatch.setattr(cloud_agent, "_broker_host", lambda: PUBLIC)
    # 默认模拟「开发机」：无 docker 网关（/proc/net/route 不存在）→ 该候选跳过
    monkeypatch.setattr(cloud_agent, "gateway_host", lambda: "")
    yield


# ---------------------------------------------------------------------------
# 候选地址
# ---------------------------------------------------------------------------
def test_candidates_order_and_dedup(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    assert cloud_agent.candidate_hosts() == [DOCKER_GW, PUBLIC]


def test_candidates_broker_fallback_when_cloud_host_empty(monkeypatch):
    """cloud.host 未配（或为空）时，候选应落到 broker.host 与运行时推导的宿主网关。"""
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg(host=""))
    monkeypatch.setattr(cloud_agent, "gateway_host", lambda: DOCKER_GW)
    assert cloud_agent.candidate_hosts() == [PUBLIC, DOCKER_GW]


def test_candidates_skip_empty_gateway(monkeypatch):
    """开发机推导不出网关（/proc/net/route 不存在）时，候选里不该出现空串地址。"""
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    assert cloud_agent.candidate_hosts() == [DOCKER_GW, PUBLIC]


def test_active_host_comes_first(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    monkeypatch.setattr(cloud_agent, "_active_host", {"host": PUBLIC, "ts": time.time()})
    cands = cloud_agent.candidate_hosts()
    assert cands[0] == PUBLIC, f"生效地址应优先，实际 {cands}"
    assert DOCKER_GW in cands


def test_stale_active_host_ignored(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    monkeypatch.setattr(cloud_agent, "_active_host",
                        {"host": PUBLIC, "ts": time.time() - cloud_agent._ACTIVE_HOST_TTL - 1})
    assert cloud_agent.candidate_hosts()[0] == DOCKER_GW


# ---------------------------------------------------------------------------
# 回退 / 记忆 / 冷却
# ---------------------------------------------------------------------------
def test_http_falls_back_to_broker_host(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    calls = []
    monkeypatch.setattr(cloud_agent.urllib.request, "urlopen",
                        _fake_urlopen(calls, fail_hosts=[DOCKER_GW], payload=b'{"ok": true, "v": 1}'))

    ok, data, err = cloud_agent._http("/api/health")
    assert ok and data == {"ok": True, "v": 1} and err == ""
    assert cloud_agent.active_host() == PUBLIC, "回退成功应记忆生效地址"
    assert any(f"://{DOCKER_GW}:" in u for u in calls) and any(f"://{PUBLIC}:" in u for u in calls)
    assert DOCKER_GW in cloud_agent._fail_until, "失败候选应进冷却"


def test_http_reuses_active_host_after_fallback(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    calls = []
    monkeypatch.setattr(cloud_agent.urllib.request, "urlopen",
                        _fake_urlopen(calls, fail_hosts=[DOCKER_GW]))
    cloud_agent._http("/api/health")
    calls.clear()

    ok, _, _ = cloud_agent._http("/api/health")
    assert ok
    assert all(f"://{PUBLIC}:" in u for u in calls), f"冷却期内不该再试不可达地址：{calls}"


def test_http_probe_again_when_all_candidates_cooled(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    monkeypatch.setattr(cloud_agent, "_fail_until",
                        {DOCKER_GW: time.time() + 30, PUBLIC: time.time() + 30})
    calls = []
    monkeypatch.setattr(cloud_agent.urllib.request, "urlopen",
                        _fake_urlopen(calls, fail_hosts=[]))
    ok, _, _ = cloud_agent._http("/api/health")
    assert ok, "全部候选冷却时仍应探测首选，避免错误信息永久滞后"
    assert any(f"://{DOCKER_GW}:" in u for u in calls), calls


def test_http_all_failed_reports_every_candidate(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    calls = []
    monkeypatch.setattr(cloud_agent.urllib.request, "urlopen",
                        _fake_urlopen(calls, fail_hosts=[DOCKER_GW, PUBLIC]))
    ok, data, err = cloud_agent._http("/api/health")
    assert ok is False and data is None
    assert DOCKER_GW in err and PUBLIC in err, f"错误应汇总各候选原因，实际：{err}"


def test_http_requires_token(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg(token=""))

    def _boom(*a, **k):
        raise AssertionError("未配置 token 时不应发起请求")

    monkeypatch.setattr(cloud_agent.urllib.request, "urlopen", _boom)
    ok, _, err = cloud_agent._http("/api/health")
    assert ok is False and "agent_token" in err


# ---------------------------------------------------------------------------
# health 诊断信息
# ---------------------------------------------------------------------------
def test_health_exposes_active_host_and_candidates(monkeypatch):
    monkeypatch.setattr(cloud_agent, "agent_cfg", lambda: _cfg())
    monkeypatch.setattr(cloud_agent, "_http", lambda *a, **k: (True, {"version": "1.1"}, ""))
    out = cloud_agent.health()
    assert out["ok"] is True
    assert PUBLIC in out["candidates"] and DOCKER_GW in out["candidates"]
    assert isinstance(out["active_host"], str)
