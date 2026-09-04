#!/usr/bin/env bash
# ============================================================================
# 能碳全平台 · 更新入口（platform/update.sh）
#
# 面向【日常更新 / 代码同步 / 内容发布】类操作；全新部署 / 首次安装 /
# 接入 / 打包请走 platform/deploy.sh。两类脚本与各部署单元统一命名一致：
# deploy.sh = 第一次部署环境；update.sh = 后续更新代码。
#
# 目标服务器地址统一配置在 platform/servers.conf，本脚本不内嵌 IP；
# 均在本机（开发机）执行，代码 rsync / git 推送后由服务器容器 reload 生效。
#
# 用法：bash platform/update.sh <目标> [脚本参数...]
#
#   目标          功能                                    脚本（在哪台机器执行）
#   ------------  ---------------------------------------  --------------------------
#   update|bs     平台更新：本地构建 + 推送代码到平台机     bs-deploy/update.sh（开发机）
#   push          提交并推送到 GitHub                      push.sh（仓库根）
#   portal        门户官网内容更新                          portal-deploy/update.sh（开发机）
#   docs          文档站 + 源文档更新                       doc-deploy/update.sh（开发机）
#   list          列出本入口支持的更新矩阵（默认无参数时显示）
#
# 示例：
#   bash platform/update.sh bs                              # 平台代码推送：本地构建 + rsync（update 等价）
#   bash platform/update.sh bs --server root@<主机>          # 推送到指定服务器
# ============================================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$DIR/servers.conf"                       # 服务器地址集中配置
[ -f "$CONF" ] && . "$CONF" || true

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 0
}

[ $# -ge 1 ] || usage
TARGET="$1"
shift

case "$TARGET" in
  update|bs|platform)
    echo "==> 平台更新：本地构建 + 推送代码到平台机（开发机执行 → ${PLATFORM_SSH:-root@36.151.146.71} 容器 reload 生效）"
    exec bash "$DIR/bs-deploy/update.sh" "$@"
    ;;
  push)
    exec bash "$DIR/../push.sh" "$@"
    ;;
  portal)
    echo "==> 平台门户官网内容更新（本机执行 → https://www.nengyousuan.com）"
    echo "    门户源码：platform/portal-deploy/（脚本自身即更新器；免密 SSH 或 export QZB_SSH_PASS=密码）"
    exec bash "$DIR/portal-deploy/update.sh" "$@"
    ;;
  docs)
    echo "==> 文档站 + 源文档更新部署（本机执行 → ${PLATFORM_IP:-36.151.146.71}:${DOCS_PORT:-40184} 文档站容器）"
    echo "    内容：platform/doc-deploy/（docs-site 站点 + docs 源文档）"
    exec bash "$DIR/doc-deploy/update.sh" "$@"
    ;;
  list|-l|--list|-h|--help|-help)
    usage
    ;;
  *)
    echo "[error] 未知目标：${TARGET}（bash platform/update.sh list 查看全部）" >&2
    exit 1
    ;;
esac
