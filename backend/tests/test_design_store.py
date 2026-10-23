"""编排方案服务端存档回归测试（backend/app/domain/scene/design_store.py + api/design_router.py）。

背景：流程编排方案（sim.scheme）与 AI 群控编排（nengtan.agc.designs.v1）此前只存在
浏览器 localStorage，开发机做好的编排带不到服务器。现落到 backend/data/designs/<bucket>.json，
随 platform/bs-deploy/update.sh 同步（本地为唯一真源）。

锁住的边界：
1. 桶白名单（flow / agc）—— 防任意文件读写；
2. 场景 id 校验 —— 只允许 K8s 风格命名，防路径穿越；
3. 按场景分档存取与删除、旧桶内容不被覆盖；
4. 外部（运维/update.sh）改文件后按指纹自动重读（多实例一致的前提）；
5. HTTP 接口：整桶读、单场景读、写入、删除，非法输入 400。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.api.design_router import router as design_router  # noqa: E402
from app.domain.scene import design_store  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """把 designs 目录与仓库缓存指向临时目录，避免污染仓库 backend/data。"""
    monkeypatch.setattr(design_store, "DESIGN_DIR", str(tmp_path))
    monkeypatch.setattr(design_store, "_repos", {})
    yield design_store
    monkeypatch.setattr(design_store, "_repos", {})


def test_bucket_whitelist(store):
    assert store.read_bucket("flow") == {}
    with pytest.raises(ValueError):
        store.read_bucket("../../etc")
    with pytest.raises(ValueError):
        store.write_scene("passwd", "steel", {})


def test_scene_id_validated(store):
    with pytest.raises(ValueError):
        store.write_scene("flow", "../secrets", {})
    with pytest.raises(ValueError):
        store.write_scene("flow", "", {})
    store.write_scene("flow", "dc-thermal", {"nodes": []})
    assert store.read_scene("flow", "dc-thermal") == {"nodes": []}


def test_scenes_are_isolated(store):
    store.write_scene("flow", "steel", {"v": 1})
    store.write_scene("flow", "dc-thermal", {"v": 2})
    assert store.read_bucket("flow") == {"steel": {"v": 1}, "dc-thermal": {"v": 2}}
    assert store.read_scene("flow", "steel") == {"v": 1}
    # 另一桶互不影响
    assert store.read_bucket("agc") == {}
    assert store.read_scene("flow", "not-exist") is None


def test_delete_scene(store):
    store.write_scene("agc", "steel", {"designs": [{"id": "m1"}]})
    store.delete_scene("agc", "steel")
    assert store.read_scene("agc", "steel") is None
    assert store.read_bucket("agc") == {}


def test_external_file_change_is_picked_up(store, tmp_path):
    """update.sh 同步过来的文件必须被运行中的进程读到（JsonRepository 指纹失效）。"""
    store.write_scene("flow", "steel", {"v": 1})
    assert store.read_scene("flow", "steel") == {"v": 1}
    # 模拟「别的机器同步过来的新文件」：直接改写磁盘并改动指纹
    p = os.path.join(str(tmp_path), "flow.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write('{"steel": {"v": 99}}')
    os.utime(p, (os.stat(p).st_atime + 5, os.stat(p).st_mtime + 5))
    assert store.read_scene("flow", "steel") == {"v": 99}


def test_prev_snapshot_keeps_last_version(store, tmp_path):
    """整档覆盖写前必须留一版 .prev：某端把默认模板提交上来时可直接回滚。

    背景（编排「莫名其妙回到默认」顽疾）：前端在服务端存档读取失败时会按模板重建
    默认方案，此前照旧落盘就把真档抹掉了。留 .prev 让运维能 cp 回来。
    """
    store.write_scene("flow", "steel", {"nodes": [{"id": "bf"}]})
    prev = os.path.join(str(tmp_path), "flow.json.prev")
    assert not os.path.exists(prev)   # 首次写入（无旧文件）不留
    store.write_scene("flow", "steel", {"nodes": []})   # 模拟被默认/空方案覆盖
    assert os.path.exists(prev)
    import json
    with open(prev, "r", encoding="utf-8") as f:
        assert json.load(f)["steel"]["nodes"] == [{"id": "bf"}]
    # 再写一次：.prev 只保留最近一版（不累积文件）
    store.write_scene("flow", "steel", {"nodes": [{"id": "ea"}]})
    with open(prev, "r", encoding="utf-8") as f:
        assert json.load(f)["steel"]["nodes"] == []


# ---------------- HTTP 接口 ----------------

@pytest.fixture()
def client(store):
    app = FastAPI()
    app.include_router(design_router)
    with TestClient(app) as c:
        yield c


def test_api_roundtrip(client):
    assert client.get("/api/designs/flow").json() == {"ok": True, "bucket": "flow", "data": {}}
    r = client.put("/api/designs/flow", json={"scene": "steel", "data": {"scheme": {"nodes": []}}})
    assert r.json()["ok"] is True
    assert client.get("/api/designs/flow/steel").json()["data"] == {"scheme": {"nodes": []}}
    # 默认场景
    assert client.put("/api/designs/agc", json={"data": [1]}).json()["scene"] == "steel"
    assert client.get("/api/designs/agc/steel").json()["data"] == [1]
    # 删除
    assert client.delete("/api/designs/agc/steel").json()["data"] == {}
    assert client.get("/api/designs/agc/steel").json()["data"] is None


def test_api_rejects_bad_input(client):
    assert client.get("/api/designs/etc%2Fpasswd").status_code == 400
    assert client.put("/api/designs/flow", json={"scene": "../x", "data": {}}).status_code == 400


# ---------------- 运行态单独写（手动提交模式下启停不得带上未提交的清单） ----------------

def test_update_scene_fields_only_touches_given_keys(store):
    """启停只改 running：designs / updatedAt 必须原样保留。"""
    payload = {"scene": "dc-thermal", "designs": [{"id": "m1"}], "updatedAt": 111, "running": []}
    store.write_scene("agc", "dc-thermal", payload)
    assert store.update_scene_fields("agc", "dc-thermal", {"running": ["m1"]}) is True
    got = store.read_scene("agc", "dc-thermal")
    assert got["running"] == ["m1"]
    assert got["designs"] == [{"id": "m1"}]   # 清单没被动过
    assert got["updatedAt"] == 111            # 提交时间不被启停刷新
    # 停止：running 清空，清单仍在
    store.update_scene_fields("agc", "dc-thermal", {"running": []})
    assert store.read_scene("agc", "dc-thermal")["designs"] == [{"id": "m1"}]
    # 其它场景不受影响
    store.write_scene("agc", "steel", {"designs": [{"id": "s1"}]})
    store.update_scene_fields("agc", "dc-thermal", {"running": ["m1"]})
    assert store.read_scene("agc", "steel") == {"designs": [{"id": "s1"}]}


def test_update_scene_fields_reports_missing_scene(store):
    """服务端还没这个场景的存档：返回 False，且不要凭空造出一个空档。"""
    assert store.update_scene_fields("agc", "dc-thermal", {"running": ["m1"]}) is False
    assert store.read_bucket("agc") == {}
    with pytest.raises(ValueError):
        store.update_scene_fields("../../etc", "dc-thermal", {"running": []})


def test_api_agc_running(client):
    """PUT /api/designs/agc/running：只改运行态；无存档时 found=False。"""
    assert client.put("/api/designs/agc/running", json={"scene": "dc-thermal", "running": ["m1"]}).json()["found"] is False
    client.put("/api/designs/agc", json={"scene": "dc-thermal", "data": {"designs": [{"id": "m1"}], "running": []}})
    r = client.put("/api/designs/agc/running", json={"scene": "dc-thermal", "running": ["m1"]}).json()
    assert r["found"] is True and r["ok"] is True
    data = client.get("/api/designs/agc/dc-thermal").json()["data"]
    assert data["running"] == ["m1"] and data["designs"] == [{"id": "m1"}]
    # 场景 id 非法 -> 400
    assert client.put("/api/designs/agc/running", json={"scene": "../x", "running": []}).status_code == 400


# ---------------- 整档覆盖（last-writer-wins）：提交什么存什么，不提交即删除 ----------------

def test_write_is_whole_scene_overwrite(store):
    """存档语义为整档覆盖：本次没提交的条目即视为删除，另一端带旧档保存会原样覆盖。

    背景：此前用 removed / hidden 墓碑防止「删了又被写回」，用户明确否决该机制
    （复杂且会让真正的删除难以推理）。现在的口径是单一真源 + 整档覆盖，
    代价是多端同时编辑时后写者胜，由使用者避免并发编辑来规避。
    """
    store.write_scene("agc", "dc-thermal", {"designs": [{"id": "m1"}, {"id": "m2"}]})
    assert [i["id"] for i in store.read_scene("agc", "dc-thermal")["designs"]] == ["m1", "m2"]
    # 删除 m1：不提交即为删除，无需任何墓碑声明
    store.write_scene("agc", "dc-thermal", {"designs": [{"id": "m2"}]})
    assert [i["id"] for i in store.read_scene("agc", "dc-thermal")["designs"]] == ["m2"]
    # 另一端拿着旧档保存：后写者胜（不再有墓碑把 m1 拦掉）
    store.write_scene("agc", "dc-thermal", {"designs": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]})
    assert [i["id"] for i in store.read_scene("agc", "dc-thermal")["designs"]] == ["m1", "m2", "m3"]
    # 按场景分档，互不影响
    store.write_scene("agc", "steel", {"designs": [{"id": "s1"}]})
    assert [i["id"] for i in store.read_scene("agc", "steel")["designs"]] == ["s1"]
