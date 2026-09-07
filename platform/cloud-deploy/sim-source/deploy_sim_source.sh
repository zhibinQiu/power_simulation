#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 独立模拟数据源服务 启停脚本（cloud-deploy/sim-source）
#
# 定位：模拟数据由**独立进程**提供（平台与中间件自身都不产生模拟数据）。
#       默认在**开发机**本地启动（数据经开发机中间件转换后并入服务器云端 Broker），
#       服务器侧通常不需要跑本服务（需要时可用 --server 部署为 systemd 常驻）。
#
# 用法（开发机，默认）：
#   bash deploy_sim_source.sh start      # 后台启动（sim-source 自带 Broker 127.0.0.1:41885）
#   bash deploy_sim_source.sh stop       # 停止
#   bash deploy_sim_source.sh restart    # 重启
#   bash deploy_sim_source.sh status     # 运行状态 + 最近日志
#   bash deploy_sim_source.sh logs       # 跟随日志
#   bash deploy_sim_source.sh check      # 自检：打印数据源清单后退出
#
# 部署到服务器（可选）：
#   bash deploy_sim_source.sh --server root@36.151.146.71 deploy    # 安装为 systemd 服务
#   bash deploy_sim_source.sh --server root@36.151.146.71 status
#   bash deploy_sim_source.sh --server root@36.151.146.71 remove
#
# 其它参数：
#   --config <文件>   指定配置文件（默认脚本同目录 config.json）
#   --port <端口>     覆盖自带 Broker 端口（默认 41885）
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${DIR}/sim_source.py"
CONFIG="${DIR}/config.json"
PORT=""
SERVER=""
CMD=""
LOG_FILE="/tmp/nengtan-sim-source.log"
PID_FILE="/tmp/nengtan-sim-source.pid"
INSTALL_DIR="/opt/nengtan-sim-source"
SERVICE_NAME="nengtan-sim-source"
PY="python3"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    start|stop|restart|status|logs|check|deploy|remove) [[ -z "$CMD" ]] && CMD="$1"; shift 1 ;;
    *) echo "未知参数: $1（-h 查看用法）" >&2; exit 2 ;;
  esac
done
CMD="${CMD:-status}"

# ----------------------------------------------------------- 远程（服务器）模式
if [[ -n "$SERVER" ]]; then
  case "$CMD" in
    deploy)
      echo "==> 部署模拟数据源到 ${SERVER}:${INSTALL_DIR}（systemd: ${SERVICE_NAME}）"
      ssh "$SERVER" "mkdir -p ${INSTALL_DIR}"
      rsync -az --exclude '__pycache__' --exclude '*.pid' --exclude '*.log' \
        -e ssh "${DIR}/" "${SERVER}:${INSTALL_DIR}/"
      ssh "$SERVER" "cp ${INSTALL_DIR}/systemd/${SERVICE_NAME}.service /etc/systemd/system/ \
        && systemctl daemon-reload && systemctl enable --now ${SERVICE_NAME} \
        && sleep 2 && systemctl is-active ${SERVICE_NAME}"
      echo "==> 完成。日志：ssh ${SERVER} journalctl -u ${SERVICE_NAME} -f"
      exit 0
      ;;
    remove)
      ssh "$SERVER" "systemctl disable --now ${SERVICE_NAME} >/dev/null 2>&1 || true; \
        rm -f /etc/systemd/system/${SERVICE_NAME}.service; systemctl daemon-reload; \
        rm -rf ${INSTALL_DIR}; echo 已移除"
      exit 0
      ;;
    status|stop|restart|start)
      ssh "$SERVER" "systemctl ${CMD} ${SERVICE_NAME}" 2>&1 | tail -5
      [[ "$CMD" == "status" ]] && ssh "$SERVER" "journalctl -u ${SERVICE_NAME} --no-pager -n 5" || true
      exit 0
      ;;
    *) echo "服务器模式不支持命令：${CMD}" >&2; exit 2 ;;
  esac
fi

# ------------------------------------------------------------- 本地（开发机）模式
port_arg=""
[[ -n "$PORT" ]] && port_arg="--port ${PORT}"

case "$CMD" in
  check)
    exec "$PY" "$SCRIPT" --config "$CONFIG" --check
    ;;
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "已在运行 pid=$(cat "$PID_FILE")（日志 ${LOG_FILE}）"; exit 0
    fi
    nohup "$PY" "$SCRIPT" --config "$CONFIG" $port_arg >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "已启动 pid=$(cat "$PID_FILE")，自带 Broker 端口 ${PORT:-41885}"
      echo "日志：tail -f ${LOG_FILE}"
    else
      echo "启动失败，查看日志：${LOG_FILE}" >&2; rm -f "$PID_FILE"; exit 1
    fi
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "已停止"
    else
      echo "未在运行"; exit 0
    fi
    ;;
  restart)
    bash "${BASH_SOURCE[0]}" stop --config "$CONFIG" || true
    bash "${BASH_SOURCE[0]}" start --config "$CONFIG" $port_arg
    ;;
  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "运行中 pid=$(cat "$PID_FILE")"
    else
      echo "未运行（启动：bash deploy_sim_source.sh start）"
    fi
    [[ -f "$LOG_FILE" ]] && { echo "--- 最近日志 ---"; tail -8 "$LOG_FILE"; }
    ;;
  logs)
    exec tail -f "$LOG_FILE"
    ;;
  *)
    echo "未知命令：${CMD}" >&2; exit 2 ;;
esac
