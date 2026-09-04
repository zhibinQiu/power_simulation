"""盒子一键接入（自解压 onboard_box.sh）单元测试。

覆盖：box-deploy 打包、自解压脚本渲染与提取闭环、onboard_node 元信息、
下载接口、远程一键接入（mock 云端 agent）。不依赖真实云端。
"""
import base64
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import box_console  # noqa: E402
from app import github_deploy  # noqa: E402

TOKEN = "a1b2c3.header.payload.sig"
CLOUD_IP = "36.151.146.71"
HOSTNAME = "edge-box"


def fake_fetch_cloud_k8s(force=True):
    return {"ok": True, "token": {"value": TOKEN, "source": "cloud", "expires": "2027-08-27"}}


def fake_rootca():
    return {"ok": True, "data": base64.b64encode(b"MOCK-ROOTCA").decode(), "size": 12}


@pytest.fixture(autouse=True)
def _patch_cloud(monkeypatch):
    # 门面引用（github_deploy 等）与模块引用（box_console.onboard 内部）双通道都 mock
    monkeypatch.setattr(box_console, "_fetch_cloud_k8s", fake_fetch_cloud_k8s)
    monkeypatch.setattr(box_console.overview, "_fetch_cloud_k8s", fake_fetch_cloud_k8s)
    monkeypatch.setattr(box_console.cloud_agent, "rootca", fake_rootca)


def test_pack_box_deploy_is_valid_targz():
    deploy_gz = box_console._pack_box_deploy()
    assert deploy_gz.startswith(b"\x1f\x8b")  # gzip 魔数
    with tarfile.open(fileobj=io.BytesIO(deploy_gz), mode="r:gz") as tf:
        names = tf.getnames()
    assert "deploy_box.sh" in names
    assert "mapper" in names
    # 不打包 __pycache__/pyc
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)


def test_render_onboard_script_roundtrip():
    deploy_gz = box_console._pack_box_deploy()
    edgecore_yaml = f"apiVersion: edgecore.config.kubeedge.io/v1alpha2\nmodules:\n  edgeHub:\n    token: {TOKEN}\n"
    script = box_console._render_onboard_script(
        HOSTNAME, CLOUD_IP, edgecore_yaml,
        base64.b64encode(b"MOCK-ROOTCA").decode(), TOKEN,
        base64.b64encode(deploy_gz).decode())
    assert "__ONBOARD_PAYLOAD__" in script
    assert CLOUD_IP in script and HOSTNAME in script
    # bash 语法合法
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        rc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert rc.returncode == 0, rc.stderr
    finally:
        os.unlink(path)
    # 提取闭环（同脚本内 awk 逻辑：marker 行锚定，取最后一次出现）
    payload_b64 = script.rsplit("__ONBOARD_PAYLOAD__", 1)[1].strip()
    restored = base64.b64decode(payload_b64)
    assert restored == deploy_gz
    with tarfile.open(fileobj=io.BytesIO(restored), mode="r:gz") as tf:
        assert "deploy_box.sh" in tf.getnames()


def test_onboard_node_metadata():
    res = box_console.onboard_node({"hostname": HOSTNAME, "cloudIP": CLOUD_IP, "boxIP": "10.0.0.8"})
    assert res["ok"]
    assert res["token"] == TOKEN
    assert res["caHash"] == "a1b2c3"
    assert res["script_size"] > 1000000
    assert res["rootca_inline"] is True
    assert "onboard_box.sh" in res["script_hint"]
    assert any("onboard_box.sh" in c for c in res["commands"])
    assert box_console.ONBOARD_SCRIPT_PATH.is_file()


def test_onboard_node_validation():
    assert not box_console.onboard_node({"hostname": "bad name!", "cloudIP": "1.2.3.4"}).get("ok")
    assert not box_console.onboard_node({"hostname": "edge-box", "cloudIP": ""}).get("ok")


def test_onboard_script_download():
    box_console.onboard_node({"hostname": HOSTNAME, "cloudIP": CLOUD_IP, "boxIP": ""})
    dl = box_console.onboard_script_download()
    assert dl["ok"]
    assert base64.b64decode(dl["script_b64"]) == box_console.ONBOARD_SCRIPT_PATH.read_bytes()
    assert dl["script_name"] == "onboard_box.sh"


def test_box_onboard_remote(monkeypatch):
    calls = {}

    def fake_edge_upload(path, data_b64, mode="0644", edge=None):
        calls["upload"] = {"path": path, "mode": mode, "edge": edge,
                           "bytes": len(base64.b64decode(data_b64))}
        return {"ok": True, "bytes": len(base64.b64decode(data_b64)), "stderr": ""}

    def fake_edge_run(cmd, timeout=60, edge=None):
        calls["run"] = {"cmd": cmd, "timeout": timeout, "edge": edge}
        return {"ok": True, "rc": 0, "stdout": "[onboard] 一键接入完成！", "stderr": ""}

    monkeypatch.setattr(box_console.cloud_agent, "edge_upload", fake_edge_upload)
    monkeypatch.setattr(box_console.cloud_agent, "edge_run", fake_edge_run)

    res = box_console.box_onboard_remote(
        {"hostname": HOSTNAME, "cloudIP": CLOUD_IP, "boxIP": "10.0.0.8"})
    assert res["ok"], res
    assert len(res["steps"]) == 2 and all(s["ok"] for s in res["steps"])
    assert calls["upload"]["path"] == "/opt/onboard_box.sh"
    assert calls["upload"]["mode"] == "0755"
    assert calls["upload"]["edge"] == {"host": "10.0.0.8"}
    assert calls["run"]["cmd"] == "bash /opt/onboard_box.sh"
    assert calls["run"]["timeout"] == 900
    assert res["hostname"] == HOSTNAME


def test_box_onboard_remote_upload_failure(monkeypatch):
    def fake_edge_upload(path, data_b64, mode="0644", edge=None):
        return {"ok": False, "bytes": 0, "stderr": "ssh: connect to host 10.0.0.8 port 22: Connection timed out"}

    monkeypatch.setattr(box_console.cloud_agent, "edge_upload", fake_edge_upload)

    res = box_console.box_onboard_remote({"hostname": HOSTNAME, "cloudIP": CLOUD_IP, "boxIP": "10.0.0.8"})
    assert not res["ok"]
    assert "ssh: connect" in res["error"]
    assert len(res["steps"]) == 1 and not res["steps"][0]["ok"]


# ------------------------- GitHub 托管（一键资产同步到用户仓库） -------------------------

def _save_github_cfg(monkeypatch, token="ghp_test123"):
    monkeypatch.setattr(github_deploy, "CONFIG_PATH", tempfile.mktemp(suffix=".json"))
    res = github_deploy.save_config(
        {"owner": "zhibinQiu", "repo": "power_simulation", "branch": "master", "token": token})
    assert res["ok"]
    return res


def test_github_get_save_config(monkeypatch):
    _save_github_cfg(monkeypatch)
    cfg = github_deploy.get_config()
    assert cfg["ok"] and cfg["owner"] == "zhibinQiu" and cfg["repo"] == "power_simulation"
    assert cfg["token_set"] is True
    # token 留空沿用已保存值
    github_deploy.save_config({"owner": "zhibinQiu", "repo": "power_simulation", "token": ""})
    assert github_deploy.get_config()["token_set"] is True
    # 缺少 owner/repo
    assert not github_deploy.save_config({"owner": "", "repo": ""})["ok"]


def test_github_launcher_render():
    script = github_deploy._render_launcher(CLOUD_IP, "zhibinQiu", "power_simulation", "master")
    assert "REPO_BASE=\"https://raw.githubusercontent.com/zhibinQiu/power_simulation/master\"" in script
    assert f"CLOUD_IP=\"{CLOUD_IP}\"" in script
    # 配置文件驱动：-c/-i/-n 参数 + 自动读 /opt/weight-bridge/box-config.json
    assert "-c|--config)" in script and "-i|--ip)" in script and "-n|--name)" in script
    assert 'CFG_FILE="$BOX_DIR/box-config.json"' in script
    assert "curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash" in script
    assert "bash -s -- -c /path/box-config.json" in script
    # 占位符统一替换（python3 一次替换三个占位符）
    assert "{{HOSTNAME}}" in script and "{{TOKEN}}" in script and "{{CLOUDIP}}" in script
    # bash 语法合法
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        rc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert rc.returncode == 0, rc.stderr
    finally:
        os.unlink(path)


def test_github_push_success(monkeypatch):
    _save_github_cfg(monkeypatch)
    puts: dict = {}

    def fake_gh(method, url, token, body=None, timeout=60):
        if method == "GET":
            return 200, {"sha": "oldsha", "path": url.rsplit("/", 1)[-1]}
        puts[url.rsplit("/", 1)[-1]] = base64.b64decode(body["content"])
        return 201, {"content": {}}

    monkeypatch.setattr(github_deploy, "_gh_request", fake_gh)
    res = github_deploy.push_to_github(CLOUD_IP)
    assert res["ok"], res
    assert len(res["files"]) == 5 and all(f["ok"] for f in res["files"])
    assert "onboard/onboard_box.sh" in [f["path"] for f in res["files"]]
    assert "curl -fsSL https://raw.githubusercontent.com/zhibinQiu/power_simulation/master/onboard/onboard_box.sh | bash" == res["command"]
    assert res["caHash"] == "a1b2c3"
    # 上传内容断言：edgecore.yaml 保留全部占位符（由盒子端按 box-config.json 统一替换），不注入真实 token
    assert b"{{HOSTNAME}}" in puts["edgecore.yaml"]
    assert b"{{TOKEN}}" in puts["edgecore.yaml"]
    assert b"{{CLOUDIP}}" in puts["edgecore.yaml"]
    assert TOKEN.encode() not in puts["edgecore.yaml"]
    assert puts["token"] == TOKEN.encode()
    assert puts["rootCA.crt"] == b"MOCK-ROOTCA"
    assert puts["onboard_box.sh"].startswith(b"#!/usr/bin/env bash")
    assert b"-c|--config)" in puts["onboard_box.sh"]
    assert "box-deploy.tar.gz" in puts and puts["box-deploy.tar.gz"].startswith(b"\x1f\x8b")


def test_github_export_box_config(monkeypatch):
    _save_github_cfg(monkeypatch)
    res = github_deploy.export_box_config(HOSTNAME, CLOUD_IP)
    assert res["ok"], res
    assert res["config"]["boxId"] == HOSTNAME
    assert res["config"]["cloudIP"] == CLOUD_IP
    assert res["config"]["token"] == TOKEN
    assert res["config"]["repo"] == "zhibinQiu/power_simulation"
    assert res["config"]["branch"] == "master"
    assert res["caHash"] == "a1b2c3" and res["token_set"] is True
    # content 是合法 JSON，含 _说明 与全部字段
    content = json.loads(res["content"])
    assert "_说明" in content and content["boxId"] == HOSTNAME and content["cloudIP"] == CLOUD_IP
    # 缺 cloudIP 报错；云端取不到 token 时 token 留空但 ok
    assert not github_deploy.export_box_config(HOSTNAME, "")["ok"]
    monkeypatch.setattr(box_console, "_fetch_cloud_k8s",
                        lambda force=True: {"ok": True, "token": {}})
    res2 = github_deploy.export_box_config(HOSTNAME, CLOUD_IP)
    assert res2["ok"] and res2["config"]["token"] == "" and res2["token_set"] is False


def test_github_push_missing_config(monkeypatch):
    monkeypatch.setattr(github_deploy, "CONFIG_PATH", tempfile.mktemp(suffix=".json"))
    res = github_deploy.push_to_github(CLOUD_IP)
    assert not res["ok"] and "GitHub 配置未设置" in res["error"]
    # 配置了 owner 但无 token
    github_deploy.save_config({"owner": "zhibinQiu", "repo": "power_simulation", "token": ""})
    res = github_deploy.push_to_github(CLOUD_IP)
    assert not res["ok"] and "token" in res["error"]


# ---------- GitHub 源码一键部署（platform/bs-deploy · platform/box-deploy） ----------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BS_DEPLOY_DIR = os.path.join(REPO_ROOT, "platform", "bs-deploy")    # 平台自身前后端部署
BOX_DEPLOY_DIR = os.path.join(REPO_ROOT, "platform", "box-deploy")  # 边缘盒子部署


def _read_deploy_script(dir_: str, name: str) -> str:
    path = os.path.join(dir_, name)
    assert os.path.isfile(path), f"部署脚本缺失：{path}"
    return open(path, encoding="utf-8").read()


def _check_bash_syntax(script: str):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        rc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert rc.returncode == 0, rc.stderr
    finally:
        os.unlink(path)


def test_deploy_server_sh():
    script = _read_deploy_script(BS_DEPLOY_DIR, "deploy.sh")
    assert script.startswith("#!/usr/bin/env bash")
    # 全新服务器一键部署：拉源码（backend 源码 + dist 均已入库）→ 构建运行环境镜像 → 卷挂载启动
    for kw in ("-r|--repo)", "-b|--branch)", "-d|--dir)", "-p|--port)",
               "git clone --depth 1", "docker compose build", "docker compose up -d",
               "DEFAULT_PORT=40014", "platform/bs-deploy", "源码卷挂载"):
        assert kw in script, f"deploy.sh 缺少：{kw}"
    assert "update.sh" in script  # 已部署实例提示走更新脚本
    _check_bash_syntax(script)


def test_deploy_box_sh():
    script = _read_deploy_script(BOX_DEPLOY_DIR, "box.sh")
    assert script.startswith("#!/usr/bin/env bash")
    # 参数与配置驱动
    for kw in ("-c|--config)", "-i|--ip)", "-n|--name)", "-t|--token)",
               'CFG_FILE="$BOX_DIR/box-config.json"', "codeload.github.com"):
        assert kw in script, f"box.sh 缺少：{kw}"
    # 源码拉取版：直接从公开仓库 tarball 取 box-deploy / edgecore 模板，无 onboard/ 预同步
    assert "platform/box-deploy" in script and "edgecore.template.yaml" in script
    assert "keadm join" in script and "deploy_box.sh" in script
    # 公开仓库不存放动态凭证：token 必须现场提供（配置或 -t）
    assert "公开仓库不存放 token" in script
    # 占位符统一替换（与平台 onboard_box.sh 一致的 python3 逻辑）
    assert "{{HOSTNAME}}" in script and "{{TOKEN}}" in script and "{{CLOUDIP}}" in script
    _check_bash_syntax(script)


def test_deploy_update_sh():
    script = _read_deploy_script(BS_DEPLOY_DIR, "update.sh")
    assert script.startswith("#!/usr/bin/env bash")
    # 开发机模式（本地构建 + rsync + reload 一体化；服务器不自拉 git）
    for kw in ("rsync", "vite build", "--skip-build", "CLOUD_MAIN",
               "docker compose up -d", "服务器不自拉 git"):
        assert kw in script, f"update.sh(开发机模式) 缺少：{kw}"
    # push 子命令：改完代码一键推送到 GitHub（调用仓库根 push.sh）
    assert '"push"' in script and 'exec bash "$ROOT/push.sh"' in script
    assert "代码入库推送" in script
    _check_bash_syntax(script)
    # 仓库根 push.sh：纯 git 推送脚本（协作者通用），已从 bs-deploy/ 迁至仓库根
    root_push = os.path.join(REPO_ROOT, "push.sh")
    assert os.path.isfile(root_push), f"仓库根 push.sh 缺失：{root_push}"
    push_script = open(root_push, encoding="utf-8").read()
    assert push_script.startswith("#!/usr/bin/env bash")
    assert 'cd "$(dirname "$0")"' in push_script      # 位于仓库根（git 根）
    assert 'GIT_REMOTE="github"' in push_script and "git push" in push_script
    _check_bash_syntax(push_script)


# ------------------------- 云端时序数据库（TDengine 历史查询） -------------------------

def test_cloud_tsdb_history(monkeypatch):
    calls = {}

    def fake_http(path, timeout=5):
        calls["path"] = path
        calls["timeout"] = timeout
        return True, {"ok": True, "box": "nt001", "count": 1, "series": [{"t": 1730000000000, "v": 0.41}]}, ""

    monkeypatch.setattr(box_console.cloud_agent, "_http", fake_http)
    res = box_console.cloud_agent.history("nt001", "chengzhong", "chengzhong", "weight",
                                          "1730000000000", "1730086400000", 500)
    assert res["ok"] and res["series"][0]["v"] == 0.41
    # 转发到 agent /api/history，query 完整
    assert "/api/history?" in calls["path"]
    for kw in ("box=nt001", "device=chengzhong", "instance=chengzhong",
               "property=weight", "start=1730000000000", "end=1730086400000", "points=500"):
        assert kw in calls["path"], f"缺少参数：{kw}"
    assert calls["timeout"] == 15


def test_cloud_tsdb_history_requires_box():
    res = box_console.cloud_agent.history("")
    assert not res["ok"] and "box 必填" in res["error"]


def test_cloud_tsdb_history_agent_error(monkeypatch):
    def fake_http(path, timeout=5):
        return False, None, "agent 不可达（云端未部署 cloud-agent）"

    monkeypatch.setattr(box_console.cloud_agent, "_http", fake_http)
    res = box_console.cloud_agent.history("nt001")
    assert not res["ok"] and "agent 不可达" in res["error"]
