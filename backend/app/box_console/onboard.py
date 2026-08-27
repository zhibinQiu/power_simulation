"""盒子接入（onboard）：一键接入自解压脚本生成 / 下载 / 远程推送执行。

脚本内嵌 box-deploy 采集部署包（tar.gz base64）+ rootCA + edgecore.yaml + 共享 token，
免除现场手工 scp 上传；token/caHash/rootCA 均来自云端真实环境（云端 agent 通道，免 SSH）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
import tarfile
from datetime import datetime
from typing import Any, Dict, List

from .. import cloud_agent
from . import overview
from ._shared import (BOX_DEPLOY_DIR, EDGECORE_TEMPLATE, GENERATED_DIR,
                      ONBOARD_SCRIPT_PATH)


def _pack_box_deploy() -> bytes:
    """把 platform/box-deploy 采集部署包打包为 tar.gz（排除 __pycache__/编译缓存），
    经 base64 内嵌进一键接入脚本，免除现场手工 scp 上传部署包。"""
    if not BOX_DEPLOY_DIR.is_dir():
        raise FileNotFoundError(f"box-deploy 部署包目录不存在：{BOX_DEPLOY_DIR}")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for f in sorted(BOX_DEPLOY_DIR.rglob("*")):
            if "__pycache__" in f.parts or f.suffix in (".pyc", ".pyo") or f.name == ".DS_Store":
                continue
            rel = f.relative_to(BOX_DEPLOY_DIR)
            if f.is_dir():
                info = tarfile.TarInfo(str(rel) + "/")
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tf.addfile(info)
            elif f.is_file():
                tf.add(f, arcname=str(rel))
    return buf.getvalue()


def _render_onboard_script(hostname: str, cloud_ip: str, edgecore_yaml: str,
                           rootca_b64: str, token: str, deploy_b64: str) -> str:
    """渲染盒子一键接入自解压脚本：bash 头 + 内嵌 base64(box-deploy.tar.gz) + 配置定制。

    脚本执行流程（幂等，可重复跑）：
      ① EdgeCore 接入（edgecore 未运行且存在 keadm → keadm join；已接入自动跳过）
      ② 写 rootCA.crt / edgecore.yaml（rootCA 内嵌失败时降级 scp）
      ③ 解包 box-deploy 到 /opt/weight-bridge/box-deploy
      ④ 首次生成 config.json 时自动定制 mqtt.boxId=hostname、broker=cloud_ip:41883
      ⑤ ./deploy_box.sh 一键部署（依赖/mapper/mosquitto，全离线）
      ⑥ ./deploy_box.sh --check 自检
    """
    script = r"""#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 盒子一键接入脚本（onboard_box.sh）
# 由平台「能碳一体机管理 → 盒子接入」自动生成，内含 box-deploy 采集部署包
# （tar.gz base64）+ edgecore.yaml + rootCA.crt，无需手工 scp 上传。
#
# 用法（盒子 root 下执行一条命令即可，幂等可重跑）：
#   bash onboard_box.sh            # 完整接入
#   bash onboard_box.sh --check    # 仅链路自检
# ============================================================================
set -euo pipefail

HOSTNAME="{HOSTNAME}"
CLOUD_IP="{CLOUD_IP}"
BOX_DIR="/opt/weight-bridge"
DEST_DIR="$BOX_DIR/box-deploy"
MAPPER_SVC="box-mapper.service"
ONBOARD_TOKEN="{TOKEN}"

log()  {{ echo -e "\033[32m[onboard]\033[0m $*"; }}
warn() {{ echo -e "\033[33m[warn ]\033[0m $*"; }}
err()  {{ echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }}

[ "$(id -u)" -ne 0 ] && {{ echo "[error] 请以 root 运行（盒子默认 root）"; exit 1; }}
command -v tar >/dev/null 2>&1 || err "缺少 tar 命令"
[ "${{1:-}}" = "--check" ] && DO_CHECK=1 || DO_CHECK=0

# ---------- ① EdgeCore 基础接入（全新盒子 keadm join；已接入自动跳过） ----------
if systemctl is-active edgecore.service >/dev/null 2>&1; then
  log "edgecore 服务已在运行，跳过 keadm join（沿用现有接入）"
else
  if command -v keadm >/dev/null 2>&1; then
    log "执行 keadm join 接入云端 CloudCore ($CLOUD_IP:10000)..."
    keadm join --cloudcore-ipport=$CLOUD_IP:10000 --token="$ONBOARD_TOKEN" \
      --kubeedge-version=v1.20.0 --with-edge-core \
      || warn "keadm join 失败（若盒子已接入可忽略；详见上方输出）"
  else
    err "盒子未安装 keadm（EdgeCore 基础未接入）。请先在盒子安装 keadm 后重跑本脚本"
  fi
fi

# ---------- ② 配置下发（rootCA / edgecore.yaml，幂等覆盖） ----------
mkdir -p /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config
if [ -n "{ROOTCA_B64}" ]; then
  echo "{ROOTCA_B64}" | base64 -d > /etc/kubeedge/ca/rootCA.crt
  log "已写入 /etc/kubeedge/ca/rootCA.crt（内嵌，来自云端真实 CA）"
else
  warn "rootCA 未内嵌（云端 agent 不可达），尝试从云端 scp（需盒子能 SSH 到云端）："
  scp root@$CLOUD_IP:/etc/kubeedge/ca/rootCA.crt /etc/kubeedge/ca/rootCA.crt \
    || err "rootCA 获取失败，请将云端 /etc/kubeedge/ca/rootCA.crt 手动放到盒子同路径后重跑"
fi
cat > /etc/kubeedge/config/edgecore.yaml <<'EDGECORE_YAML'
{EDGECORE_YAML}
EDGECORE_YAML
systemctl daemon-reload 2>/dev/null || true
if systemctl list-unit-files edgecore.service >/dev/null 2>&1; then
  systemctl restart edgecore.service 2>/dev/null || warn "edgecore 重启失败（可手动 systemctl restart edgecore.service）"
fi
log "edgecore.yaml 已写入 /etc/kubeedge/config/"

[ "$DO_CHECK" -eq 1 ] && {{
  cd "$DEST_DIR" 2>/dev/null || err "请先执行完整接入（生成部署包）后再 --check"
  ./deploy_box.sh --check
  exit 0
}}

# ---------- ③ 解包 box-deploy 采集部署包 ----------
PAYLOAD_TMP="$(mktemp)"
awk '/^__ONBOARD_PAYLOAD__$/ {{ found=1; next }} found {{ printf "%s", $0 }}' "$0" > "$PAYLOAD_TMP"
[ -s "$PAYLOAD_TMP" ] || err "脚本内嵌数据损坏（未找到 __ONBOARD_PAYLOAD__ 段）"
mkdir -p "$DEST_DIR"
base64 -d "$PAYLOAD_TMP" | tar -xzf - -C "$DEST_DIR"
rm -f "$PAYLOAD_TMP"
log "已解包 box-deploy 到 $DEST_DIR"

# ---------- ④ 首次生成 config.json 时自动定制 boxId/broker ----------
if [ ! -f "$BOX_DIR/config.json" ]; then
  cp "$DEST_DIR/mapper/config.json" "$BOX_DIR/config.json"
  python3 - "$BOX_DIR/config.json" "$HOSTNAME" "$CLOUD_IP" <<'PY'
import json, sys
path, box_id, cloud_ip = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(path))
cfg.setdefault("mqtt", {})
cfg["mqtt"]["boxId"] = box_id
cfg["mqtt"].setdefault("broker", {})
cfg["mqtt"]["broker"]["host"] = cloud_ip
json.dump(cfg, open(path, "w"), indent=2, ensure_ascii=False)
PY
  log "已生成 $BOX_DIR/config.json（mqtt.boxId=$HOSTNAME，broker=$CLOUD_IP:41883），可按现场定制后 systemctl restart $MAPPER_SVC"
else
  log "保留已有 $BOX_DIR/config.json（如需调整 mqtt.boxId/broker 请手动修改）"
fi

# ---------- ⑤ 一键部署（幂等：依赖离线安装 + mapper + mosquitto + systemd） ----------
chmod +x "$DEST_DIR/deploy_box.sh"
cd "$DEST_DIR"
./deploy_box.sh

# ---------- ⑥ 链路自检 ----------
log "链路自检："
./deploy_box.sh --check || warn "自检发现问题（详见上方输出；可重跑本脚本幂等修复）"

log "一键接入完成！盒子 $HOSTNAME 已接入云端 $CLOUD_IP（CloudHub 10002）。"
log "下一步：在平台「能碳一体机管理 → 设备管理」下发设备 YAML，设备读数将经 DMI/MQTT 上报云端。"
exit 0

__ONBOARD_PAYLOAD__
{PAYLOAD_B64}
"""
    return (script
            .replace("{HOSTNAME}", hostname)
            .replace("{CLOUD_IP}", cloud_ip)
            .replace("{ROOTCA_B64}", rootca_b64)
            .replace("{EDGECORE_YAML}", edgecore_yaml.rstrip("\n"))
            .replace("{TOKEN}", token)
            .replace("{PAYLOAD_B64}", deploy_b64)
            # 还原 bash 双花括号转义（需在命名占位符替换之后，避免误伤内嵌内容）
            .replace("{{", "{")
            .replace("}}", "}"))


def _generate_onboard(hostname: str, cloud_ip: str, box_ip: str = "") -> Dict[str, Any]:
    """生成盒子一键接入自解压脚本（内嵌 box-deploy 包 + rootCA + edgecore.yaml + token），
    写入 GENERATED_DIR/onboard_box.sh 供下载 / 远程推送。返回完整元信息。"""
    cloud = overview._fetch_cloud_k8s(force=True)
    tok_data = cloud.get("token") or {}
    tok = (tok_data.get("value") or "").strip()
    if not tok:
        return {"ok": False,
                "error": f"无法从云端获取真实共享 token（{cloud.get('error') or tok_data.get('expires')}）。"
                         f"请先确认「总览 → 配置」中的云端 agent 已配置且云端可达。"}
    token = tok
    # KubeEdge 共享 token 为四段式：caHash.header.payload.signature
    ca_hash = token.split(".")[0]
    tpl = EDGECORE_TEMPLATE.read_text("utf-8") if EDGECORE_TEMPLATE.exists() else ""
    edgecore_yaml = (
        tpl.replace("{{HOSTNAME}}", hostname)
        .replace("{{TOKEN}}", token)
        .replace("{{CLOUDIP}}", cloud_ip)
    )
    # rootCA：优先云端 agent 拉取（免 SSH），失败降级为脚本内 scp 兜底
    rootca_b64 = ""
    rc = cloud_agent.rootca()
    if rc.get("ok"):
        rootca_b64 = str(rc.get("data") or "")
    # box-deploy 打包内嵌（tar.gz -> base64）
    deploy_b64 = base64.b64encode(_pack_box_deploy()).decode("ascii")
    script = _render_onboard_script(hostname, cloud_ip, edgecore_yaml, rootca_b64, token, deploy_b64)
    script_bytes = script.encode("utf-8")
    # 落盘：下载接口 / 远程一键接入复用同一份
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    ONBOARD_SCRIPT_PATH.write_bytes(script_bytes)
    # 保留五步手工命令（旧前端/高级视图用；日常走一键脚本）
    box_conn = f"root@{box_ip}" if box_ip else "root@<盒子IP>"
    cmds = [
        "# ═══ 一键接入（推荐）：把平台生成的 onboard_box.sh 放到盒子，执行：",
        "bash /opt/onboard_box.sh",
        "",
        "# ═══ 手工五步（备选）：① EdgeCore 接入（全新盒子）═══",
        f"keadm join --cloudcore-ipport={cloud_ip}:10000 --token={token} --kubeedge-version=v1.20.0 --with-edge-core",
        "# ② 配置下发（rootCA/edgecore.yaml 已内嵌进 onboard_box.sh；手工时：）",
        "mkdir -p /etc/kubeedge/ca /etc/kubeedge/config",
        f"scp root@{cloud_ip}:/etc/kubeedge/ca/rootCA.crt /etc/kubeedge/ca/rootCA.crt",
        f"cat > /etc/kubeedge/config/edgecore.yaml << 'EOF'\n{edgecore_yaml}\nEOF",
        "systemctl daemon-reload && systemctl restart edgecore.service",
        "# ③ 上传并部署采集部署包（已内嵌进 onboard_box.sh，此处仅备选）：",
        f"scp -r {BOX_DEPLOY_DIR} {box_conn}:/opt/weight-bridge/box-deploy",
        f"ssh {box_conn} \"cd /opt/weight-bridge/box-deploy && ./deploy_box.sh\"",
        "# ④ 按现场定制 /opt/weight-bridge/config.json（改完 systemctl restart box-mapper 生效）",
        "# ⑤ 云端创建设备：平台「能碳一体机管理 → 设备管理」一键下发",
    ]
    return {
        "ok": True,
        "edgecore": edgecore_yaml,
        "token": token,
        "token_source": tok_data.get("source", "cloud"),
        "token_expires": tok_data.get("expires", ""),
        "caHash": ca_hash,
        "hostname": hostname,
        "cloudIP": cloud_ip,
        "boxIP": box_ip,
        "commands": cmds,
        "source": "cloud",   # token/caHash 均来自云端真实环境
        "script_name": "onboard_box.sh",
        "script_size": len(script_bytes),
        "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
        "script_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rootca_inline": bool(rootca_b64),
        "script_hint": (f"一键接入脚本已生成（{len(script_bytes) // 1024} KB）。"
                        f"下载到盒子执行 `bash onboard_box.sh`，或点击「远程一键接入」由云端 agent 推送执行。"),
    }


def onboard_node(p: Dict[str, Any]) -> Dict[str, Any]:
    """盒子接入：生成自解压一键脚本（内嵌 box-deploy 包 + rootCA + edgecore.yaml + token）。

    token/caHash/rootCA 均来自云端真实环境（云端 agent 通道，免 SSH）。
    """
    hostname = str(p.get("hostname", "edge-box")).strip() or "edge-box"
    cloud_ip = str(p.get("cloudIP", "")).strip()
    box_ip = str(p.get("boxIP", "")).strip()
    if not cloud_ip:
        return {"ok": False, "error": "cloudIP（云端 CloudCore 地址）不能为空"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", hostname):
        return {"ok": False, "error": f"盒子主机名不合法：{hostname}（仅允许字母/数字/点/短横线/下划线）"}
    return _generate_onboard(hostname, cloud_ip, box_ip)


def onboard_script_download() -> Dict[str, Any]:
    """返回已生成的一键接入脚本内容（base64），供前端下载/展示。"""
    if not ONBOARD_SCRIPT_PATH.is_file():
        return {"ok": False, "error": "一键接入脚本尚未生成：请先在「盒子接入」弹窗点「生成一键脚本」"}
    script_bytes = ONBOARD_SCRIPT_PATH.read_bytes()
    return {
        "ok": True,
        "script_b64": base64.b64encode(script_bytes).decode("ascii"),
        "script_name": "onboard_box.sh",
        "script_size": len(script_bytes),
        "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
        "script_generated_at": datetime.fromtimestamp(
            ONBOARD_SCRIPT_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


def box_onboard_remote(p: Dict[str, Any]) -> Dict[str, Any]:
    """盒子远程一键接入：生成脚本 → 云端 agent 经 SSH 推送到盒子并执行。

    前提：① 平台⇄云端 agent 已配置（「总览 → 配置」）；② 云端 agent 的 config.json
    已配置 edge（盒子可达地址 + 密码/密钥）。盒子无直达 IP 时云端无法 SSH 直达，
    请改用「下载脚本 → 现场 bash onboard_box.sh」。
    body 可选：boxIP/port/user/password/key 覆盖云端 agent 默认 edge 连接。
    """
    hostname = str(p.get("hostname", "edge-box")).strip() or "edge-box"
    cloud_ip = str(p.get("cloudIP", "")).strip()
    box_ip = str(p.get("boxIP", "")).strip()
    if not cloud_ip:
        return {"ok": False, "error": "cloudIP（云端 CloudCore 地址）不能为空"}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", hostname):
        return {"ok": False, "error": f"盒子主机名不合法：{hostname}（仅允许字母/数字/点/短横线/下划线）"}
    gen = _generate_onboard(hostname, cloud_ip, box_ip)
    if not gen.get("ok"):
        return gen
    # edge 连接：前端传入（boxIP + 凭据）覆盖云端 agent 默认 edge 配置
    edge: Dict[str, Any] = {}
    if box_ip:
        edge["host"] = box_ip
    for k in ("port", "user", "password", "key"):
        if p.get(k):
            edge[k] = p[k]
    script_b64 = base64.b64encode(ONBOARD_SCRIPT_PATH.read_bytes()).decode("ascii")
    steps: List[Dict[str, Any]] = []
    up = cloud_agent.edge_upload("/opt/onboard_box.sh", script_b64, mode="0755", edge=edge or None)
    steps.append({
        "name": "上传脚本到盒子 /opt/onboard_box.sh",
        "ok": bool(up.get("ok")),
        "bytes": up.get("bytes", 0),
        "detail": (up.get("stderr") or "")[:2000] or (up.get("stdout") or "")[:2000],
    })
    if not up.get("ok"):
        return {"ok": False, "steps": steps,
                "error": "脚本上传失败：" + ((up.get("stderr") or up.get("stdout") or "云端 agent 不可达")
                                            + "。若盒子无直达 IP，请下载脚本后到现场执行 bash onboard_box.sh")}
    run = cloud_agent.edge_run("bash /opt/onboard_box.sh", timeout=900, edge=edge or None)
    detail = (run.get("stdout") or "")[-4000:]
    if run.get("stderr"):
        detail += "\n[stderr] " + str(run.get("stderr"))[-2000:]
    steps.append({
        "name": "盒子执行 bash /opt/onboard_box.sh",
        "ok": bool(run.get("ok")),
        "rc": run.get("rc", 1),
        "detail": detail,
    })
    return {
        "ok": bool(run.get("ok")),
        "steps": steps,
        "error": "" if run.get("ok") else (str(run.get("stderr")) or "盒子远程执行失败"),
        "hostname": hostname,
        "cloudIP": cloud_ip,
        "script_name": "onboard_box.sh",
        "script_size": ONBOARD_SCRIPT_PATH.stat().st_size,
    }
