#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 同步脚本（platform/bs-deploy/sync.sh，在开发机执行）
#
# 本地源码 → 新服务器（Docker 源码卷挂载 + uvicorn --reload）：
#   - 后端 .py 改动  → rsync 后容器内 --reload 秒级自动生效，无需重建/重启
#   - 前端改动       → 本地 npx vite build 后 rsync frontend/dist（静态文件即刻生效）
#   - 仅 Dockerfile / docker-compose.yml / requirements 等「构建输入」变更时
#     才需 docker compose up -d --build（脚本自动检测，依赖层缓存通常 1 分钟内）
#
# 用法（仓库根任一路径执行本脚本均可，脚本自动定位仓库根）：
#   bash platform/bs-deploy/sync.sh                 rsync→71 + 自动部署 + git 提交推送
#   bash platform/bs-deploy/sync.sh "fix: xxx"      指定 git 提交信息
#   bash platform/bs-deploy/sync.sh --no-git        只同步代码到服务器（不提交 GitHub）
#   bash platform/bs-deploy/sync.sh --skip-build    只 rsync 代码，不在服务器构建/拉起
#   bash platform/bs-deploy/sync.sh --server 45     同步到备用服务器 172.19.134.45
#   bash platform/bs-deploy/sync.sh --no-portal     跳过线上官网同步
#
# 服务器免密说明：默认 BatchMode=yes 走 SSH 密钥；未配置密钥时可用
#   export QZB_SSH_PASS='<密码>' bash platform/bs-deploy/sync.sh   （依赖 sshpass）
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SELF_DIR/../.." && pwd)"          # 仓库根（rsync 源 / git / 前端构建均在此）
cd "$ROOT"

# ---- 云端目标：主=新服务器 71，备=45 ----
CLOUD_MAIN="root@36.151.146.71"        # 新服务器（Docker Compose 源码卷挂载部署，目录即仓库根）
CLOUD_BACKUP="root@172.19.134.45"      # 备用服务器（旧部署结构，保留 rsync 兼容）
SERVER="$CLOUD_MAIN"
SERVER_DIR="/root/qzb/jianpai"          # 服务器仓库根
BS_DIR="$SERVER_DIR/platform/bs-deploy" # 服务器部署编排目录（compose 相对 ../.. 指向仓库根）
GIT_REMOTE="github"
GIT_BRANCH="master"
IMAGE_NAME="ghcr.io/zhibinqiu/power_simulation:latest"

# 线上官网（https://www.nengyousuan.com，43.161.194.75 + Nginx 静态托管）
PORTAL_SERVER="root@43.161.194.75"
PORTAL_REMOTE_DIR="/var/www/nengyousuan"

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
MSG=""
RUN_GIT=1
RUN_BUILD=1
RUN_PORTAL=1
while [ $# -gt 0 ]; do
  case "$1" in
    --no-git)      RUN_GIT=0 ;;
    --skip-build)  RUN_BUILD=0 ;;
    --no-portal)   RUN_PORTAL=0 ;;
    --server|--target)
      case "${2:-}" in 45|172.19.134.45) SERVER="$CLOUD_BACKUP";; *) SERVER="${2:-$CLOUD_MAIN}";; esac
      shift 2 ;;
    *) MSG="$1"; shift ;;
  esac
done

if [ "$RUN_GIT" = "1" ] && ! git remote | grep -qx "$GIT_REMOTE"; then
  echo "⚠ 未找到 GitHub 远端 '$GIT_REMOTE'，仅同步代码到服务器。"
  echo "  添加：git remote add $GIT_REMOTE https://github.com/zhibinQiu/power_simulation.git"
  RUN_GIT=0
fi

if ! command -v rsync >/dev/null 2>&1; then echo "❌ 缺少 rsync" >&2; exit 1; fi
echo "==> 仓库根：$ROOT"
echo "==> 同步目标：$SERVER:$SERVER_DIR （ $( [ "$SERVER" = "$CLOUD_MAIN" ] && echo 新服务器/主 || echo 备用 )）"

# ---- [0/5] 本地构建前端/文档站产物（dist 已入库，随 rsync 同步；改动即生效） ----
echo "==> [0/5] 本地构建前端产物（frontend/ docs-site/，缺失/失败不阻断同步）..."
(cd frontend && npx vite build >/dev/null 2>&1) && echo "    frontend/dist 已构建" \
  || echo "    ⚠ frontend 构建跳过/失败（检查 node_modules 与 vite）"
(cd docs-site && npx vite build >/dev/null 2>&1) && echo "    docs-site/dist 已构建" \
  || echo "    ⚠ docs-site 构建跳过/失败"

# ---- [1/5] rsync 源码（运行时数据/本机环境不上传；frontend/dist 需同步以挂载生效） ----
EXCLUDES="--exclude=.git --exclude=.venv --exclude=venv --exclude=node_modules --exclude=__pycache__
  --exclude=*.pyc --exclude=.DS_Store --exclude=.env --exclude=*.log
  --exclude=docs-site/node_modules --exclude=.playwright-cli
  --exclude=outputs --exclude=generated-images --exclude=chrome_*
  --exclude=backend/data --exclude=backend/knowledge --exclude=.pre-sync-*"
echo "==> [1/5] rsync 源码 + 配置 + 前端产物到服务器（排除运行时数据/本机环境）..."
rsync_run $EXCLUDES ./ "$SERVER:$SERVER_DIR/"

# 清理服务器上历史迁移遗留目录（deploy/ 已于 2026-09 迁入 platform/，homePage 更名 home-deploy）
ssh_run "$SERVER" "rm -rf '$SERVER_DIR/deploy' '$SERVER_DIR/platform/homePage'" 2>/dev/null || true

# ---- 是否需要重建镜像：仅「构建输入」变更 / 服务器无镜像 时才 build ----
# 比对路径统一用「仓库根相对路径」（本地与远程目录结构一致）
BUILD_SENSITIVE=".dockerignore platform/bs-deploy/Dockerfile platform/bs-deploy/Dockerfile.docs platform/bs-deploy/docker-compose.yml platform/bs-deploy/.env.example backend/config/requirements.txt"
need_build() {
  local lh rh f
  ssh_run "$SERVER" "docker image inspect '$IMAGE_NAME' >/dev/null 2>&1" 2>/dev/null \
    || { echo "    ↪ 服务器无运行镜像 → 首次构建"; return 0; }
  for f in $BUILD_SENSITIVE; do
    rh=$(ssh_run "$SERVER" "cd '$SERVER_DIR' && md5sum '$f' 2>/dev/null | cut -d' ' -f1" 2>/dev/null || true)
    [ -n "$rh" ] || { echo "    ↪ 服务器缺少 $f → 需构建"; return 0; }
    if command -v md5sum >/dev/null 2>&1; then lh=$(md5sum "$f" 2>/dev/null | cut -d' ' -f1); else lh=$(md5 -q "$f" 2>/dev/null || true); fi
    [ -n "$lh" ] && [ "$lh" != "$rh" ] && { echo "    ↪ $f 已变更 → 需重建镜像"; return 0; }
  done
  return 1
}

# ---- [2/5] 服务器部署：构建输入无变更则跳过重建，代码改动由容器内 reload 生效 ----
if [ "$RUN_BUILD" = "1" ]; then
  if need_build; then
    echo "==> [2/5] 重建运行环境镜像并拉起（层缓存命中，通常 1 分钟内）..."
    ssh_run "$SERVER" "cd $BS_DIR && docker compose up -d --build" \
      || { echo "⚠ 服务器重建失败（查看上方日志）；代码已同步，可稍后手动：cd $BS_DIR && docker compose up -d --build" >&2; }
  else
    echo "==> [2/5] 构建输入无变更 → 不重建镜像；容器内 uvicorn --reload 已自动加载新代码"
    ssh_run "$SERVER" "cd $BS_DIR && docker compose up -d" \
      || { echo "⚠ 服务器拉起失败（查看上方日志）" >&2; }
  fi
  echo "    健康检查："
  ssh_run "$SERVER" 'for i in $(seq 1 12); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:40014/api/health && break; sleep 5; done; curl -m 5 -s http://127.0.0.1:40014/api/health' \
    || echo "    ⚠ 健康检查未通过，请查看：docker compose logs" || true
else
  echo "==> [2/5] 跳过服务器构建（--skip-build）。代码已同步，服务器上执行 docker compose up -d --build 生效。"
fi

# ---- [3/5] 门户官网内容更新（platform/home-deploy → https://www.nengyousuan.com） ----
if [ "$RUN_PORTAL" = "1" ]; then
  if bash "$ROOT/platform/home-deploy/sync-home.sh"; then
    echo "    官网已更新: https://www.nengyousuan.com"
  else
    echo "    ⚠ 官网同步失败（不影响平台；检查免密/网络）" >&2
  fi
fi

# ---- [4/5] git 提交并推送（可选） ----
if [ "$RUN_GIT" = "1" ]; then
  echo "==> [4/5] git 提交并推送 GitHub"
  git add -A
  if git diff --cached --quiet; then
    echo "    无本地改动，跳过提交"
  else
    git commit -q -m "${MSG:-sync: 更新代码}" && echo "    已提交: ${MSG:-sync: 更新代码}"
  fi
  echo "    推送到 GitHub（网络不通时自动跳过，稍后可用 push.sh）..."
  if command -v timeout >/dev/null 2>&1; then GIT_T="timeout 90"; else GIT_T=""; fi
  if $GIT_T git pull --rebase "$GIT_REMOTE" "$GIT_BRANCH" 2>/dev/null && $GIT_T git push "$GIT_REMOTE" "$GIT_BRANCH" 2>/dev/null; then
    echo "    推送完成"
  else
    echo "    ⚠ 本次未能推送（GitHub 网络问题），改动已在本地提交，稍后执行 bash platform/bs-deploy/push.sh"
  fi
else
  echo "==> [4/5] 已跳过 git（--no-git）"
fi

echo "==> 全部完成。服务器访问：http://36.151.146.71:40014  （日志：docker logs -f steel-carbon-twin）"
