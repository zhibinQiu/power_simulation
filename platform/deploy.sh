#!/usr/bin/env bash
# ============================================================================
# 能碳全平台 · 统一部署入口（platform/deploy.sh）
#
# 各部署目标脚本统一收口（各司其职，目录即部署单元）：
#   bs-deploy/     平台自身前后端（服务器 Docker 部署：bs = back-stage/platform）
#   cloud-deploy/  云端 KubeEdge 控制面 / 数据面 / TDengine / cloud-agent
#   box-deploy/    边缘盒子（一体机）部署包
#   mac/windows-platform-deploy/   桌面客户端打包
#
# 用法：bash platform/deploy.sh <目标> [脚本参数...]
#
#   目标       功能                                     脚本（在哪台机器执行）
#   ----------  --------------------------------------   --------------------------
#   bs|platform 平台前后端：本地同步 + 部署到 71          bs-deploy/sync.sh（开发机）
#   server      平台全新服务器一键部署                    bs-deploy/server.sh（目标机 root）
#   update      平台服务器更新（数据安全备份+重建）       bs-deploy/update.sh（目标机 root）
#   push        提交并推送到 GitHub                      bs-deploy/push.sh（开发机）
#   cloud       云端控制面/数据面/时序库/agent            cloud-deploy/deploy_cloud.sh（云机 root）
#   box         盒子 GitHub 在线一键接入                 box-deploy/box.sh（盒子 root）
#   deploy-box  盒子完整离线部署（依赖+mapper+mosquitto） box-deploy/deploy_box.sh（盒子 root）
#   migrate-box 盒子换云迁移（免手工签发证书）            box-deploy/migrate-box.sh（盒子 root）
#   mac         桌面客户端 macOS 打包                    mac-platform-deploy/build_mac.sh（本机）
#   windows     桌面客户端 Windows 打包                  windows-platform-deploy/build_windows.bat（Win）
#   home        门户官网内容更新（→ 线上 nengyousuan.com）  home-deploy/sync-home.sh（开发机）
#   home-install 门户独立站点安装（systemd 常驻服务）        home-deploy/deploy_portal.sh（开发机）
#   list        列出部署矩阵（默认无参数时显示）
#
# 示例：
#   bash platform/deploy.sh bs --no-git                          # 同步 71 且不提交 git
#   bash platform/deploy.sh bs "feat: xxx"                        # 同步 + 指定提交信息
#   bash platform/deploy.sh box -i 36.151.146.71 -n my-box-01 -t <token>
# ============================================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  sed -n '6,30p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

[ $# -ge 1 ] || usage
TARGET="$1"
shift

case "$TARGET" in
  bs|platform)
    echo "==> 平台前后端同步部署（本机执行 → 71 服务器源码卷挂载 + reload）"
    exec bash "$DIR/bs-deploy/sync.sh" "$@"
    ;;
  server)
    echo "==> 平台全新服务器一键部署"
    echo "    请在目标服务器 root 下执行；curl 版：bash <(curl -fsSL https://raw.githubusercontent.com/zhibinQiu/power_simulation/master/platform/bs-deploy/server.sh) $*"
    exec bash "$DIR/bs-deploy/server.sh" "$@"
    ;;
  update)
    echo "==> 平台服务器更新（备份现场数据 → git pull → 重建 → 自检）"
    echo "    请在已部署服务器 root 下执行"
    exec bash "$DIR/bs-deploy/update.sh" "$@"
    ;;
  push)
    exec bash "$DIR/bs-deploy/push.sh" "$@"
    ;;
  cloud)
    echo "==> 云端部署（控制面/数据面/TDengine/agent）"
    echo "    请在云端服务器（36.151.146.71）root 下执行"
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
  mac)
    echo "==> macOS 桌面客户端打包"
    exec bash "$DIR/mac-platform-deploy/build_mac.sh" "$@"
    ;;
  windows)
    echo "==> Windows 桌面客户端打包（需在 Windows 机器执行）："
    echo "    cd platform/windows-platform-deploy && build_windows.bat $*"
    exit 0
    ;;
  home|portal)
    echo "==> 平台门户官网内容更新（本机执行 → 线上 https://www.nengyousuan.com）"
    echo "    门户源码：platform/home-deploy/（脚本自身即更新器；免密 SSH 或 export QZB_SSH_PASS=密码）"
    exec bash "$DIR/home-deploy/sync-home.sh" "$@"
    ;;
  home-install|portal-install)
    echo "==> 门户独立站点安装（默认 71:/opt/nengtan-portal 端口 40200，systemd 常驻）"
    echo "    用法：bash platform/deploy.sh home-install [-s root@<服务器>] [-p <端口>]"
    exec bash "$DIR/home-deploy/deploy_portal.sh" "$@"
    ;;
  list|-l|--list)
    usage
    ;;
  *)
    echo "[error] 未知目标：$TARGET（bash platform/deploy.sh list 查看全部）" >&2
    exit 1
    ;;
esac
