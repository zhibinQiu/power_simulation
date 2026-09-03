# -*- coding: utf-8 -*-
"""GitHub 托管：把盒子一键接入资产推送到用户 GitHub 仓库，盒子现场一条命令完成接入。

仓库固定子目录 onboard/（幂等覆盖，分支可配）：
- onboard_box.sh     轻量引导脚本（盒子 `curl -fsSL <raw>/onboard/onboard_box.sh | bash` 执行，
                     自动拉其余资产 + keadm join + 配置下发 + 部署包安装 + 自检）
- box-deploy.tar.gz  采集部署包（mapper + mosquitto + wheels + deploy_box.sh，平台打包）
- edgecore.yaml      KubeEdge 边缘配置（含共享 token + {{HOSTNAME}} 占位，盒子端 sed 替换主机名）
- rootCA.crt         云端根证书（云端重建后需重新同步）
- token              共享接入 token（keadm join 用，token 重签后需重新同步）

配置存储：backend/config/github_config.json（chmod 600，含 GitHub PAT，勿提交版本库）。
盒子接入无 18MB 脚本搬运：部署包/证书/token 都放 GitHub，盒子只 curl 一个几 KB 的引导脚本。
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from .core.config import config_path
from . import box_console, cloud_agent

CONFIG_PATH = config_path("github_config.json")
_REPO_BASE = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
_API_BASE = "https://api.github.com/repos/{owner}/{repo}/contents"

_LAUNCHER = r"""#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 盒子一键接入（GitHub 托管 · 配置文件驱动）
# 由平台「能碳一体机管理 → 盒子接入 → GitHub 托管」同步到云端仓库 onboard/。
# 现场无需源码：只凭一份 box-config.json（平台导出或手工填写）+ 仓库本脚本即可接入。
#
# 用法（盒子 root 下，详细帮助见 bash onboard_box.sh -h）：
#   1) 配置文件驱动（推荐）：把 box-config.json 放到 /opt/weight-bridge/ 后一条命令
#        curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash
#      或显式指定配置路径：
#        curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s -- -c /path/box-config.json
#   2) 命令行参数（无配置文件）：
#        curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s -- -i 36.151.146.71 -n my-box-01
#   3) 仅指定主机名（其余用脚本内置默认 + 仓库 token）：
#        curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s my-box-01
#
# box-config.json 字段（平台「盒子接入 → GitHub 托管」可一键导出）：
#   { "boxId": "my-box-01", "cloudIP": "36.151.146.71", "token": "xxx.yyy.zzz",
#     "repo": "owner/repo", "branch": "master" }
#   - boxId/cloudIP 必填（缺省回落命令行参数 / 脚本内置值 / 当前主机名）；
#   - token 可选：缺省脚本自动从仓库拉取；
#   - repo/branch 可选：现场改用镜像仓库（如 gitee）时填写，将覆盖脚本内置仓库地址。
# 其余未知字段（如 _说明）脚本一律忽略，平台导出内容可直接使用。
# ============================================================================
set -euo pipefail

REPO_BASE="{REPO_BASE}"
BOX_DIR="/opt/weight-bridge"
DEST_DIR="$BOX_DIR/box-deploy"
CFG_FILE=""
BOX_ID=""
CLOUD_IP="{CLOUD_IP}"
TOKEN=""

usage() {
  cat <<'USAGE'
能碳一体机 · 盒子一键接入（GitHub 托管 · 配置文件驱动）

用法（盒子 root）：
  curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash
      用当前主机名 + 内置云端 IP；若 /opt/weight-bridge/box-config.json 存在则自动读取
  curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s -- -c /path/box-config.json
      配置文件驱动（推荐：现场只有一份 box-config.json，无需任何源码）
  curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s -- -i 36.151.146.71 -n my-box-01
      命令行指定云端 IP / 主机名（无配置文件）
  curl -fsSL $REPO_BASE/onboard/onboard_box.sh | bash -s my-box-01
      仅指定主机名（兼容旧用法）

选项：
  -c, --config <file>  box-config.json 路径（JSON：boxId / cloudIP / token / repo / branch）
  -i, --ip <ip>        云端 CloudCore 地址（缺省读配置文件，再回落脚本内置值）
  -n, --name <boxId>   盒子主机名（与云端 K8s 节点名一致，缺省取当前主机名）
  -h, --help           显示本帮助

配置文件字段（其余字段一律忽略）：
  boxId     必填·盒子主机名（与云端 K8s 节点名一致）
  cloudIP   必填·云端 CloudCore / MQTT Broker 地址
  token     可选·共享接入 token（缺省自动从仓库拉取）
  repo      可选·镜像仓库 owner/repo（如改用 gitee 镜像时填写）
  branch    可选·镜像仓库分支（默认 master）
USAGE
  exit 0
}

# ---------- 参数解析：-c 配置文件 / -i 云端 IP / -n 主机名（首位置参数兼容旧用法） ----------
while [ $# -gt 0 ]; do
  case "$1" in
    -c|--config) CFG_FILE="${2:-}"; shift 2 ;;
    -i|--ip)     CLOUD_IP="${2:-}"; shift 2 ;;
    -n|--name)   BOX_ID="${2:-}";   shift 2 ;;
    -h|--help)   usage ;;
    *) BOX_ID="$1"; shift ;;
  esac
done

log()  { echo -e "\033[32m[onboard]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] && { echo "[error] 请以 root 运行（盒子默认 root）"; exit 1; }
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || err "缺少 curl/wget"
command -v python3 >/dev/null 2>&1 || err "缺少 python3（解析配置文件 / 替换 edgecore.yaml 占位符）"
fetch() { if command -v curl >/dev/null 2>&1; then curl -fsSL "$1"; else wget -qO- "$1"; fi; }

# ---------- 配置文件驱动（优先级：-c 指定 > 默认路径 /opt/weight-bridge/box-config.json） ----------
[ -z "$CFG_FILE" ] && [ -f "$BOX_DIR/box-config.json" ] && CFG_FILE="$BOX_DIR/box-config.json"
if [ -n "$CFG_FILE" ]; then
  [ -f "$CFG_FILE" ] || err "配置文件不存在：$CFG_FILE"
  log "读取配置文件：$CFG_FILE"
  read -r CFG_BOX_ID CFG_CLOUD_IP CFG_TOKEN CFG_REPO CFG_BRANCH <<< "$(python3 - "$CFG_FILE" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])) or {}
print(c.get("boxId", "") or "", c.get("cloudIP", "") or "", c.get("token", "") or "",
      c.get("repo", "") or "", c.get("branch", "") or "")
PY
)" || true
  BOX_ID="${BOX_ID:-$CFG_BOX_ID}"
  CLOUD_IP="${CLOUD_IP:-$CFG_CLOUD_IP}"
  TOKEN="${CFG_TOKEN:-}"
  if [ -n "$CFG_REPO" ]; then
    REPO_BASE="https://raw.githubusercontent.com/${CFG_REPO}/${CFG_BRANCH:-master}"
    log "仓库覆盖：$REPO_BASE"
  fi
fi
ONBOARD_BASE="$REPO_BASE/onboard"
BOX_ID="${BOX_ID:-$(hostname)}"
[ -n "$CLOUD_IP" ] || err "缺少云端 IP：请用 -i 指定，或在 box-config.json 填 cloudIP 字段"
[ -n "$TOKEN" ] || TOKEN="$(fetch "$ONBOARD_BASE/token" | tr -d '\r\n ')"

# ---------- ① EdgeCore 基础接入（全新盒子 keadm join；已接入自动跳过） ----------
if systemctl is-active edgecore.service >/dev/null 2>&1; then
  log "edgecore 服务已在运行，跳过 keadm join（沿用现有接入）"
else
  command -v keadm >/dev/null 2>&1 || err "盒子未安装 keadm（EdgeCore 基础未接入）。请先安装 keadm 后重跑"
  [ -n "$TOKEN" ] || TOKEN="$(fetch "$ONBOARD_BASE/token" | tr -d '\r\n ')"
  [ -n "$TOKEN" ] || err "无法获取共享 token（请先在平台「盒子接入 → GitHub 托管」同步，或在 box-config.json 填写 token）"
  log "执行 keadm join 接入云端 CloudCore ($CLOUD_IP:10000)..."
  keadm join --cloudcore-ipport=$CLOUD_IP:10000 --token="$TOKEN" \
    --kubeedge-version=v1.20.0 --with-edge-core \
    || warn "keadm join 失败（若盒子已接入可忽略；详见上方输出）"
fi

# ---------- ② 配置下发（rootCA / edgecore.yaml，占位符统一替换，幂等覆盖） ----------
mkdir -p /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config
fetch "$ONBOARD_BASE/rootCA.crt" > /etc/kubeedge/ca/rootCA.crt
[ -s /etc/kubeedge/ca/rootCA.crt ] || err "rootCA 下载失败"
fetch "$ONBOARD_BASE/edgecore.yaml" > /etc/kubeedge/config/edgecore.yaml
[ -s /etc/kubeedge/config/edgecore.yaml ] || err "edgecore.yaml 下载失败"
[ -n "$TOKEN" ] || TOKEN="$(fetch "$ONBOARD_BASE/token" | tr -d '\r\n ')"
[ -n "$TOKEN" ] || warn "token 为空（edgecore.yaml 将保留 {{TOKEN}} 占位，edgeHub 握手可能失败）"
python3 - /etc/kubeedge/config/edgecore.yaml "$BOX_ID" "$CLOUD_IP" "$TOKEN" <<'PY'
import sys
path, box_id, cloud_ip, token = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
s = open(path).read()
for k, v in (("{{HOSTNAME}}", box_id), ("{{CLOUDIP}}", cloud_ip), ("{{TOKEN}}", token)):
    s = s.replace(k, v)
open(path, "w").write(s)
PY
systemctl daemon-reload 2>/dev/null || true
if systemctl list-unit-files edgecore.service >/dev/null 2>&1; then
  systemctl restart edgecore.service 2>/dev/null || warn "edgecore 重启失败（可手动 systemctl restart edgecore.service）"
fi
log "edgecore.yaml 已下发（hostname=$BOX_ID，cloud=$CLOUD_IP）"

# ---------- ③ 下载并解包 box-deploy 采集部署包 ----------
mkdir -p "$DEST_DIR"
fetch "$ONBOARD_BASE/box-deploy.tar.gz" > /tmp/box-deploy.tar.gz
[ -s /tmp/box-deploy.tar.gz ] || err "box-deploy.tar.gz 下载失败"
tar -xzf /tmp/box-deploy.tar.gz -C "$DEST_DIR"
rm -f /tmp/box-deploy.tar.gz
log "已解包 box-deploy 到 $DEST_DIR"

# ---------- ④ 首次生成 config.json 时自动定制 boxId/broker ----------
if [ ! -f "$BOX_DIR/config.json" ]; then
  cp "$DEST_DIR/mapper/config.json" "$BOX_DIR/config.json"
  python3 - "$BOX_DIR/config.json" "$BOX_ID" "$CLOUD_IP" <<'PY'
import json, sys
path, box_id, cloud_ip = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(path))
cfg.setdefault("mqtt", {})
cfg["mqtt"]["boxId"] = box_id
cfg["mqtt"].setdefault("broker", {})
cfg["mqtt"]["broker"]["host"] = cloud_ip
json.dump(cfg, open(path, "w"), indent=2, ensure_ascii=False)
PY
  log "已生成 $BOX_DIR/config.json（mqtt.boxId=$BOX_ID，broker=$CLOUD_IP:41883），可按现场定制后 systemctl restart box-mapper.service"
else
  log "保留已有 $BOX_DIR/config.json（如需调整 mqtt.boxId/broker 请手动修改）"
fi

# ---------- ⑤ 一键部署（幂等）+ 链路自检 ----------
chmod +x "$DEST_DIR/deploy_box.sh"
cd "$DEST_DIR"
./deploy_box.sh
log "链路自检："
./deploy_box.sh --check || warn "自检发现问题（详见上方输出；可重跑本命令幂等修复）"

log "一键接入完成！盒子 $BOX_ID 已接入云端 $CLOUD_IP（CloudHub 10002）。"
log "下一步：在平台「能碳一体机管理 → 设备管理」下发设备 YAML，设备读数将经 DMI/MQTT 上报云端。"
exit 0
"""


def _load_cfg() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_config() -> Dict[str, Any]:
    cfg = _load_cfg()
    if not cfg.get("owner") or not cfg.get("repo"):
        return {"ok": False, "error": "GitHub 配置未设置：请在「盒子接入 → GitHub 托管」填写 owner/repo 并保存"}
    return {
        "ok": True,
        "owner": cfg.get("owner", ""),
        "repo": cfg.get("repo", ""),
        "branch": cfg.get("branch", "master"),
        "token_set": bool(cfg.get("token")),
    }


def save_config(p: Dict[str, Any]) -> Dict[str, Any]:
    owner = str(p.get("owner", "")).strip()
    repo = str(p.get("repo", "")).strip()
    token = str(p.get("token", "")).strip()
    branch = str(p.get("branch", "")).strip() or "master"
    if not owner or not repo:
        return {"ok": False, "error": "owner 与 repo 不能为空"}
    old = _load_cfg()
    if not token:
        token = str(old.get("token") or "")  # token 留空表示沿用已保存的
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"owner": owner, "repo": repo, "branch": branch, "token": token}, f,
                  ensure_ascii=False, indent=2)
    os.chmod(CONFIG_PATH, 0o600)
    return {"ok": True, "token_set": bool(token)}


def _gh_request(method: str, url: str, token: str, body: Dict[str, Any] | None = None,
                timeout: int = 60):
    req = urllib.request.Request(url, method=method)
    if token:  # 公开仓库匿名读取无需认证；带 token 用于私有仓库 / 写入
        req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "power-simulation-platform")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # noqa: BLE001 - 网络异常统一收敛为错误码
        return -1, {"message": str(e)}


def _put_file(cfg: Dict[str, Any], path: str, data: bytes, message: str,
              timeout: int = 300) -> Dict[str, Any]:
    """GitHub Contents API：文件已存在则带 sha 更新，否则新建（同一分支，幂等）。"""
    owner, repo, branch, token = cfg["owner"], cfg["repo"], cfg["branch"], cfg["token"]
    url = f"{_API_BASE.format(owner=owner, repo=repo)}/{path}"
    sha = None
    code, body = _gh_request("GET", url, token, timeout=30)
    if code == 200 and body.get("sha"):
        sha = body["sha"]
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    code, body = _gh_request("PUT", url, token, body=payload, timeout=timeout)
    if code in (200, 201):
        return {"ok": True, "path": path, "size": len(data), "updated": bool(sha)}
    return {"ok": False, "path": path, "error": f"HTTP {code}: {body.get('message', body)}"}


def _build_assets(cloud_ip: str, owner: str, repo: str, branch: str) -> Dict[str, Any]:
    """生成全部资产字节（token/rootCA 实时取自云端 agent；部署包平台打包）。"""
    cloud = box_console._fetch_cloud_k8s(force=True)
    tok_data = cloud.get("token") or {}
    token = (tok_data.get("value") or "").strip()
    if not token:
        return {"ok": False,
                "error": f"无法从云端获取共享 token（{cloud.get('error') or tok_data.get('expires')}）。"
                         f"请先确认「总览 → 配置」中的云端 agent 已配置且云端可达。"}
    rc = cloud_agent.rootca()
    rootca_b64 = rc.get("data") or ""
    if not rc.get("ok") or not rootca_b64:
        return {"ok": False, "error": f"无法从云端获取 rootCA（{rc.get('error') or '云端 agent 不可达'}）。"
                                      f"请先确认云端 agent 可用（/api/rootca）。"}
    tpl = box_console.EDGECORE_TEMPLATE.read_text("utf-8") if box_console.EDGECORE_TEMPLATE.exists() else ""
    # GitHub 版保留全部占位符（{{HOSTNAME}}/{{TOKEN}}/{{CLOUDIP}}），
    # 由盒子端脚本按 box-config.json / 命令行参数统一替换 —— 仓库资产完全通用，
    # 云端重建 / token 重签后无需重新同步（只需更新仓库 token 文件或现场改配置）。
    edgecore_yaml = tpl
    launcher = _render_launcher(cloud_ip, owner, repo, branch)
    deploy_gz = box_console._pack_box_deploy()
    return {
        "ok": True,
        "token": token,
        "caHash": token.split(".")[0],
        "assets": {
            "onboard_box.sh": launcher.encode("utf-8"),
            "edgecore.yaml": edgecore_yaml.encode("utf-8"),
            "rootCA.crt": base64.b64decode(rootca_b64),
            "token": token.encode("utf-8"),
            "box-deploy.tar.gz": deploy_gz,
        },
    }


def _render_launcher(cloud_ip: str, owner: str, repo: str, branch: str) -> str:
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
    return (_LAUNCHER
            .replace("{REPO_BASE}", base)
            .replace("{CLOUD_IP}", cloud_ip))


def push_to_github(cloud_ip: str) -> Dict[str, Any]:
    """把盒子一键接入资产同步到 GitHub 仓库 onboard/ 目录（幂等）。返回每文件状态 + 盒子命令。"""
    cfg = _load_cfg()
    if not cfg.get("owner") or not cfg.get("repo"):
        return {"ok": False, "error": "GitHub 配置未设置：请在「盒子接入 → GitHub 托管」填写 owner/repo 并保存"}
    if not cfg.get("token"):
        return {"ok": False, "error": "GitHub token 未配置（contents 写权限 PAT）：同步写入仓库需要它。"
                                      "公开仓库的读取与盒子现场 curl 拉取无需任何验证"}
    built = _build_assets(cloud_ip, cfg["owner"], cfg["repo"], cfg["branch"])
    if not built.get("ok"):
        return built
    files: list[Dict[str, Any]] = []
    for name in ("onboard_box.sh", "edgecore.yaml", "rootCA.crt", "token", "box-deploy.tar.gz"):
        files.append(_put_file(cfg, f"onboard/{name}", built["assets"][name],
                               message=f"[平台] 同步盒子一键接入资产 {name}"))
    ok = all(f["ok"] for f in files)
    launcher_url = f"{_REPO_BASE.format(owner=cfg['owner'], repo=cfg['repo'], branch=cfg['branch'])}/onboard/onboard_box.sh"
    return {
        "ok": ok,
        "files": files,
        "error": "" if ok else ("同步失败：" + "; ".join(
            f"{f.get('path')}: {f.get('error')}" for f in files if not f.get("ok"))),
        "launcher_url": launcher_url,
        "command": f"curl -fsSL {launcher_url} | bash",
        "caHash": built.get("caHash"),
        "token_head": built.get("token", "")[:20],
    }


def export_box_config(box_id: str = "", cloud_ip: str = "") -> Dict[str, Any]:
    """导出盒子现场接入配置文件 box-config.json（平台一键生成）。

    场景：现场无平台、无源码，手头只有这份配置文件 ——
      把 box-config.json 放到盒子 /opt/weight-bridge/ 后执行
        curl -fsSL <仓库>/onboard/onboard_box.sh | bash
      脚本自动读取配置完成接入（EdgeCore join + box-deploy 部署）。
    云端不可达时 token 留空，脚本会自动从仓库拉取，不影响接入；
    repo/branch 留空时脚本使用仓库内置地址（即本配置导出的仓库）。
    """
    cloud_ip = str(cloud_ip or "").strip()
    if not cloud_ip:
        return {"ok": False, "error": "cloudIP（云端 CloudCore 地址）不能为空"}
    box_id = str(box_id or "").strip()
    cfg = _load_cfg()
    token = ""
    ca_hash = ""
    cloud = box_console._fetch_cloud_k8s(force=True)
    tok_data = cloud.get("token") or {}
    token = (tok_data.get("value") or "").strip()
    if token:
        ca_hash = token.split(".")[0]
    data = {
        "boxId": box_id,
        "cloudIP": cloud_ip,
        "token": token,
        "repo": (f"{cfg.get('owner')}/{cfg.get('repo')}"
                 if cfg.get("owner") and cfg.get("repo") else ""),
        "branch": cfg.get("branch") or "master",
    }
    content = {
        "_说明": "能碳一体机盒子现场接入配置。配合仓库 onboard_box.sh 使用：把本文件放到盒子 "
                "/opt/weight-bridge/box-config.json 后，执行 curl -fsSL <仓库>/onboard/onboard_box.sh | bash 即可一键接入。"
                "boxId/cloudIP 必填；token 留空时脚本自动从仓库拉取；repo/branch 用于覆盖镜像仓库地址。",
        **data,
    }
    return {
        "ok": True,
        "config": data,
        "content": json.dumps(content, ensure_ascii=False, indent=2),
        "caHash": ca_hash,
        "token_set": bool(token),
    }
