#!/usr/bin/env bash
# ============================================================================
# 能碳数据中间件 · 部署/更新脚本（cloud-deploy/middleware）
#
# 三种模式：
#   1) 开发机 → 服务器（首次或全量）：
#        bash deploy_middleware.sh --server root@36.151.146.71
#      （rsync 源码到服务器 → 远端执行本地安装 → venv 依赖 → systemd 常驻）
#   2) 服务器本地安装（源码已就位，脚本随源码 rsync 到服务器）：
#        sudo bash deploy_middleware.sh --local-only
#   3) 日常只更新代码（配合 platform/update.sh middleware）：
#        bash deploy_middleware.sh sync --server root@36.151.146.71
#
# 约定：
#   - 安装目录 /opt/nengtan-middleware，源码落在其中的 middleware/ 子目录
#     （runner.py 需要父级可直接 import middleware 包，故保持「仓库子目录包式」布局）；
#   - venv 在 /opt/nengtan-middleware/.venv（只装 requirements.txt 依赖）；
#   - 服务名 nengtan-middleware，管理 API 默认 42084；
#   - 已存在的 config.json 默认保留（平台注册的数据源在里头），除非 --reset-config。
#
# 端口规范：服务端口一律 40000+（管理 API 42084 / 数据直发云端 Broker 41883）。
# ============================================================================
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/nengtan-middleware"
MW_DIR="${INSTALL_DIR}/middleware"
VENV_DIR="${INSTALL_DIR}/.venv"
SERVICE_NAME="nengtan-middleware"
API_PORT="42084"
BROKER_HOST="127.0.0.1"
BROKER_PORT="41883"
SERVER=""
MODE="deploy"
RESET_CONFIG="no"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; MW_DIR="${INSTALL_DIR}/middleware"; VENV_DIR="${INSTALL_DIR}/.venv"; shift 2 ;;
    --api-port) API_PORT="$2"; shift 2 ;;
    --broker-host) BROKER_HOST="$2"; shift 2 ;;
    --broker-port) BROKER_PORT="$2"; shift 2 ;;
    --reset-config) RESET_CONFIG="yes"; shift 1 ;;
    --local-only) MODE="local"; shift 1 ;;
    sync) MODE="sync"; shift 1 ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "未知参数: $1（--help 查看用法）" >&2; exit 2 ;;
  esac
done

rsync_src() {
  # 同步源码（排除缓存与运行时产物）
  rsync -az --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
    --exclude '*.log' --exclude '*.pid' \
    -e ssh "${SRC_DIR}/" "$1"
}

# ---------------------------------------------------------------- 模式 3：同步
if [[ "$MODE" == "sync" ]]; then
  [[ -n "$SERVER" ]] || { echo "sync 模式需 --server <user@host>" >&2; exit 2; }
  echo "==> [1/2] rsync 中间件源码 → ${SERVER}:${MW_DIR}"
  ssh "$SERVER" "mkdir -p ${MW_DIR}"
  rsync_src "${SERVER}:${MW_DIR}/"
  echo "==> [2/2] 重启服务（systemd Restart=always，配置未变则仅重载代码）"
  ssh "$SERVER" "systemctl restart ${SERVICE_NAME} && sleep 3 && systemctl is-active ${SERVICE_NAME} \
    && curl -s -m 5 http://127.0.0.1:${API_PORT}/api/health | head -c 200"
  echo
  echo "==> 完成。中间件管理 API：http://${SERVER#*@}:${API_PORT}"
  exit 0
fi

# ------------------------------------------------------- 模式 1：开发机 → 服务器
if [[ "$MODE" == "deploy" ]]; then
  [[ -n "$SERVER" ]] || { echo "部署模式需 --server <user@host>（服务器本地安装用 --local-only）" >&2; exit 2; }
  echo "==> [1/2] rsync 源码 → ${SERVER}:${MW_DIR}"
  ssh "$SERVER" "mkdir -p ${MW_DIR}"
  rsync_src "${SERVER}:${MW_DIR}/"
  echo "==> [2/2] 远端执行本地安装"
  ssh -t "$SERVER" "bash ${MW_DIR}/deploy_middleware.sh --local-only \
    --dir ${INSTALL_DIR} --api-port ${API_PORT} \
    --broker-host ${BROKER_HOST} --broker-port ${BROKER_PORT} \
    $([[ "$RESET_CONFIG" == "yes" ]] && echo --reset-config)"
  exit 0
fi

# ------------------------------------------------------ 模式 2：服务器本地安装
echo "==> 1/5 检查依赖（python3 / systemctl）"
command -v python3 >/dev/null 2>&1 || { echo "错误：缺少 python3" >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo "错误：缺少 systemd" >&2; exit 1; }

echo "==> 2/5 安装源码到 ${MW_DIR}"
mkdir -p "${MW_DIR}"
if [[ "${SRC_DIR}" != "${MW_DIR}" ]]; then
  rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
    --exclude '*.log' --exclude '*.pid' \
    "${SRC_DIR}/" "${MW_DIR}/"
fi
if [[ ! -f "${MW_DIR}/config.json" || "$RESET_CONFIG" == "yes" ]]; then
  cp "${MW_DIR}/config.json" "${MW_DIR}/config.json.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
  echo "    使用仓库默认 config.json（external 形态：直发 ${BROKER_HOST}:${BROKER_PORT}）"
else
  echo "    保留已有 config.json（平台注册的数据源在里头；--reset-config 可覆盖）"
fi

echo "==> 3/5 准备 Python 虚拟环境"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install -q -U pip
"${VENV_DIR}/bin/pip" install -q -r "${MW_DIR}/requirements.txt"
"${VENV_DIR}/bin/python" -c 'import paho.mqtt; print("    依赖就绪：paho-mqtt")'

echo "==> 4/5 写入 systemd 单元 ${SERVICE_NAME}.service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=NengTan Data Middleware (external output -> cloud broker ${BROKER_PORT})
After=network.target

[Service]
Type=simple
WorkingDirectory=${MW_DIR}
ExecStart=${VENV_DIR}/bin/python ${MW_DIR}/runner.py --config ${MW_DIR}/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}" >/dev/null

echo "==> 5/5 健康检查"
sleep 3
systemctl is-active "${SERVICE_NAME}"
curl -s -m 5 "http://127.0.0.1:${API_PORT}/api/health" | head -c 300
echo
echo "==> 完成。运维：journalctl -u ${SERVICE_NAME} -f"
echo "    提醒：管理 API ${API_PORT} 需服务器防火墙放行（UFW：ufw allow ${API_PORT}/tcp）"
