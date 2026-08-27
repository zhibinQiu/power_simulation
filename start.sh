#!/usr/bin/env bash
# ============================================================
#  一键启动脚本：工业能碳智控平台
#
#  用法:
#    ./start.sh               开发模式：后端(8010) + 前端 dev(5173)
#    ./start.sh --prod        生产模式：构建前端产物 + 后端托管(8010)
#    ./start.sh --backend     仅启动后端
#    ./start.sh --frontend    仅启动前端 dev
#    ./start.sh --help        查看帮助
#
#  说明:
#    - 后端首次运行自动创建 .venv 并安装依赖
#    - 前端首次运行自动 npm install
#    - 日志写入 .logs/ 目录，Ctrl+C 停止全部服务
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

MODE="dev"        # dev | prod
RUN_BACKEND=1
RUN_FRONTEND=1

for arg in "$@"; do
  case "$arg" in
    --prod)     MODE="prod" ;;
    --backend)  RUN_FRONTEND=0 ;;
    --frontend) RUN_BACKEND=0 ;;
    -h|--help)
      sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "❌ 未知参数: $arg（用 ./start.sh --help 查看用法）" >&2
      exit 1
      ;;
  esac
done

# ---- 生产模式：先构建前端产物，由后端 Catch-all 路由托管 ----
if [ "$MODE" = "prod" ]; then
  echo "==> [构建] 前端产物 (npx vite build)..."
  (cd "$ROOT/frontend" && npx vite build)
  RUN_FRONTEND=0
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "==> 正在停止服务..."
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

# ---- 输出访问地址 ----
echo ""
echo "=============================================="
echo "  ✅ 服务已启动"
if [ "$MODE" = "prod" ]; then
  echo "  访问: http://127.0.0.1:8010  (后端托管前端产物)"
else
  echo "  前端: http://127.0.0.1:5173"
  echo "  后端: http://127.0.0.1:8010  (API / WebSocket)"
fi
echo "  按 Ctrl+C 停止全部服务"
echo "=============================================="

while true; do sleep 1; done
