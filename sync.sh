#!/usr/bin/env bash
# ============================================================================
# 同步脚本 v2：本地源码 → 新服务器（Docker 部署）→ 服务器自动重建 + 健康检查
#
# 背景：云端主服务器已从 172.19.134.45（备用）迁移到 36.151.146.71（新），
#       新服务器以 Docker Compose 镜像模式运行（后端依赖/前端产物在镜像内），
#       因此「同步代码 + 让改动生效」= rsync 代码 + docker compose up -d --build
#       （镜像层缓存命中，通常 1 分钟内），无需再手动 install/重启 systemd。
#
# 用法：
#   bash sync.sh                            rsync→71 + 71 重建 + git 提交推送
#   bash sync.sh "fix: xxx"                 指定 git 提交信息
#   bash sync.sh --no-git                   只同步代码到服务器（不提交 GitHub）
#   bash sync.sh --skip-build               只 rsync 代码，不在服务器重建（下次手动 up）
#   bash sync.sh --server 45                同步到备用服务器 172.19.134.45
#   bash sync.sh --no-portal                跳过线上官网同步
#
# 服务器免密说明：默认 BatchMode=yes 走 SSH 密钥；未配置密钥时可用
#   export QZB_SSH_PASS='<密码>' bash sync.sh   （依赖 sshpass）
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---- 云端目标：主=新服务器 71，备=45 ----
CLOUD_MAIN="root@36.151.146.71"        # 新服务器（Docker Compose 部署，目录即仓库根）
CLOUD_BACKUP="root@172.19.134.45"      # 备用服务器（旧部署结构，保留 rsync 兼容）
SERVER="$CLOUD_MAIN"
SERVER_DIR="/root/qzb/jianpai"
GIT_REMOTE="github"
GIT_BRANCH="master"

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
echo "==> 同步目标：$SERVER:$SERVER_DIR （$( [ "$SERVER" = "$CLOUD_MAIN" ] && echo 新服务器/主 || echo 备用 )）"

# ---- [1/4] rsync 源码（运行时数据/构建产物/本机环境一律不上传） ----
EXCLUDES="--exclude=.git --exclude=.venv --exclude=venv --exclude=node_modules --exclude=__pycache__
  --exclude=*.pyc --exclude=.DS_Store --exclude=.env --exclude=*.log
  --exclude=frontend/dist --exclude=docs-site/node_modules --exclude=.playwright-cli
  --exclude=outputs --exclude=generated-images --exclude=chrome_*
  --exclude=backend/data --exclude=backend/knowledge --exclude=.pre-sync-*"
echo "==> [1/4] rsync 源码 + 配置到服务器（排除运行时数据/构建产物）..."
rsync_run $EXCLUDES ./ "$SERVER:$SERVER_DIR/"

# ---- [2/4] 服务器上重建镜像并重启（改动即生效） ----
if [ "$RUN_BUILD" = "1" ]; then
  echo "==> [2/4] 服务器重建容器（层缓存命中，通常 1 分钟内）..."
  ssh_run "$SERVER" "cd $SERVER_DIR && docker compose up -d --build" \
    || { echo "⚠ 服务器重建失败（查看上方日志）；代码已同步，可稍后手动：cd $SERVER_DIR && docker compose up -d --build" >&2; }
  echo "    容器重建完成，健康检查："
  ssh_run "$SERVER" 'for i in $(seq 1 12); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:40014/api/health && break; sleep 5; done; curl -m 5 -s http://127.0.0.1:40014/api/health' \
    || echo "    ⚠ 健康检查未通过，请查看：docker compose logs" || true
else
  echo "==> [2/4] 跳过服务器重建（--skip-build）。代码已同步，服务器上执行 docker compose up -d --build 生效。"
fi

# ---- [3/4] 线上官网同步（platform/homePage → https://www.nengyousuan.com） ----
if [ "$RUN_PORTAL" = "1" ]; then
  echo "==> [3/4] 同步门户官网 platform/homePage/ → $PORTAL_SERVER:$PORTAL_REMOTE_DIR ..."
  rsync_run --delete --exclude='.DS_Store' --exclude='.serve.pid' --exclude='.serve.log' \
    --exclude='*.log' ./platform/homePage/ "$PORTAL_SERVER:$PORTAL_REMOTE_DIR/" \
    && echo "    官网已更新: https://www.nengyousuan.com" \
    || echo "    ⚠ 官网同步失败（不影响平台；检查免密/网络）" >&2
fi

# ---- [4/4] git 提交并推送（可选） ----
if [ "$RUN_GIT" = "1" ]; then
  echo "==> [4/4] git 提交并推送 GitHub"
  git add -A
  if git diff --cached --quiet; then
    echo "    无本地改动，跳过提交"
  else
    git commit -q -m "${MSG:-sync: 更新代码}" && echo "    已提交: ${MSG:-sync: 更新代码}"
  fi
  echo "    推送到 GitHub（网络不通时自动跳过，稍后可用 ./push.sh）..."
  if command -v timeout >/dev/null 2>&1; then GIT_T="timeout 90"; else GIT_T=""; fi
  if $GIT_T git pull --rebase "$GIT_REMOTE" "$GIT_BRANCH" 2>/dev/null && $GIT_T git push "$GIT_REMOTE" "$GIT_BRANCH" 2>/dev/null; then
    echo "    推送完成"
  else
    echo "    ⚠ 本次未能推送（GitHub 网络问题），改动已在本地提交，稍后执行 ./push.sh"
  fi
else
  echo "==> [4/4] 已跳过 git（--no-git）"
fi

echo "==> 全部完成。服务器访问：http://36.151.146.71:40014  （日志：docker logs -f steel-carbon-twin）"
