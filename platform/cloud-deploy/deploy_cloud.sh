#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 云端一键部署脚本 (deploy_cloud.sh)
#
# 对应 box-deploy（边缘盒子部署包）的云端侧部署包。不含平台本身
# （能碳平台 web 应用 / kubeedge-status 管理台，见 README 第 6 章）。
#
# 部署内容:
#   1. KubeEdge 云端控制面 (cloudcore v1.20.0 + Device CRD v1beta1 + 防火墙 10001-10004)
#   2. 能碳数据面 (nengtan-cloud-{broker,dashboard,collector}, MQTT 41883/WS 41083/仪表盘 41500)
#   3. 云端 agent (cloud-agent, MQTT 推送读 + HTTP 42083 写, 替代平台 SSH 数据通道)
#
# 用法:
#   ./deploy_cloud.sh                     # 完整部署: 控制面 + 数据面 + agent
#   ./deploy_cloud.sh --control-only      # 仅 KubeEdge 控制面
#   ./deploy_cloud.sh --datapath-only     # 仅数据面 (+ agent)
#   ./deploy_cloud.sh --agent-only        # 仅云端 agent (需数据面 broker 已就绪)
#   ./deploy_cloud.sh --check             # 链路自检 (不修改任何东西)
#
# 环境变量:
#   CLOUD_IP         云端对外 IP (默认 172.19.134.45, 边缘盒子要能路由到)
#   KUBEEDGE_VERSION KubeEdge 版本 (默认 v1.20.0, 兼容 k3s ≤ 1.30)
#   DATA_DIR         数据面部署路径 (默认 /root/qzb/jianpai/data-terminal)
#   DATAPATH_SRC     参考工程源码目录 (可选, 优先复制覆盖本包自带数据面实现)
#   AGENT_TOKEN      云端 agent_token (可选, 默认复用已有/自动生成并打印)
#
# 特性:
#   * 幂等: 重复执行安全, 已存在的证书/服务/CRD 不会重复创建
#   * 自检: --check 不修改任何东西, 逐项核对云端链路
#   * 控制面按 kubeedge-console-ops.md 2.x 成功路径实现 (CA 必须是 EC P-256!)
# ============================================================================
set -euo pipefail

# ----------------------------- 常量 --------------------------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBEEDGE_DIR="$SELF_DIR/kubeedge"
DATAPATH_DIR="$SELF_DIR/datapath"
SYSTEMD_SRC="$DATAPATH_DIR/systemd"
AGENT_DIR="$SELF_DIR/agent"

CLOUD_IP="${CLOUD_IP:-172.19.134.45}"
KUBEEDGE_VERSION="${KUBEEDGE_VERSION:-v1.20.0}"
DATA_DIR="${DATA_DIR:-/root/qzb/jianpai/data-terminal}"
DATAPATH_SRC="${DATAPATH_SRC:-}"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-/etc/rancher/k3s/k3s.yaml}"

[ "$(id -u)" -ne 0 ] && { echo "[error] 请以 root 运行 (云端需操作 /etc/kubeedge 与 systemd)"; exit 1; }

log()  { echo -e "\033[32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ----------------------------- 参数 --------------------------------------
DO_CONTROL=1; DO_DATAPATH=1; DO_AGENT=1; DO_CHECK=0
for a in "$@"; do
  case "$a" in
    --control-only)   DO_DATAPATH=0; DO_AGENT=0 ;;   # 无数据面 broker, agent 无法推送
    --datapath-only)  DO_CONTROL=0 ;;
    --agent-only)     DO_CONTROL=0; DO_DATAPATH=0 ;;
    --check)          DO_CONTROL=0; DO_DATAPATH=0; DO_AGENT=0; DO_CHECK=1 ;;
    *) err "未知参数: $a" ;;
  esac
done

# ----------------------------- 0. 前置检查 -------------------------------
check_prereq() {
  log "前置检查: kubectl / k3s / root ..."
  command -v kubectl >/dev/null 2>&1 || err "未找到 kubectl (请先安装 k3s)"
  command -v openssl >/dev/null 2>&1 || err "未找到 openssl"
  command -v python3 >/dev/null 2>&1 || warn "未找到 python3 (数据面需要, 请安装)"
  if command -v k3s >/dev/null 2>&1; then
    K3S_VER="$(k3s -v 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+' | head -1 || echo '')"
    log "k3s 版本: ${K3S_VER:-未知} (cloudcore $KUBEEDGE_VERSION 兼容 k8s ≤ 1.30)"
    case "${K3S_VER#v}" in
      1.3[01].*|1.[4-9][0-9].*)
        warn "k3s ${K3S_VER} 可能超出 cloudcore $KUBEEDGE_VERSION 兼容范围, 见手册 2.1 坑 C7" ;;
    esac
  fi
  kubectl version --client >/dev/null 2>&1 || warn "kubectl 无法访问集群 (k3s 未就绪?)"
}

# ----------------------------- 1. CA + 证书 -------------------------------
gen_certs() {
  log "生成 CA 与证书 (EC P-256, 预置 /etc/kubeedge) ..."
  if [ -f /etc/kubeedge/ca/rootCA.key ] && [ -f /etc/kubeedge/certs/server.crt ]; then
    log "证书已存在, 跳过 (如需重签: kubeedge/gen_certs.sh --force $CLOUD_IP)"
    return
  fi
  "$KUBEEDGE_DIR/gen_certs.sh" "$CLOUD_IP"
  log "证书就绪: /etc/kubeedge/ca/rootCA.{crt,key} + /etc/kubeedge/certs/server.{crt,key}"
}

# ----------------------------- 2. cloudcore manifest ----------------------
apply_cloudcore() {
  log "应用 cloudcore manifest (cloudcore:$KUBEEDGE_VERSION, IP=$CLOUD_IP) ..."
  if kubectl -n kubeedge get deploy cloudcore >/dev/null 2>&1; then
    log "cloudcore Deployment 已存在, 跳过 apply (如需改 IP/配置: 重新 apply 后 rollout restart)"
    return
  fi
  sed "s/{{CLOUD_IP}}/$CLOUD_IP/g" "$KUBEEDGE_DIR/cloudcore-all.yaml" | kubectl apply -f - \
    || err "cloudcore manifest apply 失败"
  log "等待 cloudcore pod Running ..."
  kubectl -n kubeedge rollout status deploy/cloudcore --timeout=120s \
    || warn "pod 未就绪, 排查: kubectl -n kubeedge get pods && kubectl -n kubeedge logs deploy/cloudcore"
  sleep 3
  ss -tln 2>/dev/null | grep -qE ':(10002|10004)\b' \
    && log "cloudhub 已监听 10002/10004 ✓" \
    || warn "10002/10004 未监听, 检查证书(EC!)与防火墙, 见手册 2.9 坑 C1/C3"
}

# ----------------------------- 3. Device CRD (v1beta1) --------------------
apply_crd() {
  log "检查 Device CRD v1beta1 ..."
  if kubectl get crd devices.devices.kubeedge.io >/dev/null 2>&1 \
     && kubectl get crd devices.devices.kubeedge.io -o jsonpath='{.spec.versions[*].name}' 2>/dev/null | grep -q v1beta1; then
    log "Device CRD 已含 v1beta1, 跳过"
    return
  fi
  log "下载并应用 devices_v1beta1.yaml ($KUBEEDGE_VERSION) ..."
  if curl -fsSL "https://github.com/kubeedge/kubeedge/releases/download/$KUBEEDGE_VERSION/devices_v1beta1.yaml" -o /tmp/devices_v1beta1.yaml; then
    kubectl apply -f /tmp/devices_v1beta1.yaml || warn "CRD apply 失败, 检查网络/版本"
    rm -f /tmp/devices_v1beta1.yaml
  else
    warn "下载失败 (云端无外网?), 请手工: kubectl apply -f <devices_v1beta1.yaml>"
  fi
}

# ----------------------------- 4. 防火墙 ----------------------------------
open_firewall() {
  local ports=("$@")
  for p in "${ports[@]}"; do
    if command -v firewall-cmd >/dev/null 2>&1; then
      firewall-cmd --permanent --add-port="$p" >/dev/null 2>&1 || true
    else
      iptables -I INPUT -p tcp --dport "${p%/*}" -j ACCEPT 2>/dev/null || true
    fi
  done
  if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --reload >/dev/null 2>&1 || true
  fi
}

open_control_firewall() {
  # 注意: 10001-10004 为 KubeEdge 官方保留端口 (CloudHub quic/https/cloudStream/websocket),
  # 非项目服务端口, 按全局端口规范例外保留, 不可迁移; 项目自身服务一律使用 40000+
  log "放行控制面端口 10001-10004/tcp ..."
  open_firewall 10001/tcp 10002/tcp 10003/tcp 10004/tcp
}

# ----------------------------- 5. 数据面 ----------------------------------
deploy_datapath() {
  log "部署数据面到 $DATA_DIR ..."
  mkdir -p "$DATA_DIR"

  # 源码: 优先参考工程 (DATAPATH_SRC), 否则用本包自带实现
  if [ -n "$DATAPATH_SRC" ] && [ -d "$DATAPATH_SRC" ]; then
    log "从参考工程复制数据面源码: $DATAPATH_SRC"
    cp -f "$DATAPATH_SRC"/*.py "$DATA_DIR/" 2>/dev/null || true
    [ -f "$DATAPATH_SRC/requirements.txt" ] && cp -f "$DATAPATH_SRC/requirements.txt" "$DATA_DIR/"
  else
    cp -f "$DATAPATH_DIR"/broker.py "$DATAPATH_DIR"/collector.py "$DATAPATH_DIR"/dashboard.py "$DATA_DIR/"
    cp -f "$DATAPATH_DIR"/requirements.txt "$DATA_DIR/"
  fi

  # venv + 依赖 (幂等)
  if [ ! -x "$DATA_DIR/venv/bin/python" ]; then
    log "创建 venv 并安装依赖 ..."
    python3 -m venv "$DATA_DIR/venv" || err "venv 创建失败"
    "$DATA_DIR/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
    "$DATA_DIR/venv/bin/pip" install -r "$DATA_DIR/requirements.txt" || {
      warn "在线安装失败, 尝试离线/镜像: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r ..."
      "$DATA_DIR/venv/bin/pip" install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$DATA_DIR/requirements.txt" || err "依赖安装失败"
    }
  else
    log "venv 已存在, 跳过依赖安装"
  fi

  # systemd 单元 (渲染占位符后幂等覆盖)
  for svc in nengtan-cloud-broker nengtan-cloud-dashboard nengtan-collector; do
    sed -e "s|__DATA_DIR__|$DATA_DIR|g" -e "s|__VENV__|$DATA_DIR/venv|g" \
      "$SYSTEMD_SRC/$svc.service" > "/etc/systemd/system/$svc.service"
  done
  systemctl daemon-reload
  for svc in nengtan-cloud-broker nengtan-cloud-dashboard nengtan-collector; do
    systemctl enable "$svc" >/dev/null 2>&1 || true
    systemctl restart "$svc" || warn "systemd 启动失败: journalctl -u $svc"
  done

  log "放行数据面端口 41883/41083/41500 ..."
  open_firewall 41883/tcp 41083/tcp 41500/tcp

  sleep 2
  ss -tln 2>/dev/null | grep -q ':41883' \
    && log "MQTT Broker 监听 41883 ✓" \
    || warn "41883 未监听, 排查: journalctl -u nengtan-cloud-broker -n 30"
}

# ----------------------------- 6. 云端 agent ------------------------------
deploy_agent() {
  log "部署云端 agent (cloud-agent: MQTT 推送读 + HTTP 42083 写, 替代平台 SSH 数据通道) ..."
  local token="${AGENT_TOKEN:-}"
  # 幂等: 已安装且 config.json 有 token 时复用, 否则新生成 (打印给平台侧填写)
  if [ -z "$token" ] && [ -f /opt/cloud-agent/config.json ]; then
    token="$(python3 -c 'import json;print(json.load(open("/opt/cloud-agent/config.json")).get("token",""))' 2>/dev/null || true)"
    [ -n "$token" ] && log "复用已有 agent_token (见 /opt/cloud-agent/config.json)"
  fi
  [ -z "$token" ] && token="$(openssl rand -hex 24)" && log "已生成新 agent_token"
  # 边缘盒子配置（可选，用于平台一键重启 box-mapper）：EDGE_HOST=IP EDGE_USER=root EDGE_PASS=xxx EDGE_KEY=xxx
  local edge_args=""
  [ -n "${EDGE_HOST:-}" ] && edge_args+=" --edge-host $EDGE_HOST --edge-port ${EDGE_PORT:-22} --edge-user ${EDGE_USER:-root}"
  [ -n "${EDGE_PASS:-}" ] && edge_args+=" --edge-pass $EDGE_PASS"
  [ -n "${EDGE_KEY:-}" ] && edge_args+=" --edge-key $EDGE_KEY"
  bash "$AGENT_DIR/install_agent.sh" --token "$token" \
    --broker-host 127.0.0.1 --broker-port 41883 --http-port 42083 $edge_args \
    || err "agent 安装失败"
  open_firewall 42083/tcp
  log "agent_token（平台侧「云端 Broker 配置 → 云端 Agent → Agent Token」需填写）: $token"
  log "自检: curl -s -H 'Authorization: Bearer $token' http://127.0.0.1:42083/api/health"
  systemctl is-active cloud-agent >/dev/null 2>&1 \
    && log "cloud-agent 运行中 ✓" \
    || warn "cloud-agent 未运行, 排查: journalctl -u cloud-agent -n 30"
}

# ----------------------------- 7. 链路自检 --------------------------------
do_check() {
  echo "================ 云端链路自检 ================"
  echo "--- 1. 控制面 ---"
  command -v kubectl >/dev/null 2>&1 && {
    kubectl -n kubeedge get pods 2>/dev/null | grep -q 'cloudcore' \
      && kubectl -n kubeedge get pods --no-headers 2>/dev/null | awk '/cloudcore/{print "  cloudcore pod : " $3 " " $2}' \
      || echo "  cloudcore pod : 缺失 (未部署或未 Running)"
    CRD_VERSIONS="$(kubectl get crd devices.devices.kubeedge.io -o jsonpath='{.spec.versions[*].name}' 2>/dev/null || true)"
    if [ -n "$CRD_VERSIONS" ]; then
      echo "  Device CRD v1beta1: $CRD_VERSIONS"
    else
      echo "  Device CRD  : 缺失"
    fi
  } || echo "  kubectl      : 缺失"
  echo "--- 2. CloudHub 端口 (hostNetwork) ---"
  for p in 10001 10002 10003 10004; do
    ss -tln 2>/dev/null | grep -q ":$p\b" && echo "  $p : OK" || echo "  $p : 未监听"
  done
  echo "--- 3. 证书 (EC P-256 校验) ---"
  [ -f /etc/kubeedge/ca/rootCA.key ] && openssl ec -in /etc/kubeedge/ca/rootCA.key -noout 2>/dev/null \
    && echo "  rootCA.key   : OK (EC)" || echo "  rootCA.key   : 缺失或非 EC (必须 EC P-256!)"
  [ -f /etc/kubeedge/certs/server.crt ] && echo "  server.crt   : OK" || echo "  server.crt   : 缺失"
  echo "--- 4. 数据面 ---"
  for svc in nengtan-cloud-broker nengtan-cloud-dashboard nengtan-collector; do
    systemctl is-active "$svc" >/dev/null 2>&1 \
      && echo "  $svc : ACTIVE" || echo "  $svc : inactive"
  done
  for p in 41883 41083 41500; do
    ss -tln 2>/dev/null | grep -q ":$p\b" && echo "  端口 $p   : OK" || echo "  端口 $p   : 未监听"
  done
  echo "--- 5. token (24h, 管理台可重签 1 年) ---"
  if TOKEN="$(kubectl -n kubeedge get secret tokensecret -o jsonpath='{.data.tokendata}' 2>/dev/null)"; then
    echo "  tokensecret  : $(echo "$TOKEN" | base64 -d | head -c 24)..."
  else
    echo "  tokensecret  : 暂无 (cloudcore 首次启动自动生成)"
  fi
  echo "--- 6. 数据面最近落盘 ---"
  ls -t "$DATA_DIR"/collected/*.log 2>/dev/null | head -1 && tail -n 2 "$(ls -t "$DATA_DIR"/collected/*.log 2>/dev/null | head -1)" 2>/dev/null \
    || echo "  (无落盘数据)"
  echo "--- 7. 云端 agent ---"
  systemctl is-active cloud-agent >/dev/null 2>&1 \
    && echo "  cloud-agent  : ACTIVE" || echo "  cloud-agent  : inactive"
  if ss -tln 2>/dev/null | grep -q ':42083'; then
    echo "  HTTP 42083   : OK"
    if [ -f /opt/cloud-agent/config.json ]; then
      echo "  agent_token  : $(python3 -c 'import json;print(json.load(open("/opt/cloud-agent/config.json")).get("token","")[:12])' 2>/dev/null || echo '?')..."
    fi
  else
    echo "  HTTP 42083   : 未监听"
  fi
  echo "=================================================="
}

# ----------------------------- 主流程 --------------------------------------
[ "$DO_CHECK" -eq 1 ] && { do_check; exit 0; }
check_prereq
[ "$DO_CONTROL" -eq 1 ] && {
  gen_certs
  apply_cloudcore
  apply_crd
  open_control_firewall
}
[ "$DO_DATAPATH" -eq 1 ] && deploy_datapath
[ "$DO_AGENT" -eq 1 ] && deploy_agent
log "部署完成 ✓"
log "  控制面: kubectl -n kubeedge get pods;  边缘盒子 keadm join --cloudcore-ipport=$CLOUD_IP:10002"
log "  数据面: systemctl status nengtan-cloud-broker;  MQTT 41883 / WS 41083 / 仪表盘 41500"
log "  agent:  systemctl status cloud-agent;  HTTP 42083 (token 见上方打印, 平台侧需填写)"
log "  自检:   $0 --check"
