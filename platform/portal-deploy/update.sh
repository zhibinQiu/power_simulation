#!/usr/bin/env bash
# ============================================================================
# 能碳平台门户 · 官网内容更新脚本（platform/portal-deploy/update.sh，开发机执行）
#
# 职责：把门户站点源码（本目录）同步发布到线上官网
#       https://www.nengyousuan.com（root@43.161.194.75:/var/www/nengyousuan，
#       Nginx 静态托管）。门户日常改版/内容更新走本脚本；
#       门户在全新服务器上的独立安装（systemd 常驻）用同目录 deploy.sh。
#
# 用法（仓库根任一路径执行均可，脚本自动定位门户目录）：
#   bash platform/update.sh portal                     # 官网更新（推荐统一入口）
#   bash platform/portal-deploy/update.sh              # 直接调用
#   bash platform/portal-deploy/update.sh -s root@192.168.1.50 -d /var/www/site
#   QZB_SSH_PASS='<密码>' bash platform/portal-deploy/update.sh        # 无免密时用密码
#
# 选项：
#   -s, --server <user@host>  目标服务器（默认 root@43.161.194.75）
#   -d, --dir <path>          目标站点目录（默认 /var/www/nengyousuan）
#   -h, --help                帮助
#
# 服务器免密说明：默认 BatchMode=yes 走 SSH 密钥；未配置密钥时用
#   export QZB_SSH_PASS='<密码>' 方式（依赖 sshpass）。
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$(cd "$SELF_DIR/.." && pwd)/servers.conf"   # 服务器地址集中配置（platform/servers.conf）
[ -f "$CONF" ] && . "$CONF" || true
SERVER="${HOME_SERVER:-${WEB_SSH:-root@43.161.194.75}}"      # 官网服务器（servers.conf WEB_SSH）
REMOTE_DIR="${HOME_DIR:-${WEB_DIR:-/var/www/nengyousuan}}"   # 官网静态目录（servers.conf WEB_DIR）

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -s|--server) SERVER="${2:-}"; shift 2 ;;
    -d|--dir)    REMOTE_DIR="${2:-}"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
[ -n "$SERVER" ] || { echo "[error] 目标服务器不能为空" >&2; exit 1; }

cd "$SELF_DIR"
[ -f index.html ] || { echo "[error] 未找到 index.html（应在 platform/portal-deploy/ 下）" >&2; exit 1; }

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
[ -z "${QZB_SSH_PASS:-}" ] || SSH_OPTS="$SSH_OPTS -o BatchMode=no"
ssh_run() { # 免密优先；QZB_SSH_PASS 时经 sshpass 传密码
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    sshpass -p "$QZB_SSH_PASS" ssh $SSH_OPTS "$@"
  else
    ssh $SSH_OPTS -o BatchMode=yes "$@"
  fi
}
rsync_run() { # 与 ssh_run 配套的 rsync 传输
  local rsh
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    rsh="sshpass -p '$QZB_SSH_PASS' ssh $SSH_OPTS"
  else
    rsh="ssh $SSH_OPTS -o BatchMode=yes"
  fi
  rsync -az -e "$rsh" "$@"
}

echo "==> 门户官网内容更新: $SELF_DIR/ → $SERVER:$REMOTE_DIR"
# 排除脚本/本地服务文件；--delete 同步清理远端多余文件
rsync_run --delete \
  --exclude='*.sh' --exclude='.DS_Store' --exclude='.serve.pid' \
  --exclude='.serve.log' --exclude='.png-backup' --exclude='*.log' \
  ./ "$SERVER:$REMOTE_DIR/"

# 同步后自检（可访问性由 Nginx 侧负责，仅确认落盘）
if ssh_run "$SERVER" "test -f '$REMOTE_DIR/index.html'"; then
  echo "✔ 官网已更新: https://www.nengyousuan.com"
else
  echo "[error] 同步后未在 $SERVER:$REMOTE_DIR 找到 index.html" >&2
  exit 1
fi
