#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 代码更新脚本（platform/bs-deploy/update.sh）
#
# 用途（开发机执行，日常更新唯一通道）：
#   本地构建前端/文档站产物 → rsync 源码到服务器 → 容器按需重建/热生效 → 健康检查
#
# 用法：bash platform/bs-deploy/update.sh [--server root@<主机>] [--skip-build] [--skip-config]
#       （或统一入口：bash platform/update.sh bs，二者等价）
#       --skip-config：本次**不**用本地 backend/config 覆盖服务器（默认每次都覆盖，见 [2/3]）
#       bash platform/bs-deploy/update.sh push ["提交信息" [--tag v1.0.0]]  # 推送代码到 GitHub（调仓库根 ./push.sh）
#   默认目标：71（root@36.151.146.71:/root/qzb/jianpai，Docker 源码卷挂载 + uvicorn --reload）
#   说明：同步本地工作区（含未提交改动），改完即可上线；代码入库推送走本脚本 push 子命令，
#         （协作者 / 其他场景统一用仓库根 ./push.sh）。
#
#   注意：代码更新一律由开发机向服务器推送（rsync），服务器不自拉 git；
#   全新部署 / 重装请走 platform/bs-deploy/deploy.sh（服务器侧 git clone）。
# ============================================================================
set -euo pipefail

# ---- 公共库（platform/lib.sh）：仓库根 ROOT / servers.conf / ssh_run / rsync_run / 标准排除列表 ----
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SELF_DIR/../lib.sh"
cd "$ROOT"

# ---- push 子命令：把本地改动提交并推送到 GitHub（调用仓库根 push.sh，与协作者同源） ----
if [ "${1:-}" = "push" ]; then
  shift
  exec bash "$ROOT/push.sh" "$@"
fi

CLOUD_MAIN="${CLOUD_MAIN:-${PLATFORM_SSH:-root@36.151.146.71}}"   # 默认目标（现 71）
SERVER="$CLOUD_MAIN"
SERVER_DIR="${PLATFORM_DIR:-/root/qzb/jianpai}"                   # 服务器仓库根
BS_DIR="$SERVER_DIR/platform/bs-deploy"
IMAGE_NAME="ghcr.io/zhibinqiu/power_simulation:latest"

# ---- 解析参数 ----
RUN_BUILD=1
SYNC_CONFIG=1
while [ $# -gt 0 ]; do
  case "$1" in
    # 每个分支都必须 shift：漏掉会让 $# 不变 → while 死循环（进程 100% CPU 空转）
    --skip-build) RUN_BUILD=0; shift ;;
    --skip-config|--no-config) SYNC_CONFIG=0; shift ;;
    --server|--target) SERVER="${2:-$CLOUD_MAIN}"; shift 2 ;;
    *) echo "[error] 未知参数：${1}（-h 查看头部注释）" >&2; exit 1 ;;
  esac
done

command -v rsync >/dev/null 2>&1 || { echo "❌ 缺少 rsync" >&2; exit 1; }
echo "==> 仓库根：$ROOT"
echo "==> 同步目标：$SERVER:$SERVER_DIR"

# ---- [1/3] 本地构建前端/文档站产物（dist 不入版本库，构建后随 rsync 同步到服务器；失败不阻断） ----
if [ "$RUN_BUILD" = "1" ]; then
  echo "==> [1/3] 本地构建前端与文档站产物..."
  (cd frontend && npx vite build >/dev/null 2>&1) && echo "    frontend/dist 已构建" \
    || echo "    ⚠ frontend 构建失败/跳过（检查 node_modules）"
  (cd platform/doc-deploy/docs-site && npx vite build >/dev/null 2>&1) && echo "    docs-site/dist 已构建" \
    || echo "    ⚠ docs-site 构建失败/跳过"
else
  echo "==> [1/3] 跳过本地构建（--skip-build）"
fi

# ---- [2/3] 配置/数据同步（本地为准）+ rsync 源码到服务器（排除本机环境与临时产物） ----
# 配置口径（用户要求：**每次推送都把本地配置文件推到服务器**，本地为唯一真源）：
#   backend/config/ 整个目录随每次同步覆盖服务器——含 box_devices.json（采集设备/模型定义）、
#   data_sources.json（数据源目录）、box_config.json / middleware.json / links.json / llm*.json /
#   mcp_*.json / strategies.json，以及 gitignore 的本地覆盖项 .env 等。
#   生产侧的增删改一律在平台界面操作后回填开发机，否则会被下一次 update.sh 覆盖。
#   ① 覆盖前先把服务器整目录备份到 <仓库根>/.devcfg-backup/config.<时间戳>（便于回滚）；
#   ② 显式 --include=backend/config/*** 且置于所有排除规则之前，后续新增宽泛排除不会误伤配置；
#   ③ *.bak.* 备份件不同步（本地/服务器的历史备份不上传，避免目录堆积）；
#   ④ 配置确有变更时重启后端容器使其生效（uvicorn --reload 只监听 .py，不监听配置文件）。
# 数据/内容口径（用户要求：**项目相关的本地文件一律同步**，本地为唯一真源）：
#   backend/data 下的项目资产同步——scenes（场景/编排模板快照）、designs（编排方案服务端存档
#   flow/agc，原只存在浏览器 localStorage）、ontology / agents / skills 等平台资产；
#   backend/knowledge 知识库文档同样同步。
#   运行产出（服务器自有的业务数据）**不同步**，避免把生产数据抹成开发机状态：
#   reports（报告及其索引）/ sessions.json（聊天会话）/ carbon_compliance.json（企业碳合规台账）/
#   market_snapshot.json（行情缓存）。
#   覆盖前服务器整目录备份到 <仓库根>/.devcfg-backup/<名>.<时间戳>，可随时回滚；
#   这些文件由 JsonRepository 按文件指纹失效（mtime+size）自动重读，**无需重启容器**，
#   故只有 backend/config 变更才触发重启。
# 平台专属排除（通用项与运行期状态文件由 lib.sh 的 LIB_EXCLUDE_COMMON / LIB_EXCLUDE_STATE 提供）
EXTRA_EXCLUDES="--exclude=platform/doc-deploy/docs-site/node_modules
  --exclude=outputs --exclude=generated-images --exclude=.playwright-cli --exclude=chrome_*
  --exclude=backend/data/reports/*** --exclude=backend/data/sessions.json
  --exclude=backend/data/carbon_compliance.json --exclude=backend/data/market_snapshot.json"
# 显式 include 须先于排除规则（rsync「先匹配者生效」），防止后续新增宽泛排除误伤
DATA_INCLUDES="--include=backend/knowledge/ --include=backend/knowledge/*** --include=backend/data/scenes/*** --include=backend/data/designs/***"
# 覆盖前需要备份的服务器目录（本地为唯一真源，覆盖即生效，故先留回滚点）
SYNC_DIRS="backend/config backend/data backend/knowledge"
CFG_BACKUP_DIR=".devcfg-backup"
BK_TS="$(date +%Y%m%d%H%M%S)"
if [ "$SYNC_CONFIG" = "1" ]; then
  # 配置目录：先排除备份件、再整体 include（rsync「先匹配者生效」，顺序不可颠倒）
  CFG_INCLUDES="--include=backend/config/ --exclude=backend/config/*.bak.* --include=backend/config/***"
  # 覆盖前逐一备份服务器现有目录（本地为真源，覆盖后不留回滚点将无法恢复生产数据）
  for d in $SYNC_DIRS; do
    if ssh_run "$SERVER" "cd '$SERVER_DIR' && mkdir -p '$CFG_BACKUP_DIR' && [ -d '$d' ] && cp -a '$d' '$CFG_BACKUP_DIR/$(basename "$d").${BK_TS}'" 2>/dev/null; then
      echo "    ✓ 服务器现有 ${d} 已备份到 ${SERVER_DIR}/${CFG_BACKUP_DIR}/$(basename "$d").${BK_TS}"
    else
      echo "    ⚠ 服务器尚无 ${d} 可备份（全新部署，本次直接同步本地版本）"
    fi
  done
else
  CFG_INCLUDES="--exclude=backend/config/*** --exclude=backend/data/*** --exclude=backend/knowledge/***"
  echo "    · 本次跳过配置/数据同步（--skip-config），服务器 backend/config|data|knowledge 保持原样"
fi

echo "==> [2/3] rsync 源码 + 配置/数据 + 前端产物到服务器..."
RSYNC_LOG="${TMPDIR:-/tmp}/nengtan-rsync-${BK_TS}.log"
rsync_run $DATA_INCLUDES \
  $CFG_INCLUDES \
  "${LIB_EXCLUDE_COMMON[@]}" "${LIB_EXCLUDE_STATE[@]}" $EXTRA_EXCLUDES --itemize-changes \
  ./ "$SERVER:$SERVER_DIR/" | tee "$RSYNC_LOG"
# 从传输清单挑出本次真正变更的文件（<f = 本地→服务器传输，>f = 反向；--skip-config 时列表恒空）
CFG_CHANGED="$(awk '$1 ~ /^[<>]f/ { print $2 }' "$RSYNC_LOG" 2>/dev/null | grep '^backend/config/' || true)"
DATA_CHANGED="$(awk '$1 ~ /^[<>]f/ { print $2 }' "$RSYNC_LOG" 2>/dev/null | grep -E '^backend/(data|knowledge)/' || true)"
rm -f "$RSYNC_LOG"
if [ -n "$DATA_CHANGED" ]; then
  echo "    ↪ 数据/内容已随本次推送更新到服务器（编排存档 / 场景包 / 知识库…）："
  echo "$DATA_CHANGED" | sed 's/^/       - /'
  echo "    ↳ 无需重启：JsonRepository 按文件指纹（mtime+size）自动重读，知识库按目录实时读取"
fi
if [ -n "$CFG_CHANGED" ]; then
  echo "    ↪ 配置已随本次推送更新到服务器："
  echo "$CFG_CHANGED" | sed 's/^/       - /'
  echo "    ↳ 重启后端容器使新配置生效（uvicorn --reload 只监听 .py，不监听配置文件）"
  ssh_run "$SERVER" "cd $BS_DIR && docker compose restart steel-twin" >/dev/null 2>&1 \
    || echo "    ⚠ 后端容器重启失败，请手动执行：ssh $SERVER 'cd $BS_DIR && docker compose restart steel-twin'" >&2
else
  echo "    ✓ 配置无变更（服务器 backend/config 与本地一致）"
fi

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
