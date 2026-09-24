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
