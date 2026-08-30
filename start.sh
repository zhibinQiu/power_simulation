#!/usr/bin/env bash
# ============================================================
#  一键启动脚本：工业能碳智控平台
#
#  用法:
#    ./start.sh               开发模式：后端(8010) + 前端 dev(5173) + 文档站 dev(5174) + 门户(40200)
#    ./start.sh --prod        生产模式：构建前端/文档站产物 + 后端托管(8010) + 文档站 preview(40183) + 门户(40200)
#    ./start.sh --backend     仅启动后端
#    ./start.sh --frontend    仅启动前端 dev
#    ./start.sh --no-docs     不启动独立文档网站
#    ./start.sh --no-portal   不启动门户网站
#    ./start.sh --no-portal-sync  不自动同步门户到线上官网 (https://www.nengyousuan.com)
#    ./start.sh --help        查看帮助
#
#  说明:
#    - 后端首次运行自动创建 .venv 并安装依赖
#    - 前端首次运行自动 npm install
#    - 日志写入 .logs/ 目录，Ctrl+C 停止全部服务
#    - 默认启动门户时会把 platform/homePage/ 同步到线上官网 43.161.194.75（免密 SSH），失败不阻断本地服务
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

MODE="dev"        # dev | prod
RUN_BACKEND=1
RUN_FRONTEND=1
RUN_DOCS=1
RUN_PORTAL=1
PORTAL_SYNC=1     # 启动门户时同步 platform/homePage 到线上官网 43.161.194.75

# 线上官网（https://www.nengyousuan.com）部署目标
PORTAL_SERVER="root@43.161.194.75"
PORTAL_REMOTE_DIR="/var/www/nengyousuan"

for arg in "$@"; do
  case "$arg" in
    --prod)     MODE="prod" ;;
    --backend)  RUN_FRONTEND=0 ;;
    --frontend) RUN_BACKEND=0 ;;
    --no-docs)  RUN_DOCS=0 ;;
    --no-portal) RUN_PORTAL=0 ;;
    --no-portal-sync) PORTAL_SYNC=0 ;;
    -h|--help)
      sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "❌ 未知参数: $arg（用 ./start.sh --help 查看用法）" >&2
      exit 1
      ;;
  esac
done

# ---- 停止上次残留的本项目服务（避免端口被旧进程占用导致新服务起不来/页面卡住）----
stop_old_services() {
  echo "==> [清理] 停止上次残留的本项目服务..."
  local stopped=0
  # 旧后端：uvicorn（--reload 的 reloader+worker 一并终止）与 run.sh 启动器
  pkill -f "uvicorn app\.main:app" 2>/dev/null && { echo "   - 已停止旧后端 (uvicorn)"; stopped=1; } || true
  pkill -f "config/run\.sh" 2>/dev/null && { echo "   - 已停止旧后端启动器 (run.sh)"; stopped=1; } || true
  # 旧前端 / 文档站 dev 服务器（vite dev 与 preview 共用 .bin/vite 入口）
  pkill -f "frontend/node_modules/\.bin/vite" 2>/dev/null && { echo "   - 已停止旧前端 dev (vite)"; stopped=1; } || true
  pkill -f "docs-site/node_modules/\.bin/vite" 2>/dev/null && { echo "   - 已停止旧文档站 dev (vite)"; stopped=1; } || true
  # 旧门户静态服务器
  pkill -f "http\.server 40200" 2>/dev/null && { echo "   - 已停止旧门户 (http.server)"; stopped=1; } || true
  # 旧的一键启动脚本（排除当前进程，避免自杀）
  for opid in $(pgrep -f "start\.sh" 2>/dev/null || true); do
    if [ "$opid" != "$$" ]; then
      kill "$opid" 2>/dev/null && { echo "   - 已停止旧启动脚本 (PID $opid)"; stopped=1; } || true
    fi
  done
  # 给被杀的进程留出退出时间，避免刚清理完又端口冲突
  if [ "$stopped" = "1" ]; then
    sleep 1
  fi
  return 0
}
stop_old_services

# ---- 生产模式：先构建前端产物，由后端 Catch-all 路由托管；文档站构建后用 vite preview 托管 ----
if [ "$MODE" = "prod" ]; then
  echo "==> [构建] 前端产物 (npx vite build)..."
  (cd "$ROOT/frontend" && npx vite build)
  if [ "$RUN_DOCS" = "1" ]; then
    echo "==> [构建] 文档网站产物 (docs-site: npx vite build)..."
    (cd "$ROOT/docs-site" && npx vite build)
  fi
  RUN_FRONTEND=0
fi

BACKEND_PID=""
FRONTEND_PID=""
DOCS_PID=""
PORTAL_PID=""

cleanup() {
  echo ""
  echo "==> 正在停止服务..."
  [ -n "$PORTAL_PID" ] && kill "$PORTAL_PID" 2>/dev/null || true
  [ -n "$DOCS_PID" ] && kill "$DOCS_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "==> 已全部停止"
  exit 0
}
trap cleanup INT TERM

# 轮询等待服务就绪
wait_ready() {
  local url="$1" name="$2" retries="${3:-90}"
  for _ in $(seq 1 "$retries"); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      echo "   ✔ $name 就绪"
      return 0
    fi
    sleep 1
  done
  echo "   ⚠ $name 等待超时，请查看日志: $LOG_DIR/" >&2
  return 1
}

# ---- 启动后端 ----
if [ "$RUN_BACKEND" = "1" ]; then
  echo "==> [后端] 启动 FastAPI (127.0.0.1:8010)..."
  bash "$ROOT/backend/config/run.sh" > "$LOG_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  echo "   PID: $BACKEND_PID    日志: $LOG_DIR/backend.log"
  wait_ready "http://127.0.0.1:8010/api/health" "后端" || true
fi

# ---- 启动前端 ----
if [ "$RUN_FRONTEND" = "1" ]; then
  echo "==> [前端] 启动 Vite dev (127.0.0.1:5173)..."
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    echo "   首次运行，安装前端依赖 (npm install)..."
    (cd "$ROOT/frontend" && npm install)
  fi
  (cd "$ROOT/frontend" && npm run dev) > "$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  echo "   PID: $FRONTEND_PID    日志: $LOG_DIR/frontend.log"
  wait_ready "http://127.0.0.1:5173" "前端" || true
fi

# ---- 启动独立文档网站（宣传手册/使用手册/技术文档） ----
if [ "$RUN_DOCS" = "1" ]; then
  if [ ! -d "$ROOT/docs-site/node_modules" ]; then
    echo "   首次运行，安装文档站依赖 (npm install)..."
    (cd "$ROOT/docs-site" && npm install)
  fi
  if [ "$MODE" = "prod" ]; then
    echo "==> [文档站] 启动静态托管 (127.0.0.1:40183)..."
    (cd "$ROOT/docs-site" && npx vite preview --port 40183 --host 127.0.0.1) > "$LOG_DIR/docs-site.log" 2>&1 &
  else
    echo "==> [文档站] 启动 Vite dev (127.0.0.1:5174)..."
    (cd "$ROOT/docs-site" && npm run dev) > "$LOG_DIR/docs-site.log" 2>&1 &
  fi
  DOCS_PID=$!
  echo "   PID: $DOCS_PID    日志: $LOG_DIR/docs-site.log"
  if [ "$MODE" = "prod" ]; then
    wait_ready "http://127.0.0.1:40183" "文档站" || true
  else
    wait_ready "http://127.0.0.1:5174" "文档站" || true
  fi
fi

# ---- 启动门户网站（平台门户静态站点 platform/homePage） ----
if [ "$RUN_PORTAL" = "1" ]; then
  echo "==> [门户] 启动静态网站 (127.0.0.1:40200)..."
  (cd "$ROOT/platform/homePage" && python3 -m http.server 40200 --bind 127.0.0.1) > "$LOG_DIR/portal.log" 2>&1 &
  PORTAL_PID=$!
  echo "   PID: $PORTAL_PID    日志: $LOG_DIR/portal.log"
  wait_ready "http://127.0.0.1:40200" "门户" || true
fi

# ---- 同步门户到线上官网（https://www.nengyousuan.com，43.161.194.75 + Nginx）----
# 每次启动都把最新 platform/homePage/ 推上线，失败仅警告、不阻断本地服务
if [ "$PORTAL_SYNC" = "1" ]; then
  echo "==> [门户] 同步 platform/homePage/ → 线上官网 $PORTAL_SERVER:$PORTAL_REMOTE_DIR ..."
  if rsync -az --delete \
      -e "ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=no -o BatchMode=yes" \
      --exclude='.DS_Store' --exclude='.serve.pid' --exclude='.serve.log' --exclude='*.log' \
      "$ROOT/platform/homePage/" "$PORTAL_SERVER:$PORTAL_REMOTE_DIR/"; then
    echo "   ✔ 线上官网已更新: https://www.nengyousuan.com"
  else
    echo "   ⚠ 官网同步失败（不影响本地服务，请检查网络与免密 SSH 配置）" >&2
  fi
fi

# ---- 输出访问地址 ----
echo ""
echo "=============================================="
echo "  ✅ 服务已启动"
if [ "$MODE" = "prod" ]; then
  echo "  访问: http://127.0.0.1:8010  (后端托管前端产物)"
  [ "$RUN_DOCS" = "1" ] && echo "  文档站: http://127.0.0.1:40183  (宣传手册/使用手册/技术文档)"
  [ "$RUN_PORTAL" = "1" ] && echo "  门户: http://127.0.0.1:40200  (平台门户网站)"
else
  echo "  前端: http://127.0.0.1:5173"
  echo "  后端: http://127.0.0.1:8010  (API / WebSocket)"
  [ "$RUN_DOCS" = "1" ] && echo "  文档站: http://127.0.0.1:5174  (宣传手册/使用手册/技术文档)"
  [ "$RUN_PORTAL" = "1" ] && echo "  门户: http://127.0.0.1:40200  (平台门户网站)"
fi
echo "  按 Ctrl+C 停止全部服务"
echo "=============================================="

while true; do sleep 1; done
