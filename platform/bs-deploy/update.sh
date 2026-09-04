#!/usr/bin/env bash
# ============================================================================
# 能碳智控平台 · 服务器更新脚本（Docker 版 · 数据安全优先）
#
# 在已部署实例（docker compose 部署）上安全更新：
#   ① 备份现场数据（backend/data、backend/config、backend/knowledge）
#   → ② git pull 拉取最新源码 → ③ 恢复备份 → ④ 重新构建镜像（有层缓存）
#   → ⑤ 滚动重启容器 → ⑥ 自检
#
# 全程无需 python/node/npm/venv；旧 systemd/venv 部署的服务器请改用本脚本，
# 或先执行 platform/bs-deploy/server.sh 完成 Docker 迁移。
#
# 用法（root）：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/platform/bs-deploy/update.sh | bash -s -- -d /opt/carbon-platform
# 选项：
#   -d, --dir <path>   安装目录（默认 /opt/carbon-platform）
#   -b, --branch <str> 分支（默认 master）
#   -h, --help         帮助
# ============================================================================
set -euo pipefail

DEFAULT_DIR="/opt/carbon-platform"
DEFAULT_BRANCH="master"
INSTALL_DIR="$DEFAULT_DIR"
BRANCH="$DEFAULT_BRANCH"

usage() {
  cat <<'USAGE'
能碳智控平台 · 服务器更新脚本（Docker 版）

用法（root）：
  curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/platform/bs-deploy/update.sh | bash -s -- -d /opt/carbon-platform

选项：
  -d, --dir <path>   安装目录（默认 /opt/carbon-platform）
  -b, --branch <str> 分支（默认 master）
  -h, --help         帮助
USAGE
  exit 0
}
while [ $# -gt 0 ]; do
  case "$1" in
    -d|--dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    -b|--branch) BRANCH="${2:-}";      shift 2 ;;
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done

log() { echo -e "\033[32m[update]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || err "请以 root 运行（或 sudo bash $0）"
[ -d "$INSTALL_DIR/.git" ] || err "目录不是 git 仓库：$INSTALL_DIR（请先执行 platform/bs-deploy/server.sh 部署）"
cd "$INSTALL_DIR"
command -v git >/dev/null 2>&1 || err "缺少 git"
command -v docker >/dev/null 2>&1 || err "缺少 docker（请先执行 platform/bs-deploy/server.sh 完成部署）"

BACKUP_DIR="$INSTALL_DIR/.update-backup-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP_DIR"

# ---------- ① 备份现场配置与运行时数据 ----------
log "① 备份现场数据 → $BACKUP_DIR"
for d in backend/data backend/config backend/knowledge; do
  [ -d "$d" ] && cp -a "$d" "$BACKUP_DIR/" 2>/dev/null || true
done

# ---------- ② 拉取最新源码 ----------
log "② 拉取最新源码（分支 $BRANCH）..."
git fetch --depth 1 origin "$BRANCH" || err "git fetch 失败（检查网络/分支名）"
git reset --hard "origin/$BRANCH"

# ---------- ③ 恢复现场配置与数据（仓库跟踪了 config/data，防覆盖丢失） ----------
log "③ 恢复现场配置与数据..."
for d in backend/data backend/config backend/knowledge; do
  [ -d "$BACKUP_DIR/$(basename "$d")" ] && cp -a "$BACKUP_DIR/$(basename "$d")/." "$d/" 2>/dev/null || true
done
[ -f "$INSTALL_DIR/platform/bs-deploy/.env" ] || cp "$INSTALL_DIR/platform/bs-deploy/.env.example" "$INSTALL_DIR/platform/bs-deploy/.env"

# ---------- ④ 重建镜像并滚动重启 ----------
cd "$INSTALL_DIR/platform/bs-deploy"   # 部署编排目录；compose 相对路径 ../.. 指向仓库根
log "④ 重建镜像 + 重启容器（依赖层缓存命中，通常 1 分钟内）..."
docker compose build || err "镜像构建失败，请查看上方日志"
docker compose up -d || err "容器启动失败，请查看上方日志"

# ---------- ⑤ 自检 ----------
sleep 3
if docker ps --format '{{.Names}}' | grep -qx "steel-carbon-twin"; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  log "更新完成 ✓ 平台已重启"
  log "  访问地址：http://${IP:-<服务器IP>}:$(docker port steel-carbon-twin 8010/tcp 2>/dev/null | sed 's/.*://')"
  log "  数据备份：$BACKUP_DIR（确认无误后可删）"
  log "  日志查看：docker logs -f steel-carbon-twin"
else
  err "平台启动失败，请查看：docker compose logs（现场数据备份在 $BACKUP_DIR）"
fi
