#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 代码更新脚本（platform/bs-deploy/update.sh）
#
# 用途（开发机执行，日常更新唯一通道）：
#   本地构建前端/文档站产物 → rsync 源码到服务器 → 容器按需重建/热生效 → 健康检查
#
# 用法：bash platform/bs-deploy/update.sh [--server root@<主机>] [--skip-build]
#       （或统一入口：bash platform/update.sh bs，二者等价）
#       bash platform/bs-deploy/update.sh push ["提交信息" [--tag v1.0.0]]  # 推送代码到 GitHub（调仓库根 ./push.sh）
#   默认目标：71（root@36.151.146.71:/root/qzb/jianpai，Docker 源码卷挂载 + uvicorn --reload）
#   说明：同步本地工作区（含未提交改动），改完即可上线；代码入库推送走本脚本 push 子命令，
#         （协作者 / 其他场景统一用仓库根 ./push.sh）。
#
#   注意：代码更新一律由开发机向服务器推送（rsync），服务器不自拉 git；
#   全新部署 / 重装请走 platform/bs-deploy/deploy.sh（服务器侧 git clone）。
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# ---- push 子命令：把本地改动提交并推送到 GitHub（调用仓库根 push.sh，与协作者同源） ----
if [ "${1:-}" = "push" ]; then
  shift
  exec bash "$ROOT/push.sh" "$@"
fi

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
    *) echo "[error] 未知参数：${1}（-h 查看头部注释）" >&2; exit 1 ;;
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
echo "    代码入库推送：bash platform/bs-deploy/update.sh push \"提交信息\"（协作者通用：仓库根 ./push.sh）"
exit 0
