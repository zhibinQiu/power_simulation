"""编排存档（flow / agc）「本地 ⇄ 服务器」双向同步回归测试。

背景：编排是用户在平台上编辑出来的运行期内容，本地实例（8010）与服务器实例（40014）
各写各的 backend/data/designs/{flow,agc}.json。此前 update.sh 只做单向 rsync 覆盖，
导致 ① 服务器上的编排本地看不到 ② 下一次推送又把服务器上的新编排整体抹掉
（表现为「刚配好的附加传感 / 采集设备绑定被还原」）。

本测试锁定两件事：
  1. platform/bs-deploy/designs_sync.py 的合并口径（按场景 updatedAt 较新者胜出，
     仅一侧有的场景并入，写回前备份）；
  2. 同步入口已接入 platform/bs-deploy/update.sh 与仓库根 update.sh（designs 目标）。
"""
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BS_DEPLOY_DIR = os.path.join(REPO_ROOT, "platform", "bs-deploy")
SYNC_PY = os.path.join(BS_DEPLOY_DIR, "designs_sync.py")
SYNC_SH = os.path.join(BS_DEPLOY_DIR, "sync_designs.sh")


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run(bucket, local, remote, *extra):
    rc = subprocess.run(
        [sys.executable, SYNC_PY, bucket, local, remote, *extra],
        capture_output=True, text=True,
    )
    return rc.returncode, rc.stdout


def test_server_only_scene_merges_into_local(tmp_path):
    """仅服务器有的场景 → 并入本地（服务器上的编排同步回开发机）。"""
    local = _write(str(tmp_path / "flow.json"), {"steel": {"sceneId": "steel", "updatedAt": 1000}})
    remote = _write(str(tmp_path / "remote.json"), {
        "steel": {"sceneId": "steel", "updatedAt": 1000},
        "dc-thermal": {"sceneId": "dc-thermal", "updatedAt": 2000},
    })
    rc, out = _run("flow", local, remote)
    assert rc == 0
    data = _read(local)
    assert "dc-thermal" in data and "服务器" in out
    # 写回前留备份，出错可回滚
    baks = [p for p in os.listdir(str(tmp_path)) if p.startswith("flow.json.bak.")]
    assert baks, "合并写回前必须备份本地存档"


def test_newer_side_wins_per_scene(tmp_path):
    """两端都有同一场景时取 updatedAt 较大的一份（谁最后编辑谁生效）。"""
    local = _write(str(tmp_path / "flow.json"), {
        "a": {"sceneId": "a", "updatedAt": 3000, "scheme": {"nodes": [{"id": "n1"}]}},
        "b": {"sceneId": "b", "updatedAt": 1000, "scheme": {"nodes": [{"id": "n1"}]}},
    })
    remote = _write(str(tmp_path / "remote.json"), {
        "a": {"sceneId": "a", "updatedAt": 2000, "scheme": {"nodes": [{"id": "old"}]}},
        "b": {"sceneId": "b", "updatedAt": 5000, "scheme": {"nodes": [{"id": "new"}]}},
    })
    rc, out = _run("flow", local, remote)
    assert rc == 0
    data = _read(local)
    # a：本地较新 → 保留本地；b：服务器较新 → 采用服务器
    assert data["a"]["scheme"]["nodes"][0]["id"] == "n1"
    assert data["b"]["scheme"]["nodes"][0]["id"] == "new"
    assert "保留本地" in out and "采用服务器" in out


def test_local_only_scene_kept_and_no_write_when_identical(tmp_path):
    """仅本地有的场景保留（随 rsync 推到服务器）；两端完全一致时不写盘。"""
    payload = {"steel": {"sceneId": "steel", "updatedAt": 1000}}
    local = _write(str(tmp_path / "flow.json"), payload)
    remote = _write(str(tmp_path / "remote.json"), json.loads(json.dumps(payload)))
    rc, out = _run("flow", local, remote)
    assert rc == 0 and "无需合并" in out
    assert not [p for p in os.listdir(str(tmp_path)) if p.startswith("flow.json.bak.")]
    # 本地独有的场景不被删除
    local2 = _write(str(tmp_path / "agc.json"), {"x": {"updatedAt": 10}})
    remote2 = _write(str(tmp_path / "remote2.json"), {"y": {"updatedAt": 20}})
    _run("agc", local2, remote2)
    assert set(_read(local2)) == {"x", "y"}


def test_missing_or_broken_remote_is_tolerated(tmp_path):
    """服务器存档缺失 / 损坏：不报错、不破坏本地。"""
    local = _write(str(tmp_path / "flow.json"), {"steel": {"updatedAt": 1}})
    broken = str(tmp_path / "broken.json")
    with open(broken, "w", encoding="utf-8") as f:
        f.write("{not-json")
    rc, out = _run("flow", local, broken)
    assert rc == 0 and _read(local) == {"steel": {"updatedAt": 1}}
    # 远端文件不存在（全新部署）
    rc, out = _run("flow", local, str(tmp_path / "nope.json"))
    assert rc == 0 and "服务器存档为空或缺失" in out


def test_dry_run_does_not_write(tmp_path):
    local = _write(str(tmp_path / "flow.json"), {"a": {"updatedAt": 1}})
    remote = _write(str(tmp_path / "remote.json"), {"a": {"updatedAt": 9}})
    rc, out = _run("flow", local, remote, "--dry-run")
    assert rc == 0 and _read(local)["a"]["updatedAt"] == 1 and "dry-run" in out


def test_sync_entry_wired_into_update_scripts():
    """同步入口必须接进 bs-deploy/update.sh（--designs 时推送前合并）与仓库根 update.sh（designs 目标）。"""
    assert os.path.isfile(SYNC_PY) and os.path.isfile(SYNC_SH)
    bs = open(os.path.join(BS_DEPLOY_DIR, "update.sh"), encoding="utf-8").read()
    assert "sync_designs.sh" in bs, "bs-deploy/update.sh 需保留编排存档双向合并入口"
    assert "--no-push" in bs, "update.sh 内的合并结果由主 rsync 统一推送，不应重复传输"
    root = open(os.path.join(REPO_ROOT, "update.sh"), encoding="utf-8").read()
    assert "step_designs" in root and "designs|design) step_designs ;;" in root
    for path in (SYNC_SH, os.path.join(BS_DEPLOY_DIR, "update.sh"), os.path.join(REPO_ROOT, "update.sh")):
        rc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert rc.returncode == 0, f"{path} 语法错误：{rc.stderr}"


def test_designs_not_synced_by_default():
    """用户口径：推送代码（./update.sh all / bs）默认不带走编排存档，必须显式 --designs 或 ./update.sh designs。

    编排是运行期内容，本地与服务器各写各的；默认整目录排除，两端各自保留。
    """
    bs = open(os.path.join(BS_DEPLOY_DIR, "update.sh"), encoding="utf-8").read()
    # 默认关闭：SYNC_DESIGNS=0，且排除规则必须真的出现在 rsync 规则变量里
    assert "SYNC_DESIGNS=0" in bs
    assert "--designs|--with-designs) SYNC_DESIGNS=1; shift ;;" in bs
    assert '--exclude=backend/data/designs/***' in bs
    assert 'DESIGN_RULES' in bs and '$DESIGN_RULES' in bs
    root = open(os.path.join(REPO_ROOT, "update.sh"), encoding="utf-8").read()
    # 根目录入口：--designs 透传给 bs；未指定时提示手动同步
    assert "DO_DESIGNS=0" in root
    assert "--designs|--with-designs) DO_DESIGNS=1; shift ;;" in root
    assert 'args+=("--designs")' in root
    assert "./update.sh designs" in root
