#!/usr/bin/env bash
# 能碳数据中间件启动/停止/自检
#   ./run.sh check          # 自检配置（不采集、不连外部 Broker）
#   ./run.sh start           # 后台启动（日志 middleware.log）
#   ./run.sh stop            # 停止
#   ./run.sh logs            # 跟随日志
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PY="python3"
CONFIG="${MW_CONFIG:-config.json}"
LOG="middleware.log"
PIDFILE="middleware.pid"

if [ -d .venv ]; then PY=".venv/bin/python"; fi

case "${1:-run}" in
  check)
    exec "$PY" "$ROOT/runner.py" --config "$ROOT/$CONFIG" --check
    ;;
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "已在运行 pid=$(cat "$PIDFILE")"; exit 0
    fi
    nohup "$PY" "$ROOT/runner.py" --config "$ROOT/$CONFIG" >> "$ROOT/$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "已启动 pid=$(cat "$PIDFILE")，日志 $LOG"
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "已发送停止信号"
    else
      echo "未在运行"; exit 1
    fi
    ;;
  logs)
    exec tail -f "$ROOT/$LOG"
    ;;
  *)
    exec "$PY" "$ROOT/runner.py" --config "$ROOT/$CONFIG"
    ;;
esac
