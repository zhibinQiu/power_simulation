"""云端 CRD 自动收敛（backend/app/box_console/reconcile.py）回归测试。

核心断言：设备定义只有本地一份，云端 CRD 必须恒等于本地登记表——
· 云端少 → 自动补建；云端多（CRD-only 孤儿）→ 自动删除；一致 → 不做任何写操作；
· 云端数据不可信（不可达 / 缓存过期）时**绝不**基于快照做增删。
"""
import pytest

from app.box_console import reconcile as rc


def _local(dev_name="dev-1", model="m1", cloud_device=""):
    dev = {"name": dev_name, "model": model, "node": "nt001"}
    if cloud_device:
        dev["cloudDevice"] = cloud_device
    return {"models": [{"name": model}], "devices": [dev]}


def _crds(devices=(), models=(), ok=True, fresh=True, age=1.0):
    return {
        "ok": ok,
        "devices": [{"name": n} for n in devices],
        "models": [{"name": n} for n in models],
        "_cached": True, "_cache_age": age, "_cache_fresh": fresh,
    }


@pytest.fixture
def stub(monkeypatch):
    """桩住云端读写，只观测收敛动作；返回记录用的 calls 字典。"""
    calls = {"apply": 0, "deleted": [], "apply_ok": True, "delete_ok": True}

    monkeypatch.setattr(rc, "_load_devices", lambda: _local())
    monkeypatch.setattr(rc, "cloud_config", lambda: {"namespace": "default"})
    monkeypatch.setattr(rc, "apply_devices_to_cloud",
                        lambda *a, **k: {"ok": calls["apply_ok"],
                                         "error": "" if calls["apply_ok"] else "agent 不可达"})
    monkeypatch.setattr(rc, "_cloud_delete_crds",
                        lambda kind, name, ns: (calls["deleted"].append((kind, name, ns)) or
                                                {"ok": calls["delete_ok"],
                                                 "error": "" if calls["delete_ok"] else "delete failed"}))

    def _wrap_apply(*a, **k):
        calls["apply"] += 1
        return {"ok": calls["apply_ok"], "error": "" if calls["apply_ok"] else "agent 不可达"}

    monkeypatch.setattr(rc, "apply_devices_to_cloud", _wrap_apply)
    return calls


def test_missing_in_cloud_is_applied(monkeypatch, stub):
    """云端没有本地登记表里的设备/模型 → 自动补建（云端少一台也是故障态）。"""
    monkeypatch.setattr(rc.cloud_agent, "crds", lambda: _crds())
    res = rc.reconcile_cloud()
    assert stub["apply"] == 1
    assert res["created"] == ["device dev-1", "model m1"]
    assert res["deleted"] == [] and res["ok"] is True


def test_crd_only_orphan_is_deleted(monkeypatch, stub):
    """云端多出来的 CRD-only 孤儿必须被删掉（用户明确不接受云端存在本地没有的设备）。"""
    monkeypatch.setattr(rc.cloud_agent, "crds",
                        lambda: _crds(devices=["dev-1", "ghost-dev"], models=["m1", "ghost-model"]))
    res = rc.reconcile_cloud()
    assert stub["deleted"] == [("device", "ghost-dev", "default"),
                               ("model", "ghost-model", "default")]
    assert stub["apply"] == 0                      # 没有缺失就不必整包 apply
    assert res["deleted"] == ["device ghost-dev", "model ghost-model"]


def test_aligned_makes_no_write(monkeypatch, stub):
    """已一致时不产生任何写操作（幂等，不是每次周期都去 kubectl 刷一遍）。"""
    monkeypatch.setattr(rc.cloud_agent, "crds", lambda: _crds(devices=["dev-1"], models=["m1"]))
    res = rc.reconcile_cloud()
    assert stub["apply"] == 0 and stub["deleted"] == []
    assert "已一致" in res["skipped"]
    assert res["ok"] is True


def test_stale_cache_is_skipped(monkeypatch, stub):
    """CRD 缓存过期（agent 推送中断）时绝不基于旧快照增删，否则会误删/误补。"""
    monkeypatch.setattr(rc.cloud_agent, "crds",
                        lambda: _crds(devices=["dev-1", "ghost"], models=["m1"], fresh=False, age=900))
    res = rc.reconcile_cloud()
    assert stub["deleted"] == [] and stub["apply"] == 0
    assert res["ok"] is False and "过期" in res["skipped"]


def test_cloud_unreadable_is_skipped(monkeypatch, stub):
    """云端不可读 → 跳过（云端断连时不存heckmark在对账这回事）。"""
    monkeypatch.setattr(rc.cloud_agent, "crds",
                        lambda: {"ok": False, "error": "agent 不可达", "models": [], "devices": []})
    res = rc.reconcile_cloud()
    assert stub["deleted"] == [] and stub["apply"] == 0
    assert res["ok"] is False and "不可读" in res["skipped"]


def test_bound_cloud_device_name_is_not_orphan(monkeypatch, stub):
    """设备靠 cloudDevice 绑定云端旧名时，该名不是孤儿 —— 删掉会让设备与云端失联。

    平台语义是「每台本地设备在云端有同名 CRD」，所以本地名 new-name 缺失仍要补建；
    cloudDevice 只用来保护云端既有对象不被误删，不参与「是否已对齐」的判定。
    """
    monkeypatch.setattr(rc, "_load_devices", lambda: _local("new-name", cloud_device="old-crd-name"))
    monkeypatch.setattr(rc.cloud_agent, "crds", lambda: _crds(devices=["old-crd-name"], models=["m1"]))
    res = rc.reconcile_cloud()
    assert stub["deleted"] == []                       # 绑定名绝不能被当成孤儿删掉
    assert res["created"] == ["device new-name"]       # 本地名在云端应有同名 CRD


def test_apply_failure_is_reported(monkeypatch, stub):
    """补建失败要如实报出来（ok=False + 原因），不能留下「静默漂移」。"""
    stub["apply_ok"] = False
    monkeypatch.setattr(rc.cloud_agent, "crds", lambda: _crds())
    res = rc.reconcile_cloud()
    assert res["ok"] is False
    assert any("补建云端对象失败" in f for f in res["failed"])
    assert res["created"] == []


def test_delete_failure_is_reported(monkeypatch, stub):
    """删除失败同样要报出来，否则孤儿还在却显示已收敛。"""
    stub["delete_ok"] = False
    monkeypatch.setattr(rc.cloud_agent, "crds",
                        lambda: _crds(devices=["dev-1", "ghost-dev"], models=["m1"]))
    res = rc.reconcile_cloud()
    assert res["ok"] is False
    assert res["deleted"] == [] and res["failed"]


def test_last_reconcile_records_result(monkeypatch, stub):
    """最近一次结果可被查询（前端展示「云端已对齐 / 跳过原因」）。"""
    monkeypatch.setattr(rc.cloud_agent, "crds", lambda: _crds(devices=["dev-1"], models=["m1"]))
    rc.reconcile_cloud()
    last = rc.last_reconcile()
    assert last["ran"] is True and "已一致" in last["skipped"]


def test_reconciler_disabled_when_interval_zero(monkeypatch):
    """BOX_CLOUD_RECONCILE_INTERVAL=0 → 不启动后台线程（可关闭自动收敛）。"""
    monkeypatch.setenv("BOX_CLOUD_RECONCILE_INTERVAL", "0")
    monkeypatch.setattr(rc, "stop_reconciler", lambda: None)
    rc.stop_reconciler()
    assert rc.start_reconciler() is None
