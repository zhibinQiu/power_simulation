#!/usr/bin/env bash
# 平台门户网站独立静态服务
# 用法: ./serve.sh {start|stop|status|restart}
# 端口: 40200 (全局端口规范 40000+)
set -euo pipefail

PORT=40200
HOST=0.0.0.0
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$DIR/.serve.pid"
LOGFILE="$DIR/.serve.log"

start() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "门户服务已在运行 (pid $(cat "$PIDFILE"), 端口 $PORT)"
    return 0
  fi
  nohup python3 -m http.server "$PORT" --bind "$HOST" --directory "$DIR" \
    >"$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  sleep 1
  if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "门户服务已启动: http://127.0.0.1:$PORT  (pid $(cat "$PIDFILE"))"
  else
    echo "启动失败, 日志: $LOGFILE" >&2
    exit 1
  fi
}

stop() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")"
    rm -f "$PIDFILE"
    echo "门户服务已停止"
  else
    rm -f "$PIDFILE"
    echo "门户服务未在运行"
  fi
}

status() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "运行中: pid $(cat "$PIDFILE"), 端口 $PORT"
    curl -s -o /dev/null -w "HTTP 状态: %{http_code}\n" "http://127.0.0.1:$PORT/" || true
  else
    echo "未运行"
  fi
}

case "${1:-start}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *)       echo "用法: $0 {start|stop|status|restart}" >&2; exit 1 ;;
esac
