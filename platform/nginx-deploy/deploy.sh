#!/usr/bin/env bash
# ============================================================================
# 官网域名反代网关（nginx）· 配置下发脚本（platform/nginx-deploy/deploy.sh）
#
# 管理对象：线上官网 https://www.nengyousuan.com 的 nginx 站点配置
#           /etc/nginx/conf.d/nengyousuan.conf（权威源 = 同目录 nengyousuan.conf）
#   · 门户静态站托管   /var/www/nengyousuan（内容由 portal-deploy/update.sh 同步）
#   · 平台反代 /sim/   → {BACKEND}（剥离 /sim 前缀，后端按根路径直出 frontend）
#   · 平台反代 /api/   → {BACKEND}（保留前缀 + WebSocket upgrade）
#   · 文档站反代 /docs/→ {BACKEND}（后端再反代 docs-site 容器）
#   · HTTPS：Certbot 托管证书 + 80→443 跳转
#
# 用法（本机执行，需能免密 SSH 到官网服务器；无免密时 export QZB_SSH_PASS=<密码>）：
#   ./deploy.sh                                  # 下发配置到默认官网服务器并 reload
#   ./deploy.sh -s root@<主机>                   # 指定服务器
#   ./deploy.sh -b 36.151.146.71:40014           # 指定平台后端地址（默认同上）
#   ./deploy.sh status                           # 查看 nginx 状态与线上可达性
#   ./deploy.sh -h                               # 帮助
#
# 流程：本地 sed 替换后端地址 → scp 上传为 .tmp → 远端备份旧配置 →
#       mv 生效 → nginx -t 校验（失败自动回滚）→ systemctl reload nginx
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$(cd "$SELF_DIR/.." && pwd)/servers.conf"   # 服务器地址集中配置（platform/servers.conf）
[ -f "$CONF" ] && . "$CONF" || true
SERVER="${NGINX_SERVER:-${WEB_SSH:-root@43.161.194.75}}"        # 官网 nginx 服务器（servers.conf WEB_SSH）
BACKEND="${NGINX_BACKEND:-${WEB_BACKEND:-36.151.146.71:40014}}" # 平台后端地址（servers.conf WEB_BACKEND）
CONF_NAME="nengyousuan.conf"
REMOTE_CONF="/etc/nginx/conf.d/$CONF_NAME"

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -s|--server) SERVER="${2:-}"; shift 2 ;;
    -b|--backend) BACKEND="${2:-}"; shift 2 ;;
    -h|--help)   usage ;;
    status)      CMD="$1"; shift ;;
    *) echo "[error] 未知参数：${1}（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
[ -n "$SERVER" ] || { echo "[error] 服务器不能为空" >&2; exit 1; }
[ -n "$BACKEND" ] || { echo "[error] 后端地址不能为空（如 36.151.146.71:40014）" >&2; exit 1; }

# ---------- SSH / scp 封装（免密优先；QZB_SSH_PASS 时经 sshpass 传密码） ----------
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
[ -z "${QZB_SSH_PASS:-}" ] || SSH_OPTS="$SSH_OPTS -o BatchMode=no"
ssh_run() {
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    sshpass -p "$QZB_SSH_PASS" ssh $SSH_OPTS "$@"
  else
    ssh $SSH_OPTS -o BatchMode=yes "$@"
  fi
}
scp_up() {
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    sshpass -p "$QZB_SSH_PASS" scp $SSH_OPTS "$@"
  else
    scp $SSH_OPTS -o BatchMode=yes "$@"
  fi
}

log() { echo -e "\033[32m[nginx]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ---------- 前置校验 ----------
[ -f "$SELF_DIR/$CONF_NAME" ] || err "未找到 $SELF_DIR/$CONF_NAME"
ssh_run "$SERVER" true 2>/dev/null || err "无法 SSH 到 ${SERVER}（请配置免密或 export QZB_SSH_PASS=密码）"

deploy() {
  # ---------- ① 生成下发文件：替换后端地址 ----------
  # 注：TMP_CONF/TMP_REMOTE 用全局变量而非 local——
  #     macOS bash 3.2 EXIT trap 在函数作用域结束后触发，local 变量已销毁会 unbound
  TMP_CONF="$(mktemp)"
  sed "s|36\.151\.146\.71:40014|$BACKEND|g" "$SELF_DIR/$CONF_NAME" > "$TMP_CONF"
  TMP_REMOTE="$REMOTE_CONF.tmp"
  trap 'rm -f "$TMP_CONF"' EXIT
  log "① 上传配置 → ${SERVER}:${TMP_REMOTE}（后端地址已替换为 ${BACKEND}）"
  scp_up "$TMP_CONF" "$SERVER:$TMP_REMOTE"

  # ---------- ② 远端：备份 + 生效 + 校验 + reload（失败回滚） ----------
  log "② 备份旧配置并校验生效"
  ssh_run "$SERVER" "
    set -e
    cd /etc/nginx/conf.d
    cp -a $CONF_NAME $CONF_NAME.bak.\$(date +%Y%m%d%H%M%S) 2>/dev/null || true
    mv -f $CONF_NAME.tmp $CONF_NAME
    if nginx -t >/tmp/nginx-test.log 2>&1; then
      systemctl reload nginx
      echo '[nginx] nginx -t 通过，已 reload ✓'
    else
      mv -f $CONF_NAME.bak.\$(ls -t $CONF_NAME.bak.* 2>/dev/null | head -1 | sed 's/.*\.bak\.//') $CONF_NAME 2>/dev/null || true
      echo '[nginx] nginx -t 失败，已回滚备份！详情：' >&2
      cat /tmp/nginx-test.log >&2
      exit 1
    fi
  "

  # ---------- ③ 自检 ----------
  sleep 1
  log "③ 线上自检"
  ssh_run "$SERVER" "curl -sk -o /dev/null -w '  https://www.nengyousuan.com/        → HTTP %{http_code}\n' --max-time 15 https://www.nengyousuan.com/ || true
    curl -sk -o /dev/null -w '  https://www.nengyousuan.com/sim/      → HTTP %{http_code}\n' --max-time 20 https://www.nengyousuan.com/sim/ || true
    curl -sk -o /dev/null -w '  https://www.nengyousuan.com/api/health → HTTP %{http_code}\n' --max-time 20 https://www.nengyousuan.com/api/health || true"
  log "配置已下发完成 ✓（备份在远端 conf.d/ 下 .bak.<时间戳>）"
}

status() {
  ssh_run "$SERVER" "
    echo '--- nginx 服务状态 ---'
    systemctl is-active nginx | sed 's/^/nginx: /'
    systemctl is-enabled nginx 2>/dev/null | sed 's/^/开机自启: /'
    echo '--- 配置校验 ---'
    nginx -t 2>&1 | tail -2
    echo '--- 当前 conf.d 配置 ---'
    ls -t /etc/nginx/conf.d/*.conf 2>/dev/null | sed 's|/etc/nginx/conf.d/||'
    echo '--- 线上可达性（服务器本机 curl）---'
    curl -sk -o /dev/null -w '  https://www.nengyousuan.com/        → HTTP %{http_code}\n' --max-time 15 https://www.nengyousuan.com/ || true
    curl -sk -o /dev/null -w '  https://www.nengyousuan.com/sim/      → HTTP %{http_code}\n' --max-time 20 https://www.nengyousuan.com/sim/ || true
    curl -sk -o /dev/null -w '  https://www.nengyousuan.com/api/health → HTTP %{http_code}\n' --max-time 20 https://www.nengyousuan.com/api/health || true
  " || err "status 查询失败"
}

case "${CMD:-deploy}" in
  deploy) deploy ;;
  status) status ;;
  *) usage ;;
esac
