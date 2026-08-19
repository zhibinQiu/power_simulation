#!/usr/bin/env bash
#
# push.sh —— 把本项目（含已编译的前端）同步到部署服务器
#
# 目标服务器（来自 docker-compose.yml 注释：映射目录 /root/qzb/jianpai）
#   172.19.134.45  (user: root)
#
# 用法：
#   普通推送（用本地已有的 frontend/dist）：        ./push.sh
#   推送前先本地重新构建前端：                      BUILD_FRONTEND=1 ./push.sh
#   只预览会改动哪些文件（不实际传输）：            ./push.sh --dry-run
#   推送但不重启容器：                              RESTART_CONTAINER=0 ./push.sh
#
# 说明：
#   - 采用 rsync 增量同步，只传变化的部分，第二次起很快。
#   - 容器 steel-carbon-twin 用 volume 挂载项目目录，后端 .py 改动会被 uvicorn --reload 自动热加载；
#     前端 dist 属静态托管，推送后默认重启一次容器以确保新前端立即生效。
#   - 远端独有的 data-terminal/ 目录被显式保护，不会被删除或覆盖。
#
set -euo pipefail

# ============================ 配置（如需改服务器，改这里） ============================
REMOTE_HOST="172.19.134.45"
REMOTE_USER="root"
REMOTE_PATH="/root/qzb/jianpai"
CONTAINER_NAME="steel-carbon-twin"

# 本地项目根 = 本脚本所在目录
LOCAL_PATH="$(cd "$(dirname "$0")" && pwd)"

# 行为开关（可用环境变量覆盖，见上方用法）
BUILD_FRONTEND="${BUILD_FRONTEND:-0}"      # 1 = 推送前先 npm run build
RESTART_CONTAINER="${RESTART_CONTAINER:-1}" # 0 = 推送后不重启容器

# ============================ 排除规则（不上传到服务器的内容） ============================
# 注意：/* 锚定到项目根，所以 /*.png 只排除“根目录下的开发截图”，
#       不会影响 frontend/dist/assets 里真正需要的前端图片。
EXCLUDES=(
  --exclude='node_modules'
  --exclude='frontend/node_modules'
  --exclude='.venv'            # 本地 Python 虚拟环境：容器用镜像内依赖，不必上传，且极易触发 rsync 退出码 23
  --exclude='*.egg-info'
  --exclude='__pycache__'
  --exclude='*.pyc'
  --exclude='.DS_Store'
  --exclude='*.log'
  --exclude='.playwright-cli'
  --exclude='generated-images'
  --exclude='outputs'
  --exclude='.workbuddy'       # 本机 agent 工作记忆，不属于部署内容
  --exclude='/*.png'            # 仅排除根目录的开发截图/验证图
  --exclude='data-terminal/'   # 保护服务器上已有的独立目录：不同步、不删除
)

# ============================ 解析参数 ============================
RSYNC_OPTS=(-az -r --delete -P "${EXCLUDES[@]}")   # -r 必须独立书写：macOS 自带 openrsync 的 --delete 校验只认独立 -r 标志
SSH_OPTS=(-o StrictHostKeyChecking=no -o BatchMode=yes)

DRY_RUN=""
if [ "${1:-}" = "--dry-run" ] || [ "${1:-}" = "-n" ]; then
  DRY_RUN=1
  RSYNC_OPTS=(--dry-run "${RSYNC_OPTS[@]}")
  echo ">>> [dry-run] 仅预览，不会实际传输/删除"
fi

# ============================ 可选：先构建前端 ============================
if [ "$BUILD_FRONTEND" = "1" ]; then
  echo ">>> 构建前端 (npm run build) ..."
  (cd "$LOCAL_PATH/frontend" && npm run build)
fi

# ============================ 同步到服务器 ============================
echo ">>> 同步 ${LOCAL_PATH}/  ->  ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/"
# 把 rsync 放进 if 条件里：即使 rsync 偶发非 0（如个别文件临时失败），也不会被 set -e 中断，
# 后续的重启步骤照常执行；同时不依赖捕获变量，避免 set -u 的未定义变量坑。
if rsync "${RSYNC_OPTS[@]}" -e "ssh ${SSH_OPTS[*]}" \
    "$LOCAL_PATH/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/"; then
  :
else
  echo "警告: rsync 返回非 0（openrsync 大批量传输常见，若上方无明显报错可忽略）"
fi

# ============================ 可选：重启容器使改动生效 ============================
if [ "$RESTART_CONTAINER" = "1" ]; then
  if [ -n "$DRY_RUN" ]; then
    echo ">>> [dry-run] 将重启容器: $CONTAINER_NAME"
  else
    echo ">>> 重启容器 $CONTAINER_NAME ..."
    ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" "docker restart ${CONTAINER_NAME}" \
      || echo "警告: 容器重启失败，请登录服务器手动检查 (docker restart ${CONTAINER_NAME})"
  fi
fi

echo ">>> 完成。"
