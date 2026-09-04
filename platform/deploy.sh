#!/usr/bin/env bash
# ============================================================================
# 能碳全平台 · 部署入口（platform/deploy.sh）
#
# 面向【全新部署 / 首次安装 / 接入 / 打包】类操作；日常更新请走
# platform/update.sh（代码同步 / 内容发布）。两类脚本与各部署单元统一
# 命名一致：deploy.sh = 第一次部署环境；update.sh = 后续更新代码。
#
# 目标服务器地址统一配置在 platform/servers.conf，本脚本不内嵌 IP；
# 目标机执行类（server/cloud/box 等）在目标机器 root 下运行。
#
# 用法：bash platform/deploy.sh <目标> [脚本参数...]
#
#   目标          功能                                    脚本（在哪台机器执行）
#   ------------  ---------------------------------------  --------------------------
#   server        平台全新服务器一键部署                    bs-deploy/deploy.sh（目标机 root）
#   cloud         云端控制面/数据面/时序库/agent            cloud-deploy/deploy_cloud.sh（云机 root）
#   box           盒子 GitHub 在线一键接入                  box-deploy/box.sh（盒子 root）
#   deploy-box    盒子完整离线部署（依赖+mapper+mosquitto） box-deploy/deploy_box.sh（盒子 root）
#   migrate-box   盒子换云迁移                              box-deploy/migrate-box.sh（盒子 root）
#   portal-install 门户独立站点安装（systemd 常驻）         portal-deploy/deploy.sh（开发机）
#   docs-install  文档站首次拉起/重建                       doc-deploy/deploy.sh（开发机）
#   nginx         官网域名反代网关配置下发                  nginx-deploy/deploy.sh（开发机）
#   mac           macOS 桌面客户端打包                      mac-deploy/build_mac.sh（本机）
#   windows       Windows 桌面客户端打包                    windows-deploy/build_windows.bat（Win）
#   list          列出本入口支持的部署矩阵（默认无参数时显示）
#
# 示例：
#   bash platform/deploy.sh server
#   bash platform/deploy.sh box -i 36.151.146.71 -n my-box-01 -t <token>
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
  server)
    echo "==> 平台全新服务器一键部署（仅需 Docker）"
    echo "    请在目标服务器 root 下执行；curl 版：bash <(curl -fsSL https://raw.githubusercontent.com/zhibinQiu/power_simulation/master/platform/bs-deploy/deploy.sh) $*"
    exec bash "$DIR/bs-deploy/deploy.sh" "$@"
    ;;
  cloud)
    echo "==> 云端部署（K3s 控制面 / 数据面 / TDengine / cloud-agent）"
    echo "    请在云端服务器（${CLOUD_IP:-36.151.146.71}）root 下执行"
    exec bash "$DIR/cloud-deploy/deploy_cloud.sh" "$@"
    ;;
  box)
    echo "==> 盒子 GitHub 在线一键接入"
    echo "    请在盒子 root 下执行（Debian/Ubuntu arm64）"
    exec bash "$DIR/box-deploy/box.sh" "$@"
    ;;
  deploy-box|box-offline)
    echo "==> 盒子完整离线部署（依赖 + mapper + mosquitto + systemd）"
    echo "    请在盒子 root 下执行"
    exec bash "$DIR/box-deploy/deploy_box.sh" "$@"
    ;;
  migrate-box)
    echo "==> 盒子换云迁移"
    echo "    请在盒子 root 下执行"
    exec bash "$DIR/box-deploy/migrate-box.sh" "$@"
    ;;
  portal-install)
    echo "==> 门户独立站点安装（默认 ${PORTAL_SSH:-root@36.151.146.71}:${PORTAL_PORT:-40200}，systemd 常驻）"
    echo "    用法：bash platform/deploy.sh portal-install [-s root@<服务器>] [-p <端口>]"
    exec bash "$DIR/portal-deploy/deploy.sh" "$@"
    ;;
  docs-install)
    echo "==> 文档站首次拉起/重建（复用 doc-deploy/update.sh 幂等链路，容器缺失自动构建）"
    exec bash "$DIR/doc-deploy/deploy.sh" "$@"
    ;;
  nginx)
    echo "==> 官网域名反代网关配置下发（本机执行 → ${WEB_SSH:-root@43.161.194.75} nginx）"
    echo "    源配置：platform/nginx-deploy/nengyousuan.conf（自动备份 + nginx -t 校验 + reload）"
    exec bash "$DIR/nginx-deploy/deploy.sh" "$@"
    ;;
  mac)
    echo "==> macOS 桌面客户端打包"
    exec bash "$DIR/mac-deploy/build_mac.sh" "$@"
    ;;
  windows)
    echo "==> Windows 桌面客户端打包（需在 Windows 机器执行）："
    echo "    cd platform/windows-deploy && build_windows.bat $*"
    exit 0
    ;;
  list|-l|--list|-h|--help|-help)
    usage
    ;;
  *)
    echo "[error] 未知目标：${TARGET}（bash platform/deploy.sh list 查看全部）" >&2
    exit 1
    ;;
esac
