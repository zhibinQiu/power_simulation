#!/usr/bin/env bash
# ============================================================================
# 平台门户网站 · 独立部署脚本（nengtan-portal）
#
# 面向公众的平台门户静态站点（platform/portal-deploy），独立安装到服务器
# /opt/nengtan-portal/，注册 systemd 常驻服务 nengtan-portal.service
# （开机自启 + 崩溃自动重启）。
# 注：官网（https://www.nengyousuan.com）日常内容更新用同目录 update.sh。
#
# 用法（本机开发机执行，需能免密 SSH 到服务器）：
#   ./deploy.sh                                        # 部署到默认服务器
#   ./deploy.sh -s root@192.168.1.100                  # 指定服务器
#   ./deploy.sh -p 40200                               # 指定端口（默认 40200）
#   ./deploy.sh status                                 # 查看运行状态
#   ./deploy.sh uninstall                              # 卸载服务（保留站点文件）
#
# 选项：
#   -s, --server <user@host>  目标服务器（默认 root@36.151.146.71，可改）
#   -p, --port <port>         对外端口（默认 40200，遵循 40000+ 端口规范）
#   -h, --help                帮助
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SELF_DIR"
CONF="$(cd "$SELF_DIR/.." && pwd)/servers.conf"   # 服务器地址集中配置（platform/servers.conf）
[ -f "$CONF" ] && . "$CONF" || true

SERVER="${SERVER:-${PORTAL_SSH:-root@36.151.146.71}}"   # 门户独立站点服务器（servers.conf PORTAL_SSH）
PORT="${PORT:-${PORTAL_PORT:-40200}}"                    # 门户端口（servers.conf PORTAL_PORT）
APP_DIR="/opt/nengtan-portal"
SERVICE="nengtan-portal.service"

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$SELF_DIR/$(basename "${BASH_SOURCE[0]}")"
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -s|--server) SERVER="${2:-}"; shift 2 ;;
    -p|--port)   PORT="${2:-}";   shift 2 ;;
    -h|--help)   usage ;;
    status|uninstall) CMD="$1"; shift ;;
    *) echo "[error] 未知参数：${1}（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
[ -n "$SERVER" ] || { echo "[error] 服务器不能为空" >&2; exit 1; }
SSH=(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$SERVER")

log() { echo -e "\033[32m[portal]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ---------- 前置校验 ----------
[ -f index.html ] || err "未找到 index.html，请在 platform/portal-deploy/ 下运行本脚本"
command -v rsync >/dev/null 2>&1 || err "缺少 rsync"
"${SSH[@]}" true 2>/dev/null || err "无法 SSH 到 ${SERVER}（请先配置免密登录）"

case "${CMD:-deploy}" in

  deploy)
    # ---------- ① 推送静态站点（排除运行时文件与 png 备份） ----------
    log "① 推送站点 → $SERVER:$APP_DIR"
    rsync -az --delete \
      -e "ssh -o StrictHostKeyChecking=no" \
      --exclude='*.sh' --exclude='.DS_Store' --exclude='.serve.pid' --exclude='.serve.log' \
      --exclude='.png-backup' --exclude='*.log' \
      ./ "$SERVER:$APP_DIR/"

    # ---------- ② 写入 systemd 单元 ----------
    log "② 注册 systemd 常驻服务 ${SERVICE}（端口 ${PORT}）"
    "${SSH[@]}" "cat > /etc/systemd/system/$SERVICE" <<EOF
[Unit]
Description=NengTan Portal (平台门户网站)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 -m http.server $PORT --bind 0.0.0.0 --directory $APP_DIR
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    # ---------- ③ 防火墙放行（firewalld 未放行则自动放行，避免端口被拦） ----------
    log "③ 检查防火墙放行 ${PORT}/tcp"
    "${SSH[@]}" "if systemctl is-active --quiet firewalld; then
        if ! firewall-cmd --list-ports 2>/dev/null | grep -qw '$PORT/tcp'; then
          firewall-cmd --permanent --add-port=$PORT/tcp && firewall-cmd --reload
          echo '[portal] 已放行 '$PORT'/tcp'
        else
          echo '[portal] '$PORT'/tcp 已放行'
        fi
      else
        echo '[portal] firewalld 未运行，跳过'
      fi"

    # ---------- ④ 启用并启动 ----------
    "${SSH[@]}" "systemctl daemon-reload && systemctl enable --now $SERVICE"

    # ---------- ⑤ 自检 ----------
    sleep 2
    if "${SSH[@]}" "systemctl is-active --quiet $SERVICE"; then
      IP=$("${SSH[@]}" "hostname -I 2>/dev/null | awk '{print \$1}'")
      log "部署完成 ✓ 门户已常驻运行"
      log "  访问地址：http://${IP:-<服务器IP>}:$PORT"
      log "  服务管理：systemctl status $SERVICE"
      log "  日志查看：journalctl -u $SERVICE -f"
    else
      err "服务启动失败，请查看：journalctl -u $SERVICE -n 50"
    fi
    ;;

  status)
    "${SSH[@]}" "systemctl status $SERVICE --no-pager | head -12; echo '---'; \
      systemctl is-enabled $SERVICE 2>/dev/null | sed 's/^/开机自启: /'; \
      curl -s -o /dev/null -w 'HTTP 自检: %{http_code}\n' http://127.0.0.1:$PORT/ || true"
    ;;

  uninstall)
    log "卸载服务 ${SERVICE}（保留 ${APP_DIR} 站点文件）"
    "${SSH[@]}" "systemctl disable --now $SERVICE 2>/dev/null || true; rm -f /etc/systemd/system/$SERVICE; systemctl daemon-reload"
    log "已卸载"
    ;;

  *) usage ;;
esac
