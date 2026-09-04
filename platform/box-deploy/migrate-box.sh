#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 一键迁移换云（免手工签发证书）
#
# 原理：edgecore.yaml 已配置 rotateCertificates: true + token。KubeEdge 在
# 证书缺失/过期时会用 token 向云端 CloudCore 自动申请新证书，因此「换云」
# 只需在盒子上改 3 个东西，无需在云端手工 openssl 签发 + scp：
#   ① rootCA.crt    → 换成新云的 CA
#   ② edgecore.yaml → 云地址(server/httpServer/stream) + token 换成新云
#   ③ 删除旧 server.crt/key（触发 edgecore 用 token 自动重签）
#
# 用法（盒子 root）：
#   ./migrate-box.sh -i 36.151.146.71 -t <新token> [--ca-base64 <新rootCA base64>]
#   ./migrate-box.sh --config /opt/weight-bridge/box-config.json   # 配置文件驱动
#
# 选项：
#   -i, --ip <ip>        新云端 CloudCore / MQTT Broker 地址
#   -t, --token <token>  新云端共享 token（keadm token create / tokensecret 获取）
#       --ca-base64 <b64> 新云端 rootCA.crt 的 base64（也可先手工放到
#                         /etc/kubeedge/ca/rootCA.crt 后不传本参数）
#   -c, --config <file>  配置文件（含 cloudIP/token/rootCA 字段，见 platform/box-deploy/box.sh）
#   -h, --help           帮助
# 回滚：备份在 /opt/backup_pre_migrate_<时间戳>/，恢复后 systemctl restart edgecore box-mapper
# ============================================================================
set -euo pipefail

CLOUD_IP=""
TOKEN=""
CA_B64=""
CFG_FILE=""
BOX_DIR="/opt/weight-bridge"

usage() { cat <<'USAGE'
能碳一体机 · 一键迁移换云（免手工签发证书）
用法（盒子 root）：
  ./migrate-box.sh -i 36.151.146.71 -t xx.xx.xx.xx [--ca-base64 <b64>]
  ./migrate-box.sh --config box-config.json
选项：
  -i, --ip <ip>         新云端地址
  -t, --token <token>   新云端共享 token
      --ca-base64 <b64> 新云端 rootCA base64
  -c, --config <file>   配置文件驱动
  -h, --help            帮助
USAGE
exit 0; }
while [ $# -gt 0 ]; do
  case "$1" in
    -i|--ip)        CLOUD_IP="${2:-}"; shift 2 ;;
    -t|--token)     TOKEN="${2:-}";    shift 2 ;;
    --ca-base64)    CA_B64="${2:-}";   shift 2 ;;
    -c|--config)    CFG_FILE="${2:-}"; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "[error] 未知参数：$1" >&2; exit 1 ;;
  esac
done

log()  { echo -e "\033[32m[migrate]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] && err "请以 root 运行"
[ -f /etc/kubeedge/config/edgecore.yaml ] || err "未找到 /etc/kubeedge/config/edgecore.yaml（盒子未接入 KubeEdge？）"

# ---------- 配置文件驱动 ----------
[ -z "$CFG_FILE" ] && [ -f "$BOX_DIR/box-config.json" ] && CFG_FILE="$BOX_DIR/box-config.json"
if [ -n "$CFG_FILE" ] && [ -f "$CFG_FILE" ]; then
  read -r _IP _TOK _CA <<< "$(python3 - "$CFG_FILE" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])) or {}
print(c.get("cloudIP", "") or "", c.get("token", "") or "", c.get("rootCA", "") or "")
PY
)" || true
  CLOUD_IP="${CLOUD_IP:-$_IP}"; TOKEN="${TOKEN:-$_TOK}"; CA_B64="${CA_B64:-$_CA}"
fi
[ -n "$CLOUD_IP" ] || err "缺少新云端 IP（-i 或配置 cloudIP）"

# ---------- 备份（含 CA/证书/edgecore.yaml/config.json） ----------
TS=$(date +%Y%m%d%H%M%S)
BK="/opt/backup_pre_migrate_$TS"
mkdir -p "$BK"
for p in /etc/kubeedge/ca /etc/kubeedge/certs /etc/kubeedge/config "$BOX_DIR/config.json"; do
  [ -e "$p" ] && cp -a "$p" "$BK/"
done
log "现场已备份 → ${BK}（回滚：恢复该目录后重启 edgecore/box-mapper）"

# ---------- ① 新 rootCA ----------
if [ -n "$CA_B64" ]; then
  mkdir -p /etc/kubeedge/ca
  echo "$CA_B64" | base64 -d > /etc/kubeedge/ca/rootCA.crt || err "rootCA base64 解码失败"
  log "① rootCA.crt 已更新（base64）"
elif [ -s /etc/kubeedge/ca/rootCA.crt ]; then
  log "① rootCA.crt 保留现状：/etc/kubeedge/ca/rootCA.crt"
  warn "  若换到全新云，请先放置新云 rootCA.crt（可用 --ca-base64 传入）"
else
  err "缺少 rootCA.crt（用 --ca-base64 传入新云 CA）"
fi

# ---------- ② edgecore.yaml：云地址 + token 替换 ----------
ECY=/etc/kubeedge/config/edgecore.yaml
[ -n "$TOKEN" ] || warn "未提供 token：edgecore 将无法用 token 自动申请证书，需要证书已预置"
python3 - "$ECY" "$CLOUD_IP" "$TOKEN" <<'PY'
import sys, re
path, ip, token = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path).read().splitlines()
# 仅替换「云端地址行」中的 IP（httpServer / websocket.server / quic.server /
# edgeStream.server），其他行（clusterDNS 10.43.0.10、token、路径等）一律不动
out = []
for ln in lines:
    stripped = ln.strip()
    has_ip = bool(re.search(r'\d{1,3}(\.\d{1,3}){3}', ln))
    if stripped.startswith("httpServer:") and "://" in ln and has_ip:
        ln = re.sub(r'\d{1,3}(\.\d{1,3}){3}', ip, ln)          # https://IP:10002
    elif stripped.startswith("server:") and has_ip:
        ln = re.sub(r'\d{1,3}(\.\d{1,3}){3}', ip, ln)          # IP:10004 / IP:10003 / IP:10001
    elif "{{CLOUDIP}}" in ln:
        ln = ln.replace("{{CLOUDIP}}", ip)
    elif stripped.startswith("token:") and token:
        ln = re.sub(r'token:\s*\S+', f'token: {token}', ln)
    out.append(ln)
open(path, "w").write("\n".join(out) + "\n")
PY
log "② edgecore.yaml 已更新：云端地址=$CLOUD_IP"$( [ -n "$TOKEN" ] && echo "，token 已替换" )

# ---------- ③ 删除旧证书，触发 edgecore token 自动重签 ----------
rm -f /etc/kubeedge/certs/server.crt /etc/kubeedge/certs/server.key
log "③ 旧证书已删除（edgecore 将用 token 自动向新云申请证书）"
log "    若新云未开启 token 签发，请手工把 server.crt/key 放到 /etc/kubeedge/certs/"

# ---------- ④ 重启 edgecore ----------
systemctl restart edgecore.service 2>/dev/null || warn "edgecore 重启失败（可手动 systemctl restart edgecore.service）"
log "④ edgecore 已重启，等待接入云端（10~30s）..."

# ---------- ⑤ box-mapper broker 指向新云 ----------
if [ -f "$BOX_DIR/config.json" ]; then
  python3 - "$BOX_DIR/config.json" "$CLOUD_IP" <<'PY'
import json, sys
path, ip = sys.argv[1], sys.argv[2]
c = json.load(open(path))
broker = c["mqtt"].setdefault("broker", {})
broker["host"] = ip
json.dump(c, open(path, "w"), ensure_ascii=False, indent=2)
PY
  systemctl restart box-mapper 2>/dev/null || warn "box-mapper 重启失败"
  log "⑤ box-mapper 已重启，MQTT broker 指向 $CLOUD_IP"
fi

# ---------- ⑥ 自检 ----------
sleep 12
log "自检："
log "  edgecore ：$(systemctl is-active edgecore.service 2>/dev/null || echo 未知)"
log "  box-mapper：$(systemctl is-active box-mapper 2>/dev/null || echo 未知)"
log "  提示：云端确认 kubectl get nodes 出现本盒子、kubectl get device 的 twins 开始更新即完成。"
log "  回滚：$BK"
