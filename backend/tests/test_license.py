"""平台激活（License）模块单元测试。"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import license as lic  # noqa: E402


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(lic, "_LICENSE_PATH", str(tmp_path / "license.json"))


def test_machine_id_stable_and_hex():
    m1 = lic.machine_id()
    m2 = lic.machine_id()
    assert m1 == m2
    assert len(m1) == 16
    assert all(c in "0123456789abcdef" for c in m1)


def test_gen_license_format_and_matches_machine():
    mid = lic.machine_id()
    code = lic.gen_license(mid)
    parts = code.split("-")
    assert parts[0] == "NENG"
    assert len(parts) == 5
    assert all(len(p) == 4 for p in parts[1:])
    assert lic.verify(code, mid)
    # 换机器不匹配
    other = "b" * 16
    assert not lic.verify(lic.gen_license(other), mid)


def test_verify_rejects_bad_input():
    assert not lic.verify("")
    assert not lic.verify("NENG-1234-1234-1234")          # 组数不足
    assert not lic.verify("NENG-ZZZZ-1234-1234-1234")     # 非 hex
    assert not lic.verify("NENG-1234-1234-1234-5678")     # 伪造签名
    assert not lic.verify(" abc-NENG-1234-1234-1234-5678 ".strip())


def test_activate_persists_state(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mid = lic.machine_id()
    code = lic.gen_license(mid)

    # 初始未激活
    assert lic.get_status()["activated"] is False

    ok, msg, st = lic.activate(code)
    assert ok, msg
    assert st["activated"] is True
    assert st["bound_machine"] == mid

    # 已写入文件
    with open(lic._LICENSE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert data["activated"] is True
    assert data["machine_id"] == mid

    # 状态接口读取文件
    assert lic.get_status()["activated"] is True


def test_activate_rejects_invalid_and_duplicate(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mid = lic.machine_id()
    good = lic.gen_license(mid)

    ok, msg, _ = lic.activate("NENG-0000-0000-0000-0000")
    assert not ok and "无效" in msg

    ok, msg, _ = lic.activate(good)
    assert ok, msg
    # 重复激活同一机器 -> 拒绝
    ok, msg, _ = lic.activate(good)
    assert not ok and "已激活" in msg


def test_activate_detects_other_machine(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # 用另一个机器指纹生成的激活码在本机应无效
    other_code = lic.gen_license("b" * 16)
    ok, msg, _ = lic.activate(other_code)
    assert not ok and ("无效" in msg or "不匹配" in msg)


def test_api_status_route():
    """真实 TestClient 级：GET /api/license/status 返回激活状态。"""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/license/status")
        assert r.status_code == 200
        body = r.json()
        assert "activated" in body
        assert "machine_id" in body
        assert len(body["machine_id"]) == 16


def test_api_activate_route(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    _isolate(monkeypatch, tmp_path)
    mid = lic.machine_id()
    good = lic.gen_license(mid)

    with TestClient(app) as c:
        r = c.post("/api/license/activate", json={"code": good})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["activated"] is True

        r2 = c.post("/api/license/activate", json={"code": "NENG-0000-0000-0000-0000"})
        assert r2.json()["ok"] is False
