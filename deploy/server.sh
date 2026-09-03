#!/usr/bin/env bash
# ============================================================================
# 能碳智控平台 · 全新服务器一键部署（Docker 镜像版 · 免 pip/npm/node）
#
# 服务器只需安装 Docker，镜像内已含后端依赖 + 前端构建产物：
#   - 有镜像源（ghcr 已发布）→ docker compose pull，秒级拉起，零编译
#   - 无镜像源/离线网络   → docker compose build（利用层缓存，只编译一次）
# 不再像旧版那样在服务器装 python3-venv/npm/node_modules/vite，大幅省资源。
#
# 用法（服务器 root，Ubuntu/Debian/CentOS）：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh | bash
#   自定义仓库 / 分支 / 目录 / 端口：
#   curl -fsSL <同上> | bash -s -- -r gitee.com/user/mirror -b main -d /opt/carbon-platform
#
# 选项：
#   -r, --repo <owner/repo>  源码仓库（默认内置；公开仓库拉取无需 token）
#   -b, --branch <branch>    分支（默认 master）
#   -d, --dir <path>         安装目录（默认 /opt/carbon-platform）
#   -p, --pull               优先 docker compose pull（ghcr 镜像），默认本地 build
#   -h, --help               显示本帮助
# ============================================================================
set -euo pipefail

DEFAULT_REPO="zhibinQiu/power_simulation"
DEFAULT_BRANCH="master"
DEFAULT_DIR="/opt/carbon-platform"
DEFAULT_PORT=40014

REPO="$DEFAULT_REPO"
BRANCH="$DEFAULT_BRANCH"
INSTALL_DIR="$DEFAULT_DIR"
PORT="$DEFAULT_PORT"
USE_PULL=0

usage() {
  cat <<'USAGE'
能碳智控平台 · 全新服务器一键部署（Docker 镜像版）

用法（root）：
  curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh | bash
  curl -fsSL <同上> | bash -s -- -d /opt/carbon-platform -p 40014

选项：
  -r, --repo <owner/repo>  源码仓库（默认内置，公开仓库无需 token）
  -b, --branch <branch>    分支（默认 master）
  -d, --dir <path>         安装目录（默认 /opt/carbon-platform）
  -p, --port <port>        对外端口（默认 40014，遵循 40000+ 端口规范）
      --pull               优先拉取 ghcr.io 镜像（默认本地 docker build）
  -h, --help               显示本帮助
USAGE
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -r|--repo)   REPO="${2:-}";        shift 2 ;;
    -b|--branch) BRANCH="${2:-}";      shift 2 ;;
    -d|--dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    -p|--port)   PORT="${2:-}";        shift 2 ;;
    --pull)      USE_PULL=1;           shift ;;
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
[ -n "$REPO" ] && [ -n "$BRANCH" ] || { echo "[error] 仓库地址不能为空" >&2; exit 1; }

log() { echo -e "\033[32m[deploy:server]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ---------- 0. root 与 docker ----------
[ "$(id -u)" -eq 0 ] || err "请以 root 运行（或 sudo bash $0）"
command -v git >/dev/null 2>&1 || err "缺少 git：apt/yum install -y git"
if ! command -v docker >/dev/null 2>&1; then
  log "安装 Docker（官方脚本）..."
  curl -fsSL https://get.docker.com | sh || err "Docker 安装失败，请手动安装后重跑"
fi
if ! docker info >/dev/null 2>&1; then
  log "启动 docker 服务..."
  systemctl enable --now docker >/dev/null 2>&1 || service docker start || true
fi
command -v docker compose >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 \
  || err "缺少 docker compose 插件（Docker ≥ 20.10 自带，重装 docker 即可）"

# ---------- 1. 拉取源码（仅取部署编排 + 数据/配置模板） ----------
if [ -d "$INSTALL_DIR/.git" ]; then
  log "目录已是 git 仓库：$INSTALL_DIR"
  log "已部署实例请使用「更新脚本」：deploy/update.sh（备份现场数据后安全更新）"
  exit 0
fi
mkdir -p "$(dirname "$INSTALL_DIR")"
log "克隆源码：https://github.com/$REPO（分支 $BRANCH）→ $INSTALL_DIR"
git clone --depth 1 -b "$BRANCH" "https://github.com/$REPO.git" "$INSTALL_DIR"
[ -f "$INSTALL_DIR/docker-compose.yml" ] || err "源码结构异常：缺少 docker-compose.yml"

# ---------- 2. 端口占位替换（可选） ----------
if [ "$PORT" != "40014" ]; then
  sed -i "s/\"$DEFAULT_PORT:8010\"/\"$PORT:8010\"/" "$INSTALL_DIR/docker-compose.yml"
  log "对外端口改为 $PORT"
fi

# ---------- 3. .env 模板 ----------
[ -f "$INSTALL_DIR/.env" ] || cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
log "已生成 $INSTALL_DIR/.env（如需大模型问答，编辑填 LLM_API_KEY）"

# ---------- 4. 启动（镜像拉取 或 本地构建） ----------
cd "$INSTALL_DIR"
if [ "$USE_PULL" -eq 1 ]; then
  log "拉取 ghcr.io 镜像（docker compose pull）..."
  docker compose pull || { log "镜像拉取失败（可能未发布），回退本地构建..."; USE_PULL=0; }
fi
if [ "$USE_PULL" -eq 0 ]; then
  log "构建镜像（首次约 3~5 分钟，含前端编译 + Python 依赖；之后有层缓存秒级）..."
  docker compose build || err "镜像构建失败，请查看上方日志"
fi
docker compose up -d || err "容器启动失败，请查看上方日志"

# ---------- 5. 自检与提示 ----------
sleep 3
NAME="steel-carbon-twin"
if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  log "部署完成 ✓ 平台已启动"
  log "  访问地址：http://${IP:-<服务器IP>}:$PORT"
  log "  文档站  ：http://${IP:-<服务器IP>}:40184"
  log "  日志查看：docker logs -f $NAME"
  log "  更新     ：deploy/update.sh（git pull + docker compose up -d --build）"
  log "  备注：平台如需连接云端 MQTT / cloud-agent，在「总览 → 配置」填写云端地址即可"
else
  err "平台容器启动失败，请查看：docker compose logs"
fi
