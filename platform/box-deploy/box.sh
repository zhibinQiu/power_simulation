#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 全新盒子一键接入（GitHub 源码拉取版 · 公开仓库无需预同步）
#
# 与平台「GitHub 托管」方案的区别：无需平台先「同步资产」到仓库 onboard/，
# 盒子直接从公开源码仓库拉取 box-deploy 部署包与 edgecore 模板完成接入。
# 唯一仍需现场提供的动态凭证：共享接入 token（云端 keadm token，公开仓库不存放）。
#
# 用法（盒子 root，Debian/Ubuntu arm64）：
#   1) 配置文件驱动（推荐）：把 box-config.json 放到 /opt/weight-bridge/ 后一条命令
#        curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/platform/box-deploy/box.sh | bash
#      box-config.json 字段（其余字段一律忽略）：
#        { "boxId": "my-box-01", "cloudIP": "36.151.146.71", "token": "xxx.yyy.zzz",
#          "repo": "owner/repo", "branch": "master", "rootCA": "<base64 可选>" }
#   2) 命令行参数（无配置文件）：
#        curl -fsSL <同上> | bash -s -- -i 36.151.146.71 -n my-box-01 -t <token>
#   3) 仅指定主机名（兼容旧用法，其余用脚本内置默认）：
#        curl -fsSL <同上> | bash -s my-box-01
#
# 选项：
#   -c, --config <file>  box-config.json 路径（默认 /opt/weight-bridge/box-config.json）
#   -i, --ip <ip>        云端 CloudCore / MQTT Broker 地址
#   -n, --name <boxId>   盒子主机名（与云端 K8s 节点名一致，缺省取当前主机名）
#   -t, --token <token>  共享接入 token（keadm join 必填，公开仓库不存放）
#   -r, --repo <owner/repo>  源码仓库（默认内置）
#   -b, --branch <branch>    分支（默认 master）
#       --ca <file>       rootCA.crt 文件（可选；keadm join 会自动从云端拉取）
#   -h, --help           显示本帮助
# ============================================================================
set -euo pipefail

DEFAULT_REPO="zhibinQiu/power_simulation"   # ← 改为你的公开仓库 owner/repo
DEFAULT_BRANCH="master"
DEFAULT_CLOUD_IP=""
BOX_DIR="/opt/weight-bridge"
DEST_DIR="$BOX_DIR/box-deploy"

CFG_FILE=""
BOX_ID=""
CLOUD_IP="$DEFAULT_CLOUD_IP"
TOKEN=""
REPO="$DEFAULT_REPO"
BRANCH="$DEFAULT_BRANCH"
ROOTCA_FILE=""

usage() {
  cat <<'USAGE'
能碳一体机 · 全新盒子一键接入（GitHub 源码拉取版）

用法（盒子 root）：
  curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/platform/box-deploy/box.sh | bash
      自动读取 /opt/weight-bridge/box-config.json（boxId/cloudIP/token 必填）
  curl -fsSL <同上> | bash -s -- -c /path/box-config.json
      指定配置文件
  curl -fsSL <同上> | bash -s -- -i 36.151.146.71 -n my-box-01 -t <token>
      命令行指定（无配置文件）

选项：
  -c, --config <file>  box-config.json 路径
  -i, --ip <ip>        云端 CloudCore / MQTT Broker 地址
  -n, --name <boxId>   盒子主机名（与云端 K8s 节点名一致）
  -t, --token <token>  共享接入 token（keadm join 必填）
  -r, --repo <owner/repo>  源码仓库（默认内置）
  -b, --branch <branch>    分支（默认 master）
      --ca <file>       rootCA.crt 文件（可选）
  -h, --help           显示本帮助

box-config.json 字段：
  boxId     必填·盒子主机名（与云端 K8s 节点名一致）
  cloudIP   必填·云端 CloudCore / MQTT Broker 地址
  token     必填·共享接入 token（公开仓库不存放，需平台导出或云端获取）
  repo      可选·源码仓库 owner/repo（默认内置）
  branch    可选·源码分支（默认 master）
  rootCA    可选·rootCA.crt 的 base64（keadm join 会自动从云端拉取，一般无需提供）
USAGE
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -c|--config) CFG_FILE="${2:-}"; shift 2 ;;
    -i|--ip)     CLOUD_IP="${2:-}"; shift 2 ;;
    -n|--name)   BOX_ID="${2:-}";   shift 2 ;;
    -t|--token)  TOKEN="${2:-}";    shift 2 ;;
    -r|--repo)   REPO="${2:-}";     shift 2 ;;
    -b|--branch) BRANCH="${2:-}";   shift 2 ;;
    --ca)        ROOTCA_FILE="${2:-}"; shift 2 ;;
    -h|--help)   usage ;;
    *) BOX_ID="$1"; shift ;;
  esac
done

log()  { echo -e "\033[32m[onboard]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] && err "请以 root 运行（盒子默认 root）"
for c in curl python3 tar; do command -v "$c" >/dev/null 2>&1 || err "缺少 $c"; done
fetch() { if command -v curl >/dev/null 2>&1; then curl -fsSL "$1"; else wget -qO- "$1"; fi; }

# ---------- 配置文件驱动（优先级：-c 指定 > 默认路径） ----------
[ -z "$CFG_FILE" ] && [ -f "$BOX_DIR/box-config.json" ] && CFG_FILE="$BOX_DIR/box-config.json"
if [ -n "$CFG_FILE" ]; then
  [ -f "$CFG_FILE" ] || err "配置文件不存在：$CFG_FILE"
  log "读取配置文件：$CFG_FILE"
  read -r CFG_BOX_ID CFG_CLOUD_IP CFG_TOKEN CFG_REPO CFG_BRANCH CFG_ROOTCA <<< "$(python3 - "$CFG_FILE" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])) or {}
print(c.get("boxId", "") or "", c.get("cloudIP", "") or "", c.get("token", "") or "",
      c.get("repo", "") or "", c.get("branch", "") or "", c.get("rootCA", "") or "")
PY
)" || true
  BOX_ID="${BOX_ID:-$CFG_BOX_ID}"
  CLOUD_IP="${CLOUD_IP:-$CFG_CLOUD_IP}"
  TOKEN="${TOKEN:-$CFG_TOKEN}"
  [ -n "$CFG_REPO" ]   && REPO="$CFG_REPO"
  [ -n "$CFG_BRANCH" ] && BRANCH="$CFG_BRANCH"
  [ -n "$CFG_ROOTCA" ] && CFG_ROOTCA_B64="$CFG_ROOTCA"
fi

# ---------- 必填校验 ----------
BOX_ID="${BOX_ID:-$(hostname)}"
[ -n "$CLOUD_IP" ] || err "缺少云端 IP：请用 -i 指定，或在 box-config.json 填 cloudIP 字段"
[ -n "$TOKEN" ] || err "缺少共享接入 token：公开仓库不存放 token，请用 -t 指定，或在 box-config.json 填 token（平台「盒子接入 → 导出 box-config.json」可自动填入）"
case "$TOKEN" in
  *.*.*.*) ;;  # 四段式 caHash.header.payload.signature
  *) warn "token 格式异常（应为四段式 xx.yy.zz.ww），keadm join 可能失败" ;;
esac

# ---------- ① 拉取公开源码仓库（tarball 含 box-deploy / edgecore 模板） ----------
TARBALL_URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
SRC_ROOT="/tmp/carbon-src"
rm -rf "$SRC_ROOT" && mkdir -p "$SRC_ROOT"
log "拉取公开源码仓库：$REPO（分支 $BRANCH，含 box-deploy 部署包约 13MB，请稍候）..."
fetch "$TARBALL_URL" > /tmp/carbon-src.tar.gz
tar -xzf /tmp/carbon-src.tar.gz -C "$SRC_ROOT"
rm -f /tmp/carbon-src.tar.gz
SRC="$(find "$SRC_ROOT" -maxdepth 1 -mindepth 1 -type d | head -1)"
[ -n "$SRC" ] && [ -d "$SRC/platform/box-deploy" ] || err "源码拉取/解压失败：缺少 platform/box-deploy"
log "源码就绪：$SRC"

# ---------- ② EdgeCore 基础接入（全新盒子 keadm join；已接入自动跳过） ----------
if systemctl is-active edgecore.service >/dev/null 2>&1; then
  log "edgecore 服务已在运行，跳过 keadm join（沿用现有接入）"
else
  command -v keadm >/dev/null 2>&1 || err "盒子未安装 keadm（EdgeCore 基础未接入）。请先安装 keadm 后重跑"
  log "执行 keadm join 接入云端 CloudCore ($CLOUD_IP:10000)..."
  keadm join --cloudcore-ipport=$CLOUD_IP:10000 --token="$TOKEN" \
    --kubeedge-version=v1.20.0 --with-edge-core \
    || warn "keadm join 失败（若盒子已接入可忽略；详见上方输出）"
fi

# ---------- ③ 配置下发（rootCA / edgecore.yaml，占位符替换，幂等覆盖） ----------
mkdir -p /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config
if [ -n "${CFG_ROOTCA_B64:-}" ]; then
  echo "$CFG_ROOTCA_B64" | base64 -d > /etc/kubeedge/ca/rootCA.crt
  log "rootCA 已写入（box-config.json 提供）"
elif [ -n "$ROOTCA_FILE" ]; then
  [ -f "$ROOTCA_FILE" ] || err "rootCA 文件不存在：$ROOTCA_FILE"
  cp -f "$ROOTCA_FILE" /etc/kubeedge/ca/rootCA.crt
  log "rootCA 已写入（--ca 指定）"
else
  log "未提供 rootCA：keadm join 已自动从云端拉取（如需覆盖可放 /etc/kubeedge/ca/rootCA.crt 后重启 edgecore）"
fi
cp -f "$SRC/backend/config/edgecore.template.yaml" /etc/kubeedge/config/edgecore.yaml
[ -s /etc/kubeedge/config/edgecore.yaml ] || err "edgecore.yaml 模板缺失"
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

# ---------- ④ 部署 box-deploy 采集部署包（源码拷贝，无需平台打包） ----------
mkdir -p "$DEST_DIR"
cp -rf "$SRC/platform/box-deploy/." "$DEST_DIR/"
chmod +x "$DEST_DIR/deploy_box.sh"
log "运行 box-deploy 部署脚本..."
cd "$DEST_DIR" && ./deploy_box.sh

# ---------- ⑤ 按现场写入 mqtt.boxId / broker（幂等，改完重启 box-mapper 生效） ----------
if [ -f "$BOX_DIR/config.json" ]; then
  python3 - "$BOX_DIR/config.json" "$BOX_ID" "$CLOUD_IP" <<'PY'
import json, sys
path, box_id, cloud_ip = sys.argv[1], sys.argv[2], sys.argv[3]
c = json.load(open(path))
c.setdefault("mqtt", {})["boxId"] = box_id
broker = c["mqtt"].setdefault("broker", {})
broker["host"] = cloud_ip
json.dump(c, open(path, "w"), ensure_ascii=False, indent=2)
PY
  systemctl restart box-mapper 2>/dev/null || warn "box-mapper 重启失败（可手动 systemctl restart box-mapper）"
  log "config.json 已写入 mqtt.boxId=$BOX_ID，broker.host=$CLOUD_IP"
fi

# ---------- ⑥ 自检 ----------
log "接入流程完成，自检："
log "  edgecore ：$(systemctl is-active edgecore.service 2>/dev/null || echo 未知)"
log "  box-mapper：$(systemctl is-active box-mapper 2>/dev/null || echo 未知)"
log "  提示：云端 K8s 需确认节点已注册（kubectl get nodes）后，在平台「设备管理」下发 Device CRD；"
log "  改设备配置：vim $BOX_DIR/config.json && systemctl restart box-mapper"
