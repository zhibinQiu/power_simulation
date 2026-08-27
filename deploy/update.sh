#!/usr/bin/env bash
# ============================================================================
# 能碳智控平台 · 服务器更新脚本（数据安全优先）
#
# 在已部署实例上拉取最新源码并安全更新：
#   ① 备份现场配置与运行时数据 → ② 拉取更新 → ③ 恢复备份 → ④ 重建前端 → ⑤ 重启
#
# 为什么必须用它而不是 server.sh 重跑：源码仓库跟踪了 backend/config/ 下的
# box_config.json / box_devices.json / links.json / mqtt.yaml 与 backend/data/
# （碳合规、历史报告），直接 git reset --hard 会把这些现场数据覆盖丢失；
# 本脚本更新前自动备份、更新后自动恢复，全程不丢数据。
#
# 用法（root）：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/update.sh | bash -s -- -d /opt/carbon-platform
# 选项：
#   -d, --dir <path>         安装目录（默认 /opt/carbon-platform）
#   -b, --branch <branch>    分支（默认 master）
#   -p, --port <port>        对外端口（默认沿用已部署服务的 systemd 配置）
#   -h, --help               显示本帮助
#
# 盒子侧更新：重新执行 deploy/box.sh 即可（幂等：edgecore 运行中跳过 join、
# /opt/weight-bridge/config.json 现场配置保留，仅更新 box-deploy 程序）。
# ============================================================================
set -euo pipefail

DEFAULT_DIR="/opt/carbon-platform"
DEFAULT_BRANCH="master"

INSTALL_DIR="$DEFAULT_DIR"
BRANCH="$DEFAULT_BRANCH"
PORT=""

usage() {
  cat <<'USAGE'
能碳智控平台 · 服务器更新脚本（备份现场数据 → 更新 → 恢复 → 重启）

用法（root）：
  curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/update.sh | bash -s -- -d /opt/carbon-platform

选项：
  -d, --dir <path>       安装目录（默认 /opt/carbon-platform）
  -b, --branch <branch>  分支（默认 master）
  -p, --port <port>      对外端口（默认沿用已部署 systemd 配置）
  -h, --help             显示本帮助
USAGE
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -d|--dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    -b|--branch) BRANCH="${2:-}";      shift 2 ;;
    -p|--port)   PORT="${2:-}";        shift 2 ;;
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done

log() { echo -e "\033[32m[update]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || err "请以 root 运行（或 sudo bash $0）"
[ -d "$INSTALL_DIR/.git" ] || err "目录不是 git 仓库：$INSTALL_DIR（请先执行 deploy/server.sh 部署）"
cd "$INSTALL_DIR"
command -v git >/dev/null 2>&1 || err "缺少 git"

BACKUP_DIR="$INSTALL_DIR/.update-backup-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP_DIR/config" "$BACKUP_DIR/data"

# ---------- ① 备份现场配置与运行时数据 ----------
log "① 备份现场数据 → $BACKUP_DIR"
for f in box_config.json box_devices.json links.json mqtt.yaml \
         platform_config.json strategies.json .env github_config.json; do
  [ -f "backend/config/$f" ] && cp -a "backend/config/$f" "$BACKUP_DIR/config/"
done
[ -d backend/data ] && cp -a backend/data/. "$BACKUP_DIR/data/" 2>/dev/null || true

# ---------- ② 拉取最新源码（reset --hard 后恢复备份，不丢现场数据） ----------
log "② 拉取最新源码（分支 $BRANCH）..."
git fetch --depth 1 origin "$BRANCH" || { err "git fetch 失败（检查网络 / 分支名）"; }
git reset --hard "origin/$BRANCH"

# ---------- ③ 恢复现场配置与数据 ----------
log "③ 恢复现场配置与数据..."
cp -a "$BACKUP_DIR/config/." backend/config/ 2>/dev/null || true
cp -a "$BACKUP_DIR/data/."   backend/data/   2>/dev/null || true

# ---------- ④ 依赖与前端重建 ----------
log "④ 更新后端依赖 + 重建前端（可能需要几分钟）..."
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip -q
backend/.venv/bin/pip install -r backend/config/requirements.txt -q || backend/.venv/bin/pip install -r backend/config/requirements.txt
cd frontend
[ -d node_modules ] || npm install --no-audit --no-fund
npm install --no-audit --no-fund --silent || true
npx vite build || { cd "$INSTALL_DIR"; err "前端构建失败，请检查上方日志"; }

# ---------- ⑤ 重启服务（沿用 systemd 配置或 -p 指定端口） ----------
cd "$INSTALL_DIR"
if [ -n "$PORT" ]; then
  sed -i "s/--port [0-9]*/--port $PORT/" /etc/systemd/system/carbon-platform.service 2>/dev/null \
    || sed -i "s/--port [0-9]*/--port $PORT/" /etc/systemd/system/carbon-platform.service
  systemctl daemon-reload
fi
systemctl restart carbon-platform.service || true

# ---------- ⑥ 自检 ----------
sleep 2
if systemctl is-active carbon-platform.service >/dev/null 2>&1; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  log "更新完成 ✓ 平台已重启"
  log "  访问地址：http://${IP:-<服务器IP>}:$(systemctl show carbon-platform.service -p ExecStart --value | sed -n 's/.*--port \([0-9]*\).*/\1/p')"
  log "  数据备份：$BACKUP_DIR（确认无误后建议保留，无需手工清理）"
  log "  日志查看：journalctl -u carbon-platform -f"
else
  err "服务启动失败，请查看：journalctl -u carbon-platform -n 50（现场数据备份在 $BACKUP_DIR，可手动恢复）"
fi
