#!/usr/bin/env bash
# ============================================================================
# 能碳智控平台 · 全新服务器一键部署（GitHub 源码拉取，公开仓库无需任何凭证）
#
# 在全新 Ubuntu/Debian/CentOS 服务器（root 或 sudo）上执行：拉取源码 → 安装
# 后端依赖 → 构建前端 → systemd 常驻启动平台（后端托管前端，单端口对外）。
#
# 用法（服务器 root）：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh | bash
#   自定义仓库 / 分支 / 目录 / 端口：
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh \
#     | bash -s -- -r gitee.com/user/mirror -b main -d /opt/carbon-platform -p 40013
#
# 选项：
#   -r, --repo <owner/repo>  源码仓库（默认内置；公开仓库拉取无需 token）
#   -b, --branch <branch>    分支（默认 master）
#   -d, --dir <path>         安装目录（默认 /opt/carbon-platform）
#   -p, --port <port>        对外监听端口（默认 40013，遵循 40000+ 端口规范）
#   -h, --help               显示本帮助
# ============================================================================
set -euo pipefail

DEFAULT_REPO="zhibinQiu/power_simulation"   # ← 改为你的公开仓库 owner/repo
DEFAULT_BRANCH="master"
DEFAULT_DIR="/opt/carbon-platform"
DEFAULT_PORT=40013

REPO="$DEFAULT_REPO"
BRANCH="$DEFAULT_BRANCH"
INSTALL_DIR="$DEFAULT_DIR"
PORT="$DEFAULT_PORT"

usage() {
  cat <<'USAGE'
能碳智控平台 · 全新服务器一键部署（GitHub 源码拉取）

用法（root）：
  curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh | bash
  curl -fsSL <同上> | bash -s -- -r gitee.com/user/mirror -b main -d /opt/carbon-platform -p 40013

选项：
  -r, --repo <owner/repo>  源码仓库（默认内置，公开仓库无需 token）
  -b, --branch <branch>    分支（默认 master）
  -d, --dir <path>         安装目录（默认 /opt/carbon-platform）
  -p, --port <port>        对外监听端口（默认 40013）
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
    -h|--help)   usage ;;
    *) echo "[error] 未知参数：$1（-h 查看帮助）" >&2; exit 1 ;;
  esac
done
[ -n "$REPO" ] && [ -n "$BRANCH" ] || { echo "[error] 仓库地址不能为空" >&2; exit 1; }

log() { echo -e "\033[32m[deploy:server]\033[0m $*"; }
err() { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ---------- 0. 权限与系统依赖 ----------
[ "$(id -u)" -eq 0 ] || err "请以 root 运行（或 sudo bash $0）"
command -v git  >/dev/null 2>&1 || err "缺少 git"
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || err "缺少 curl/wget"

MISSING=""
for c in python3 node npm; do
  command -v "$c" >/dev/null 2>&1 || MISSING="$MISSING $c"
done
if [ -n "$MISSING" ]; then
  if command -v apt-get >/dev/null 2>&1; then
    log "安装系统依赖（apt）：$MISSING"
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip nodejs npm
  elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
    log "安装系统依赖（yum/dnf）：$MISSING"
    (command -v dnf >/dev/null 2>&1 && dnf install -y python3 python3-pip nodejs npm) \
      || yum install -y python3 python3-pip nodejs npm
  else
    err "缺少系统依赖：$MISSING，请手动安装后重跑"
  fi
fi
python3 -m venv --help >/dev/null 2>&1 || err "缺少 python3-venv（Ubuntu/Debian：apt install python3-venv）"

# ---------- 1. 拉取源码（公开仓库，匿名即可） ----------
if [ -d "$INSTALL_DIR/.git" ]; then
  log "目录已是 git 仓库：$INSTALL_DIR"
  log "已部署实例请使用「更新脚本」（自动备份现场配置/数据，避免覆盖 box_devices/links/mqtt.yaml 等）："
  log "  curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/deploy/update.sh | bash -s -- -d $INSTALL_DIR"
  exit 0
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  log "克隆源码：https://github.com/$REPO（分支 $BRANCH）→ $INSTALL_DIR"
  git clone --depth 1 -b "$BRANCH" "https://github.com/$REPO.git" "$INSTALL_DIR"
fi
[ -f "$INSTALL_DIR/backend/config/requirements.txt" ] || err "源码结构异常：缺少 backend/config/requirements.txt"

# ---------- 2. 后端依赖 ----------
cd "$INSTALL_DIR/backend"
[ -d .venv ] || python3 -m venv .venv
log "安装后端依赖（pip，约 1~3 分钟）..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r config/requirements.txt -q || .venv/bin/pip install -r config/requirements.txt

# ---------- 3. 前端构建 ----------
cd "$INSTALL_DIR/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund
log "构建前端（vite build）..."
npx vite build

# ---------- 4. systemd 服务（uvicorn 单端口对外，前端由后端托管） ----------
SERVICE="/etc/systemd/system/carbon-platform.service"
cat > "$SERVICE" <<EOF
[Unit]
Description=Carbon Twin Platform (能碳智控平台)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/backend
ExecStart=$INSTALL_DIR/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable carbon-platform.service
systemctl restart carbon-platform.service

# ---------- 5. 自检与提示 ----------
sleep 2
if systemctl is-active carbon-platform.service >/dev/null 2>&1; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  log "部署完成 ✓ 平台已启动"
  log "  访问地址：http://${IP:-<服务器IP>}:$PORT"
  log "  日志查看：journalctl -u carbon-platform -f"
  log "  服务管理：systemctl status carbon-platform"
  log "  备注：平台如需连接云端 MQTT / cloud-agent，在「总览 → 配置」填写云端地址即可"
else
  err "服务启动失败，请查看：journalctl -u carbon-platform -n 50"
fi
