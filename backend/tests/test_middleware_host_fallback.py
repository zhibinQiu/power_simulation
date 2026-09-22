"""中间件连接「候选地址回退」回归测试（backend/app/middleware_client.py）。

背景（用户诉求）：配置里不要写局域网/本地地址。中间件 base_url 因此只写可移植的公网
地址（http://36.151.146.71:42084），而平台容器访问同机宿主服务需要 docker 网关，于是
由 core.netinfo.gateway_host() 运行时推导，作为最后一个候选。

锁定行为：
1. 候选顺序 = 记忆的生效地址 → 配置 base_url → 同机 Broker 主机:42084 → 宿主网关:42084（去重、
   空值跳过）；
2. **只有连接层失败才回退**（连接失败记忆成功的候选并冷却失败的候选）；
3. **业务错误绝不回退重试**（HTTP 4xx/5xx 或 ok=false，如「数据源不存在」）——否则写操作
   会在下一个候选地址上被执行两次；
4. 全部候选连接失败时给出汇总错误。

运行：cd backend && python -m pytest tests/test_middleware_host_fallback.py -v
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations import middleware_client as mw  # noqa: E402

PUBLIC = "http://36.151.146.71:42084"    # 配置里的公网地址
BROKER = "http://36.151.146.71:42084"    # 与 PUBLIC 同主机 → 用于验证去重
GATEWAY = "http://172.18.0.1:42084"      # 容器内推导出的宿主网关（生产形态）


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakeClient:
    """按 URL 的 base 决定行为：("conn", None) 抛连接异常，("resp", payload[, status]) 返回。"""

    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append(url)
        base = url.split("/api/")[0]
        kind, *rest = self.behavior.get(base, ("conn", None))
        if kind == "conn":
            raise ConnectionError(f"[Errno 61] Connection refused ({base})")
        return _Resp(rest[0], rest[1] if len(rest) > 1 else 200)


def _install(monkeypatch, behavior):
    fake = _FakeClient(behavior)
    monkeypatch.setattr(mw, "_client", fake)
    return fake


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(mw, "_active_base", {"url": "", "ts": 0.0})
    monkeypatch.setattr(mw, "_fail_until", {})
    monkeypatch.setattr(mw, "load_config",
                        lambda: {"enabled": True, "base_url": PUBLIC, "token": "t0k", "timeout": 3.0})
    monkeypatch.setattr(mw, "_broker_base", lambda: BROKER)
    monkeypatch.setattr(mw, "_gateway_base", lambda: GATEWAY)
    mw.reset_cache()   # 读接口有 TTL 缓存，逐用例清空
    yield
    mw.reset_cache()


# ---------------------------------------------------------------------------
# 候选地址
# ---------------------------------------------------------------------------
def test_base_candidates_order_and_dedup():
    # PUBLIC 与 BROKER 同主机 → 去重后只剩公网 + 网关
    assert mw.base_candidates() == [PUBLIC, GATEWAY]


def test_base_candidates_skip_empty_gateway(monkeypatch):
    """开发机推导不出 docker 网关（/proc/net/route 不存在）时不该出现空串地址。"""
    monkeypatch.setattr(mw, "_gateway_base", lambda: "")
    assert mw.base_candidates() == [PUBLIC]


def test_base_candidates_active_first(monkeypatch):
    monkeypatch.setattr(mw, "_active_base", {"url": GATEWAY, "ts": time.time()})
    assert mw.base_candidates()[0] == GATEWAY


def test_base_candidates_stale_active_ignored(monkeypatch):
    monkeypatch.setattr(mw, "_active_base",
                        {"url": GATEWAY, "ts": time.time() - mw._ACTIVE_TTL - 1})
    assert mw.base_candidates()[0] == PUBLIC


# ---------------------------------------------------------------------------
# 回退 / 记忆 / 冷却
# ---------------------------------------------------------------------------
def test_request_falls_back_to_gateway(monkeypatch):
    fake = _install(monkeypatch, {PUBLIC: ("conn", None),
                                  GATEWAY: ("resp", {"ok": True, "value": 7})})
    out = mw._request("GET", "/api/status")
    assert out == {"ok": True, "value": 7}
    assert mw.active_base_url() == GATEWAY, "回退成功应记忆生效地址"
    assert any(u.startswith(PUBLIC) for u in fake.calls) and any(u.startswith(GATEWAY) for u in fake.calls)
    assert PUBLIC in mw._fail_until, "连接失败的候选应进冷却"


def test_request_reuses_active_base(monkeypatch):
    fake = _install(monkeypatch, {PUBLIC: ("conn", None),
                                  GATEWAY: ("resp", {"ok": True})})
    mw._request("GET", "/api/status")
    fake.calls.clear()
    mw._request("GET", "/api/status")
    assert all(u.startswith(GATEWAY) for u in fake.calls), f"冷却期内不该再试不可达地址：{fake.calls}"


# ---------------------------------------------------------------------------
# 业务错误绝不回退（防止写操作被重复执行）
# ---------------------------------------------------------------------------
def test_business_error_does_not_fallback(monkeypatch):
    fake = _install(monkeypatch, {PUBLIC: ("resp", {"ok": False, "error": "数据源不存在"}),
                                  GATEWAY: ("resp", {"ok": True})})
    with pytest.raises(mw.MiddlewareError) as ei:
        mw._request("POST", "/api/sources/delete", {"id": "s1"})
    assert "数据源不存在" in str(ei.value)
    assert len(fake.calls) == 1 and fake.calls[0].startswith(PUBLIC), \
        f"业务错误不应回退重试，实际调用：{fake.calls}"
    assert mw._fail_until == {} and mw.active_base_url() == ""


def test_http_error_does_not_fallback(monkeypatch):
    fake = _install(monkeypatch, {PUBLIC: ("resp", {"ok": True}, 500),
                                  GATEWAY: ("resp", {"ok": True})})
    with pytest.raises(mw.MiddlewareError):
        mw._request("POST", "/api/sources", {"id": "s1"})
    assert len(fake.calls) == 1, f"HTTP 5xx 属业务侧错误，不应回退重试：{fake.calls}"


def test_all_candidates_conn_error_reports_each(monkeypatch):
    _install(monkeypatch, {})
    with pytest.raises(mw.MiddlewareError) as ei:
        mw._request("GET", "/api/status")
    msg = str(ei.value)
    assert PUBLIC in msg and GATEWAY in msg, f"错误应汇总各候选原因，实际：{msg}"


def test_status_exposes_active_base(monkeypatch):
    _install(monkeypatch, {PUBLIC: ("conn", None), GATEWAY: ("resp", {"ok": True, "sources": []})})
    out = mw.status()
    assert out["base_url"] == PUBLIC and out["active_base_url"] == GATEWAY
