"""一次改动多处生效 + 对外接口清单自描述 回归测试。

覆盖两条约束：
① 设备的新增/改名/删除之后，云端 CRD 与盒子 mapper 取数配置都由平台自动同步，
   调用方不需要（也没有）额外的「同步」动作；盒子不可达不得阻断本地操作。
② 「数据服务接口清单」里的每一项都必须真实存在于路由中（防止清单与实现漂移），
   且 GET/POST 的调用示例可直接复制使用。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.box_console import devices as dev_mod  # noqa: E402
from app.data_sources.api_catalog import catalog  # noqa: E402


@pytest.fixture()
def mem_cfg(monkeypatch):
    """把设备配置读写重定向到内存，避免污染 config/box_devices.json。"""
    box = {"data": {"devices": [], "models": [], "cloud": {}}}
    monkeypatch.setattr(dev_mod, "_load_devices", lambda: box["data"])
    monkeypatch.setattr(dev_mod, "_save_devices", lambda d: box.__setitem__("data", d))
    return box


@pytest.fixture()
def box_push(monkeypatch):
    """记录向盒子的每次推送；可在用例里注入失败。"""
    calls = {"boxes": [], "fail": False}

    def _push(box=""):
        calls["boxes"].append(box)
        if calls["fail"]:
            raise RuntimeError("盒子不可达")
        return {"ok": True, "box": box, "applied": True}

    monkeypatch.setattr(dev_mod, "push_lora_config", _push)
    return calls


def _device(name, node="nt001"):
    return {"name": name, "namespace": "default", "hwId": "lora-0120560100000245-s7",
            "model": "lora-temp-model", "node": node, "protocol": "lora",
            "lora": {"devEUI": "0120560100000245", "slaveId": 7},
            "properties": [{"name": "temperature", "type": "int", "scale": 0.1}],
            "yaml": "kind: Device\n", "status": "reporting"}


# ------------------------- ① 删除：云端 CRD + 盒子配置同步 -------------------------
def test_delete_syncs_cloud_and_box(mem_cfg, box_push, monkeypatch):
    """删除设备默认同时删除云端 CRD，并向该设备所在盒子重推取数配置（停采）。"""
    mem_cfg["data"]["devices"] = [_device("shuitong-temp"), _device("flow-meter", node="nt001")]
    deleted = []
    monkeypatch.setattr(dev_mod, "_cloud_delete_crds",
                        lambda kind, name, ns: deleted.append((kind, name, ns)) or {"ok": True})

    res = dev_mod.delete_device("device", "shuitong-temp")

    assert res["ok"] is True
    assert res["removed"]["devices"] == ["shuitong-temp"]
    assert deleted == [("device", "shuitong-temp", "default")]
    # 只对该设备所在的盒子推一次，且去重
    assert box_push["boxes"] == ["nt001"]


def test_delete_box_failure_does_not_break_local(mem_cfg, box_push, monkeypatch):
    """盒子不可达时本地删除照常完成，失败以 box_sync 反馈（不抛异常、不回滚）。"""
    mem_cfg["data"]["devices"] = [_device("shuitong-temp")]
    box_push["fail"] = True
    monkeypatch.setattr(dev_mod, "_cloud_delete_crds", lambda *a: {"ok": True})

    res = dev_mod.delete_device("device", "shuitong-temp")

    assert res["ok"] is True
    assert res["removed"]["devices"] == ["shuitong-temp"]
    assert res["box_sync"]["nt001"]["ok"] is False
    assert "盒子不可达" in res["box_sync"]["nt001"]["error"]


def test_can_delete_crd_only(mem_cfg, box_push):
    """local=False 且 cloud=True：只删云端 CRD，本地配置保留，不打扰盒子。"""
    mem_cfg["data"]["devices"] = [_device("shuitong-temp")]
    res = dev_mod.delete_device("device", "shuitong-temp", cloud=False, local=False)
    assert res["ok"] is True
    assert "removed" not in res
    assert res["box_sync"] == {}


# ------------------------- ② 接口清单与真实路由一致 -------------------------
def test_catalog_items_exist_in_routes():
    """清单每一项都必须是已注册的路由，避免文档与实现漂移。"""
    from app.main import app  # 延迟导入：main 装配较重

    # 以 OpenAPI 为准（部分路由经子应用挂载，routes 里路径形态不统一）
    registered = {(m.upper(), path) for path, ops in app.openapi()["paths"].items()
                  for m in ops if m in ("get", "post")}
    items = [it for g in catalog("")["groups"] for it in g["items"]]
    assert items, "清单不应为空"
    for it in items:
        assert (it["method"], it["path"]) in registered, \
            "清单里的接口不存在：%s %s" % (it["method"], it["path"])


def test_catalog_examples_ready_to_use():
    """GET 给出含 base_url 与示例参数的完整 URL；POST 给出请求体。"""
    data = catalog("http://host:8010/")
    assert data["base_url"] == "http://host:8010"
    by_id = {g["id"]: g for g in data["groups"]}
    assert {"history", "realtime", "command"} <= set(by_id)

    hist = by_id["history"]["items"][0]
    assert hist["url"].startswith("http://host:8010/api/box/cloud/tsdb/history?")
    assert "box=nt001" in hist["url"] and "body" not in hist

    cmd = next(i for i in by_id["command"]["items"] if i["path"] == "/api/box/devices")
    assert cmd["method"] == "POST"
    assert cmd["url"] == "http://host:8010/api/box/devices"
    assert "deviceName" in cmd["body"]
