#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 文档站/文档更新脚本（platform/doc-deploy/update.sh，开发机执行）
#
# 职责：文档站（platform/doc-deploy/docs-site，宣传手册/使用手册/技术文档）
#       与源文档（platform/doc-deploy/docs）同步发布到平台机（目标见
#       platform/servers.conf PLATFORM_SSH/PLATFORM_DIR/DOCS_PORT），并让运行中的
#       docs-site 容器立即加载新内容：
#         ① 本机构建 docs-site/dist（npx vite build）
#         ② rsync platform/doc-deploy/ 与构建编排文件 → 平台机仓库根
#         ③ 编排/镜像输入有变更 → docker compose up -d --build docs-site
#            （仅首次或 compose/Dockerfile.docs 变更时）
#            无变更 → docker compose restart docs-site（dist 卷挂载即生效）
#         ④ 健康自检
#
# 用法（仓库根任一路径执行均可，脚本自动定位仓库根）：
#   bash platform/update.sh docs                        # 文档站更新（推荐统一入口）
#   bash platform/doc-deploy/update.sh                  # 直接调用
#
# 服务器免密说明：默认 BatchMode=yes 走 SSH 密钥；未配置密钥时可用
#   export QZB_SSH_PASS='<密码>' bash platform/doc-deploy/update.sh
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SELF_DIR/../.." && pwd)"
cd "$ROOT"
CONF="$ROOT/platform/servers.conf"      # 服务器地址集中配置（platform/servers.conf）
[ -f "$CONF" ] && . "$CONF" || true

SERVER="${DOC_SERVER:-${PLATFORM_SSH:-root@36.151.146.71}}"   # 文档站随平台同机（servers.conf PLATFORM_SSH）
SERVER_DIR="${PLATFORM_DIR:-/root/qzb/jianpai}"                # 服务器仓库根（servers.conf PLATFORM_DIR）
BS_DIR="platform/bs-deploy"                   # 服务器构建编排目录（相对仓库根）
DOC_SITE="platform/doc-deploy/docs-site"
DOC_DIR="platform/doc-deploy"

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

command -v rsync >/dev/null 2>&1 || { echo "❌ 缺少 rsync" >&2; exit 1; }
[ -f "$DOC_SITE/package.json" ] || { echo "❌ 未找到文档站源码（应在 platform/doc-deploy/docs-site/）" >&2; exit 1; }

echo "==> 文档站更新部署：$DOC_DIR → $SERVER:$SERVER_DIR"
echo "    服务器访问：http://${SERVER#*@}:${DOCS_PORT:-40184}"

# ---- [1/4] 本地构建文档站产物 ----
echo "==> [1/4] 构建文档站产物（$DOC_SITE: npx vite build）..."
(cd "$DOC_SITE" && npm install --silent >/dev/null 2>&1 || true)
(cd "$DOC_SITE" && npx vite build) || { echo "❌ 文档站构建失败" >&2; exit 1; }
echo "    ✔ dist 已构建"

# ---- [2/4] rsync 文档站 + 源文档 + 构建编排到服务器（运行时数据不上传） ----
echo "==> [2/4] rsync 到服务器（doc-deploy/ + 编排文件）..."
rsync_run \
  --exclude=node_modules --exclude=.DS_Store --exclude='*.log' \
  "$DOC_DIR/" "$SERVER:$SERVER_DIR/$DOC_DIR/"
rsync_run "$BS_DIR/docker-compose.yml" "$SERVER:$SERVER_DIR/$BS_DIR/docker-compose.yml"
rsync_run "$BS_DIR/Dockerfile.docs"    "$SERVER:$SERVER_DIR/$BS_DIR/Dockerfile.docs"

# ---- [3/4] 服务器更新容器：编排/镜像输入变更 → 重建；否则重启即可（dist 卷挂载） ----
need_build() {
  local f rh lh
  for f in "$BS_DIR/docker-compose.yml" "$BS_DIR/Dockerfile.docs"; do
    rh=$(ssh_run "$SERVER" "cd '$SERVER_DIR' && md5sum '$f' 2>/dev/null | cut -d' ' -f1" 2>/dev/null || true)
    [ -n "$rh" ] || { echo "    服务器缺少 $f → 需重建镜像"; return 0; }
    if command -v md5sum >/dev/null 2>&1; then lh=$(md5sum "$f" 2>/dev/null | cut -d' ' -f1); else lh=$(md5 -q "$f" 2>/dev/null || true); fi
    [ -n "$lh" ] && [ "$lh" != "$rh" ] && { echo "    ↪ $f 已变更 → 重建镜像"; return 0; }
  done
  # 容器尚不存在（如 docs-site 服务从未起过）也需要构建
  ssh_run "$SERVER" "docker ps -a --format '{{.Names}}' | grep -qx 'nengtan-docs-site'" 2>/dev/null \
    || { echo "    容器不存在 → 首次构建"; return 0; }
  return 1
}

echo "==> [3/4] 更新服务器 docs-site 容器..."
if need_build; then
  echo "    docker compose up -d --build docs-site（层缓存命中，通常秒级）..."
  ssh_run "$SERVER" "cd '$SERVER_DIR/$BS_DIR' && docker compose up -d --build docs-site" \
    || { echo "⚠ 服务器重建失败，请手动执行：cd $SERVER_DIR/$BS_DIR && docker compose up -d --build docs-site" >&2; exit 1; }
else
  echo "    编排无变更 → docker compose restart docs-site（dist 卷挂载即生效）..."
  ssh_run "$SERVER" "cd '$SERVER_DIR/$BS_DIR' && docker compose restart docs-site" \
    || { echo "⚠ 服务器重启失败，请查看：docker logs nengtan-docs-site" >&2; exit 1; }
fi

# ---- [4/4] 健康自检 ----
echo "==> [4/4] 健康自检..."
if ssh_run "$SERVER" 'for i in $(seq 1 10); do curl -fsS -m 3 -o /dev/null http://127.0.0.1:40184/ && break; sleep 2; done; curl -m 5 -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:40184/'; then
  echo "✔ 文档站已更新：http://${SERVER#*@}:${DOCS_PORT:-40184}"
else
  echo "⚠ 自检未通过，请查看：docker logs nengtan-docs-site" >&2
  exit 1
fi
