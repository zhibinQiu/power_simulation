#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 代码更新脚本（platform/bs-deploy/update.sh）
#
# 两种用法（同一脚本，按运行位置自动区分）：
#
#   ① 开发机执行（默认，日常主力）：
#       本地构建前端/文档站产物 → rsync 源码到服务器 → 容器按需重建/热生效 → 健康检查
#       用法：bash platform/bs-deploy/update.sh [--server root@<主机>] [--skip-build]
#       默认目标：71（root@36.151.146.71:/root/qzb/jianpai，Docker 源码卷挂载 + uvicorn --reload）
#       说明：同步本地工作区（含未提交改动），改完即可上线；代码入库推送请用 push.sh。
#
#   ② 已部署服务器 root 执行（从 GitHub 拉取团队推送的版本）：
#       用法：curl -fsSL <…/platform/bs-deploy/update.sh> | bash -s -- server [-d 目录] [-b 分支]
#       流程：备份现场数据 → git 拉取最新 → 恢复备份 → 重建容器 → 自检（数据安全优先）
# ============================================================================
set -euo pipefail

# ---- 模式判定：显式 server 参数，或非源码仓库/无 node（如 curl | bash）→ 服务器模式 ----
MODE="dev"
for a in "$@"; do
  case "$a" in
    server|-d|--dir|-b|--branch) MODE="server"; break ;;
  esac
done
if [ "$MODE" = "dev" ]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd || true)"
  if [ -z "$ROOT" ] || [ ! -f "$ROOT/frontend/package.json" ] || ! command -v node >/dev/null 2>&1; then
    MODE="server"
  fi
fi

# ============================================================================
# ① 开发机模式
# ============================================================================
if [ "$MODE" = "dev" ]; then
  cd "$ROOT"
  CONF="$ROOT/platform/servers.conf"    # 服务器地址集中配置（platform/servers.conf）
  [ -f "$CONF" ] && . "$CONF" || true
  CLOUD_MAIN="${CLOUD_MAIN:-${PLATFORM_SSH:-root@36.151.146.71}}"   # 默认目标（现 71）
  SERVER="$CLOUD_MAIN"
  SERVER_DIR="${PLATFORM_DIR:-/root/qzb/jianpai}"                   # 服务器仓库根
  BS_DIR="$SERVER_DIR/platform/bs-deploy"
  IMAGE_NAME="ghcr.io/zhibinqiu/power_simulation:latest"

  SSH_OPTS="-o StrictHostKeyChecking=no"
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

  # ---- 解析参数 ----
  RUN_BUILD=1
  while [ $# -gt 0 ]; do
    case "$1" in
      --skip-build) RUN_BUILD=0 ;;
      --server|--target) SERVER="${2:-$CLOUD_MAIN}"; shift 2 ;;
      *) echo "[error] 未知参数：$1（-h 查看头部注释）" >&2; exit 1 ;;
    esac
  done

  command -v rsync >/dev/null 2>&1 || { echo "❌ 缺少 rsync" >&2; exit 1; }
  echo "==> 仓库根：$ROOT"
  echo "==> 同步目标：$SERVER:$SERVER_DIR"

  # ---- [1/3] 本地构建前端/文档站产物（dist 已入库，随 rsync 同步；失败不阻断） ----
  if [ "$RUN_BUILD" = "1" ]; then
    echo "==> [1/3] 本地构建前端与文档站产物..."
    (cd frontend && npx vite build >/dev/null 2>&1) && echo "    frontend/dist 已构建" \
      || echo "    ⚠ frontend 构建失败/跳过（检查 node_modules）"
    (cd platform/doc-deploy/docs-site && npx vite build >/dev/null 2>&1) && echo "    docs-site/dist 已构建" \
      || echo "    ⚠ docs-site 构建失败/跳过"
  else
    echo "==> [1/3] 跳过本地构建（--skip-build）"
  fi

  # ---- [2/3] rsync 源码到服务器（排除运行时数据/本机环境） ----
  EXCLUDES="--exclude=.git --exclude=.venv --exclude=venv --exclude=node_modules --exclude=__pycache__
    --exclude=*.pyc --exclude=.DS_Store --exclude=.env --exclude=*.log
    --exclude=platform/doc-deploy/docs-site/node_modules
    --exclude=outputs --exclude=generated-images --exclude=.playwright-cli --exclude=chrome_*
    --exclude=backend/data --exclude=backend/knowledge"
  echo "==> [2/3] rsync 源码 + 配置 + 前端产物到服务器..."
  rsync_run $EXCLUDES ./ "$SERVER:$SERVER_DIR/"

  # ---- [3/3] 服务器部署：构建输入变更才重建镜像，否则容器内 reload 自动生效 ----
  # 构建输入 = Dockerfile / compose / .dockerignore / requirements
  BUILD_SENSITIVE=".dockerignore platform/bs-deploy/Dockerfile platform/bs-deploy/Dockerfile.docs platform/bs-deploy/docker-compose.yml backend/config/requirements.txt"
  need_build() {
    local lh rh f
    ssh_run "$SERVER" "docker image inspect '$IMAGE_NAME' >/dev/null 2>&1" 2>/dev/null \
      || { echo "    服务器无运行镜像 → 首次构建"; return 0; }
    for f in $BUILD_SENSITIVE; do
      rh=$(ssh_run "$SERVER" "cd '$SERVER_DIR' && md5sum '$f' 2>/dev/null | cut -d' ' -f1" 2>/dev/null || true)
      [ -n "$rh" ] || { echo "    服务器缺少 $f → 需重建镜像"; return 0; }
      if command -v md5sum >/dev/null 2>&1; then lh=$(md5sum "$f" 2>/dev/null | cut -d' ' -f1); else lh=$(md5 -q "$f" 2>/dev/null || true); fi
      [ -n "$lh" ] && [ "$lh" != "$rh" ] && { echo "    ↪ $f 已变更 → 重建镜像"; return 0; }
    done
    return 1
  }

  if need_build; then
    echo "==> [3/3] 重建运行环境镜像并拉起（依赖层缓存命中，通常 1 分钟内）..."
    ssh_run "$SERVER" "cd $BS_DIR && docker compose up -d --build" \
      || echo "⚠ 服务器重建失败（代码已同步，可稍后手动：cd $BS_DIR && docker compose up -d --build）" >&2
  else
    echo "==> [3/3] 构建输入无变更 → 不重建镜像；容器内 uvicorn --reload 已自动加载新代码"
    ssh_run "$SERVER" "cd $BS_DIR && docker compose up -d" \
      || echo "⚠ 服务器拉起失败，请查看日志" >&2
  fi
  echo "    健康检查："
  ssh_run "$SERVER" 'for i in $(seq 1 12); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:40014/api/health && break; sleep 5; done; curl -m 5 -s http://127.0.0.1:40014/api/health' \
    || echo "    ⚠ 健康检查未通过，请查看：docker compose logs" || true

  echo "==> 完成。平台访问：http://${SERVER##*@}:${PLATFORM_PORT:-40014}  （日志：docker logs -f steel-carbon-twin）"
  echo "    代码入库推送：bash platform/bs-deploy/push.sh"
  exit 0
fi

# ============================================================================
# ② 服务器模式：备份现场 → git 拉取 → 恢复 → 重建（数据安全优先）
# ============================================================================
log() { echo -e "\033[32m[update]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
能碳平台 · 服务器更新脚本（Docker 版 · 数据安全优先）

用法（root）：
  curl -fsSL https://raw.githubusercontent.com/zhibinQiu/power_simulation/master/platform/bs-deploy/update.sh | bash -s -- server [-d 目录] [-b 分支]

选项：
  -d, --dir <path>   安装目录（默认 /opt/carbon-platform；当前目录已是部署仓库则就地更新）
  -b, --branch <str> 分支（默认 master）
  -h, --help         帮助
USAGE
  exit 0
}

DEFAULT_DIR="/opt/carbon-platform"
DEFAULT_BRANCH="master"
INSTALL_DIR=""
BRANCH="$DEFAULT_BRANCH"
[ "${1:-}" = "server" ] && shift
while [ $# -gt 0 ]; do
  case "$1" in
    -d|--dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    -b|--branch) BRANCH="${2:-}"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
if [ -z "$INSTALL_DIR" ]; then
  if [ -d "$(pwd)/.git" ] && [ -f "$(pwd)/platform/bs-deploy/docker-compose.yml" ]; then
    INSTALL_DIR="$(pwd)"
    log "当前目录已是部署仓库 → 就地更新：$INSTALL_DIR"
  else
    INSTALL_DIR="$DEFAULT_DIR"
  fi
fi

[ "$(id -u)" -eq 0 ] || err "请以 root 运行（或 sudo bash $0）"
[ -d "$INSTALL_DIR/.git" ] || err "目录不是 git 仓库：$INSTALL_DIR（请先执行 platform/bs-deploy/deploy.sh 部署）"
cd "$INSTALL_DIR"
command -v git >/dev/null 2>&1 || err "缺少 git"
command -v docker >/dev/null 2>&1 || err "缺少 docker（请先执行 platform/bs-deploy/deploy.sh 完成部署）"

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

# ---------- ③ 恢复现场配置与数据 ----------
log "③ 恢复现场配置与数据..."
for d in backend/data backend/config backend/knowledge; do
  [ -d "$BACKUP_DIR/$(basename "$d")" ] && cp -a "$BACKUP_DIR/$(basename "$d")/." "$d/" 2>/dev/null || true
done
[ -f "$INSTALL_DIR/platform/bs-deploy/.env" ] || cp "$INSTALL_DIR/platform/bs-deploy/.env.example" "$INSTALL_DIR/platform/bs-deploy/.env"

# ---------- ④ 重建镜像并启动 ----------
cd "$INSTALL_DIR/platform/bs-deploy"
log "④ 重建镜像 + 启动容器（依赖层缓存命中，通常 1 分钟内）..."
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
