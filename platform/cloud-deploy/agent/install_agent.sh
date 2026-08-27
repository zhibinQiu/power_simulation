#!/bin/bash
# 能碳一体机云端 Agent 一键安装（在云端 K3s 主机上以 root 执行）
# 用途：以「MQTT 推送(读) + HTTP API(写)」替代「平台 SSH 到云端执行 kubectl」。
#
# 用法：
#   sudo bash install_agent.sh \
#     --broker-host 127.0.0.1 --broker-port 41883 \
#     --broker-user <可省略> --broker-pass <可省略> \
#     --token <平台侧配置的 agent_token，必填> \
#     --http-port 42083 \
#     --edge-host <边缘盒子 IP，可省略> --edge-port 22 --edge-user root \
#     --edge-pass <边缘 SSH 密码，可省略> --edge-key <边缘 SSH 私钥路径，可省略>
#
# 提示：若云端 mosquitto 未开启认证，--broker-user/--broker-pass 可省略。
#       edge 字段用于「重启边缘盒子 box-mapper 等」：密码与密钥二选一（密码需 sshpass）。
set -euo pipefail

INSTALL_DIR=/opt/cloud-agent
SERVICE_NAME=cloud-agent
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cloud_agent.py"

HTTP_PORT=42083
TOKEN=""
BROKER_HOST=127.0.0.1
BROKER_PORT=41883
BROKER_USER=""
BROKER_PASS=""
EDGE_HOST=""
EDGE_PORT=22
EDGE_USER="root"
EDGE_PASS=""
EDGE_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --http-port) HTTP_PORT="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --broker-host) BROKER_HOST="$2"; shift 2 ;;
    --broker-port) BROKER_PORT="$2"; shift 2 ;;
    --broker-user) BROKER_USER="$2"; shift 2 ;;
    --broker-pass) BROKER_PASS="$2"; shift 2 ;;
    --edge-host) EDGE_HOST="$2"; shift 2 ;;
    --edge-port) EDGE_PORT="$2"; shift 2 ;;
    --edge-user) EDGE_USER="$2"; shift 2 ;;
    --edge-pass) EDGE_PASS="$2"; shift 2 ;;
    --edge-key) EDGE_KEY="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

if [[ -z "$TOKEN" ]]; then
  echo "错误：--token 必填（与平台「总览 → 配置」里的 agent_token 保持一致）" >&2
  exit 1
fi

echo "==> 1/4 检查依赖（kubectl / openssl / ss / mosquitto_pub）"
for bin in kubectl openssl ss mosquitto_pub; do
  command -v "$bin" >/dev/null 2>&1 || { echo "错误：缺少命令 $bin（cloud-agent 依赖系统命令，避免装 pip 包）" >&2; exit 1; }
done

echo "==> 2/4 写入配置 $INSTALL_DIR/config.json"
mkdir -p "$INSTALL_DIR"
cat > "$INSTALL_DIR/config.json" <<EOF
{
  "http_port": $HTTP_PORT,
  "token": "$TOKEN",
  "broker_host": "$BROKER_HOST",
  "broker_port": $BROKER_PORT,
  "broker_username": "$BROKER_USER",
  "broker_password": "$BROKER_PASS",
  "intervals": {"state": 30, "crds": 5, "logs": 3},
  "edge": {
    "host": "$EDGE_HOST",
    "port": $EDGE_PORT,
    "user": "$EDGE_USER",
    "password": "$EDGE_PASS",
    "key": "$EDGE_KEY"
  }
}
EOF
# 兼容旧版 agent：备份旧配置时若没有 edge 字段则自动补齐（下次重启 agent 生效）
if [ -z "$EDGE_HOST" ]; then
  echo "   （未配置 --edge-host，重启边缘盒子服务能力暂不可用；可后续编辑 $INSTALL_DIR/config.json 的 edge 字段）"
fi

echo "==> 3/4 安装主程序 + systemd 单元"
install -m 0755 "$SRC" "$INSTALL_DIR/cloud_agent.py"
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=能碳一体机云端 Agent（MQTT 推送 + HTTP API，替代 SSH 数据通道）
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/cloud_agent.py
Restart=always
RestartSec=3
# 若用非 root 用户，去掉下面注释并放开 kubectl 权限
# User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "==> 4/4 启动并设置开机自启"
systemctl daemon-reload
systemctl enable --now $SERVICE_NAME
sleep 1
systemctl --no-pager --lines=20 status $SERVICE_NAME || true

echo ""
echo "✅ cloud-agent 安装完成"
echo "   - HTTP API : http://0.0.0.0:$HTTP_PORT（Bearer token 认证）"
echo "   - MQTT 推送 : cloud/state(30s) cloud/crds(5s) cloud/logs(3s) → $BROKER_HOST:$BROKER_PORT"
echo "   - 日志查看 : journalctl -u $SERVICE_NAME -f"
echo ""
echo "   ⚠ 若云端口未放行，请执行："
echo "     sudo firewall-cmd --permanent --add-port=$HTTP_PORT/tcp && sudo firewall-cmd --reload"
echo "     （或云安全组放行 TCP $HTTP_PORT）"
echo ""
echo "   ⚠ 平台侧需在「能碳一体机管理 → 总览 → 配置」填写："
echo "     云端地址 / agent端口=$HTTP_PORT / agent_token=$TOKEN"
echo ""
if [ -n "$EDGE_HOST" ]; then
  echo "   ✅ 边缘盒子已配置（$EDGE_USER@$EDGE_HOST:$EDGE_PORT），可在平台一键重启 box-mapper 等边缘服务"
else
  echo "   ⚠ 未配置边缘盒子（--edge-host），平台「重启 Mapper」将提示配置；"
  echo "     需支持时编辑 $INSTALL_DIR/config.json 的 edge 字段（密码方式需 yum install -y sshpass）"
fi
