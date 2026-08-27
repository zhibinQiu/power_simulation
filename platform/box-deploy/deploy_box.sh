#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 边缘盒子一键部署脚本 (deploy_box.sh)
#
# 标准 KubeEdge DMI 链路: 仪表/DCS --(RS485/以太网)--> mapper --gRPC(dmi.sock)-->
#   edgecore --CloudHub--> 云端 CloudCore --> K3s Device.status.twins
# mapper 支持多设备多协议并行: modbus-rtu / modbus-tcp / opcua
#
# 用法:
#   ./deploy_box.sh                     # 完整部署: 依赖 + mapper + mosquitto + systemd
#   ./deploy_box.sh --deps-only         # 仅安装 Python 依赖 (grpcio/protobuf/asyncua)
#   ./deploy_box.sh --mapper-only       # 仅部署 mapper 文件与 systemd 服务
#   ./deploy_box.sh --mosquitto-only    # 仅部署并启动 mosquitto 容器
#   ./deploy_box.sh --check             # 链路自检 (不修改任何东西)
#
# 特性:
#   * 幂等: 重复执行安全, 已存在的配置/服务不会重复创建
#   * 离线: 依赖优先从本包 wheels/ 离线安装, 盒子无外网可用
#   * 可编辑: mapper 配置在 /opt/weight-bridge/config.json, 改完 systemctl restart box-mapper
#   * 可换密: MQTT_USER/MQTT_PASS 环境变量指定, 自动重生成 mosquitto passwd
# ============================================================================
set -euo pipefail

# ----------------------------- 常量 --------------------------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOX_DIR="${BOX_DIR:-/opt/weight-bridge}"
MOSQ_DIR="$BOX_DIR/mosquitto"
DMI_DIR="$BOX_DIR/dmi"
MOSQ_IMG="${MOSQ_IMG:-swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/eclipse-mosquitto:2.0.22-linuxarm64}"
MOSQ_CTR="${MOSQ_CTR:-nengtan-mosquitto}"
MAPPER_SVC="box-mapper.service"
MQTT_USER="${MQTT_USER:-admin}"
MQTT_PASS="${MQTT_PASS:-}"

PYTHON="${PYTHON:-python3}"
PYTHON_BIN="$(command -v "$PYTHON" || echo /usr/bin/python3)"

[ "$(id -u)" -ne 0 ] && { echo "[error] 请以 root 运行 (盒子默认 root)"; exit 1; }

log()  { echo -e "\033[32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

# ----------------------------- 参数 --------------------------------------
DO_DEPS=1; DO_MAPPER=1; DO_MOSQ=1; DO_CHECK=0
for a in "$@"; do
  case "$a" in
    --deps-only)      DO_MAPPER=0; DO_MOSQ=0 ;;
    --mapper-only)    DO_DEPS=0; DO_MOSQ=0 ;;
    --mosquitto-only) DO_DEPS=0; DO_MAPPER=0 ;;
    --check)          DO_DEPS=0; DO_MAPPER=0; DO_MOSQ=0; DO_CHECK=1 ;;
    *) err "未知参数: $a" ;;
  esac
done

# ----------------------------- 1. Python 依赖 ------------------------------
install_deps() {
  log "检查 Python 依赖 (grpcio/protobuf)..."
  if "$PYTHON" -c "import grpc, google.protobuf" 2>/dev/null; then
    log "依赖已就绪: grpcio=$("$PYTHON" -c 'import grpc;print(grpc.__version__)') protobuf=$("$PYTHON" -c 'import google.protobuf;print(google.protobuf.__version__)')"
    return
  fi
  if ls "$SELF_DIR"/wheels/*.whl >/dev/null 2>&1; then
    log "从离线 wheels/ 安装..."
    "$PYTHON" -m pip install --no-index --find-links="$SELF_DIR/wheels" "$SELF_DIR"/wheels/*.whl
  else
    warn "本包无离线 wheel, 尝试在线安装 (盒子通常无外网, 失败请将 arm64 wheel 放入 $SELF_DIR/wheels/)..."
    "$PYTHON" -m pip install grpcio protobuf || err "依赖安装失败"
  fi
  "$PYTHON" -c "import grpc, google.protobuf" || err "依赖安装后仍不可用"
  # paho-mqtt 可选 (云边协同 MQTT 断点续传通道): 缺失时 mapper 自动降级为仅 DMI 补传, 本地缓存不受影响
  if ! "$PYTHON" -c "import paho.mqtt.client" 2>/dev/null; then
    log "安装可选依赖 paho-mqtt (MQTT 断点续传通道)..."
    if ls "$SELF_DIR"/wheels/paho*.whl >/dev/null 2>&1; then
      "$PYTHON" -m pip install --no-index --find-links="$SELF_DIR/wheels" "$SELF_DIR"/wheels/paho*.whl 2>/dev/null \
        || warn "paho-mqtt 离线安装失败 (mapper 仅走 DMI 补传, 本地缓存不丢)"
    else
      "$PYTHON" -m pip install paho-mqtt 2>/dev/null \
        || warn "paho-mqtt 在线安装失败 (mapper 仅走 DMI 补传, 本地缓存不丢)"
    fi
  else
    log "paho-mqtt 已就绪"
  fi
  # opcua-asyncio 可选 (OPC-UA 协议采集): 缺失时 mapper 跳过 opcua 设备, 不影响 modbus-rtu/modbus-tcp
  if ! "$PYTHON" -c "import asyncua" 2>/dev/null; then
    log "安装可选依赖 asyncua (opcua-asyncio, OPC-UA 设备采集)..."
    if ls "$SELF_DIR"/wheels/asyncua*.whl >/dev/null 2>&1; then
      "$PYTHON" -m pip install --no-index --find-links="$SELF_DIR/wheels" "$SELF_DIR"/wheels/asyncua*.whl 2>/dev/null \
        || warn "asyncua 离线安装失败 (opcua 设备将被跳过, 需把 arm64 wheel 放入 $SELF_DIR/wheels/)"
    else
      "$PYTHON" -m pip install asyncua 2>/dev/null \
        || warn "asyncua 在线安装失败 (opcua 设备将被跳过)"
    fi
    if "$PYTHON" -c "import asyncua" 2>/dev/null; then
      log "asyncua 已就绪"
    else
      warn "asyncua 仍不可用: OPC-UA 设备将被跳过, 排查: $PYTHON -c 'import asyncua'"
    fi
  else
    log "asyncua 已就绪"
  fi
  log "依赖安装完成"
}

# ----------------------------- 2. mapper 文件 + systemd --------------------
deploy_mapper() {
  log "部署 mapper 文件到 $DMI_DIR ..."
  mkdir -p "$DMI_DIR"
  cp -f "$SELF_DIR/mapper/box_mapper.py" "$DMI_DIR/"
  cp -f "$SELF_DIR/mapper/api_pb2.py"     "$DMI_DIR/"
  cp -f "$SELF_DIR/mapper/api_pb2_grpc.py" "$DMI_DIR/"
  # 保留已有可编辑配置, 首次部署才复制模板
  if [ ! -f "$BOX_DIR/config.json" ]; then
    cp -f "$SELF_DIR/mapper/config.json" "$BOX_DIR/config.json"
    log "已创建可编辑配置 $BOX_DIR/config.json (改完 systemctl restart $MAPPER_SVC 生效)"
  else
    log "保留已有配置 $BOX_DIR/config.json"
  fi

  # 兼容旧命名: 移除历史 nengtan-mapper 服务与旧脚本, 统一为 box-mapper
  if [ -f /etc/systemd/system/nengtan-mapper.service ]; then
    log "发现旧服务 nengtan-mapper.service, 迁移到 $MAPPER_SVC ..."
    systemctl stop nengtan-mapper.service >/dev/null 2>&1 || true
    systemctl disable nengtan-mapper.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/nengtan-mapper.service
  fi
  [ -f "$DMI_DIR/nengtan_mapper.py" ] && rm -f "$DMI_DIR/nengtan_mapper.py"

  # systemd 服务 (幂等覆盖)
  cat > "/etc/systemd/system/$MAPPER_SVC" <<EOF
[Unit]
Description=NengTan KubeEdge DMI Multi-Protocol Mapper (Modbus RTU/TCP, OPC-UA)
After=network.target edgecore.service

[Service]
ExecStart=$PYTHON_BIN -u $DMI_DIR/box_mapper.py
Restart=always
RestartSec=5
WorkingDirectory=$DMI_DIR

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  # 确保开机自启 (is-enabled 对 disabled 返回非零, 直接 enable)
  systemctl enable "$MAPPER_SVC" >/dev/null 2>&1 || true

  # 清理旧的 nohup 实例, 避免双实例冲突 (串口/注册名重复)
  if pgrep -f "$DMI_DIR/box_mapper.py" >/dev/null 2>&1; then
    log "停止旧 mapper 实例 (nohup/systemd)..."
    pkill -f "$DMI_DIR/box_mapper.py" || true
    sleep 2
  fi

  if systemctl is-enabled "$MAPPER_SVC" >/dev/null 2>&1; then
    systemctl enable "$MAPPER_SVC" >/dev/null 2>&1 || true
  fi
  systemctl restart "$MAPPER_SVC" || warn "systemd 启动失败, 检查: journalctl -u $MAPPER_SVC"
  sleep 2
  systemctl is-active "$MAPPER_SVC" >/dev/null 2>&1 \
    && log "mapper 服务运行中 ✓" \
    || warn "mapper 服务未激活, 尝试 nohup 兜底: nohup $PYTHON_BIN -u $DMI_DIR/box_mapper.py > $DMI_DIR/mapper.log 2>&1 &"
}

# ----------------------------- 3. mosquitto 容器 ----------------------------
deploy_mosquitto() {
  log "部署 mosquitto 配置到 $MOSQ_DIR ..."
  mkdir -p "$MOSQ_DIR/data" "$MOSQ_DIR/log"
  cp -f "$SELF_DIR/mosquitto/mosquitto.conf" "$MOSQ_DIR/"
  cp -f "$SELF_DIR/mosquitto/mosquitto.acl"  "$MOSQ_DIR/"

  if [ -n "$MQTT_PASS" ]; then
    log "按 MQTT_USER=$MQTT_USER 重新生成 passwd..."
    ctr -n k8s.io run --rm --net-host "$MOSQ_IMG" mosq-passwd \
      /usr/bin/mosquitto_passwd -b -c /tmp/passwd "$MQTT_USER" "$MQTT_PASS" >/dev/null 2>&1 \
      || warn "容器内生成 passwd 失败, 沿用预生成文件"
    if [ -f /tmp/passwd ]; then
      cp -f /tmp/passwd "$MOSQ_DIR/passwd"
      rm -f /tmp/passwd
    fi
  elif [ ! -f "$MOSQ_DIR/passwd" ]; then
    cp -f "$SELF_DIR/mosquitto/passwd" "$MOSQ_DIR/passwd"
    log "已部署预生成 passwd (admin 密码 hy@2025@, 改密见 README)"
  fi

  # 权限修正 (关键坑: 容器内 mosquitto 以 uid=1883 运行, 600 权限的 passwd 读不到)
  chmod 644 "$MOSQ_DIR"/mosquitto.conf "$MOSQ_DIR"/mosquitto.acl "$MOSQ_DIR"/passwd 2>/dev/null || true
  chmod 777 "$MOSQ_DIR/data" "$MOSQ_DIR/log" 2>/dev/null || true

  log "启动 mosquitto 容器 ($MOSQ_CTR)..."
  if ctr -n k8s.io t ls 2>/dev/null | grep -q "$MOSQ_CTR" && ss -tlnp 2>/dev/null | grep -q ':1883'; then
    log "mosquitto 已在运行并监听 1883 ✓"
    return
  fi
  # 拉镜像 (首次或缺失)
  ctr -n k8s.io i check "$MOSQ_IMG" >/dev/null 2>&1 || {
    log "拉取镜像 $MOSQ_IMG ..."
    ctr -n k8s.io i pull "$MOSQ_IMG" >/dev/null 2>&1 || err "镜像拉取失败, 请检查网络或手工导入"
  }
  ctr -n k8s.io c rm "$MOSQ_CTR" >/dev/null 2>&1 || true
  ctr -n k8s.io run --detach --net-host \
    --mount "type=bind,src=$MOSQ_DIR,dst=/mosquitto/config,options=rbind:rw" \
    "$MOSQ_IMG" "$MOSQ_CTR" \
    /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf >/dev/null 2>&1 \
    || err "mosquitto 容器启动失败"
  sleep 3
  ss -tlnp 2>/dev/null | grep -q ':1883' \
    && log "mosquitto 监听 1883 ✓" \
    || err "1883 未监听, 启动异常 (ctr -n k8s.io t ls 查看容器状态)"
}

# ----------------------------- 4. 链路自检 ----------------------------------
do_check() {
  echo "================ 边缘盒子链路自检 ================"
  echo "--- 1. 服务状态 ---"
  systemctl is-active edgecore   2>/dev/null && echo "  edgecore   : ACTIVE"  || echo "  edgecore   : inactive"
  systemctl is-active "$MAPPER_SVC" 2>/dev/null && echo "  mapper     : ACTIVE"  || echo "  mapper     : inactive"
  echo "--- 2. mosquitto 1883 ---"
  ss -tlnp 2>/dev/null | grep -q ':1883' && echo "  1883       : OK" || echo "  1883       : FAIL"
  echo "--- 3. DMI socket ---"
  [ -S /etc/kubeedge/dmi.sock ] && echo "  dmi.sock   : OK" || echo "  dmi.sock   : 缺失 (edgecore 需启用 DMI)"
  echo "--- 4. 串口设备 ---"
  if ls /dev/ttyUSB* /dev/ttyS* 2>/dev/null | head -3; then :; else echo "  未找到 ttyUSB/ttyS 设备"; fi
  echo "--- 5. mapper 最近日志 ---"
  tail -n 6 "$DMI_DIR/mapper.log" 2>/dev/null \
    || journalctl -u "$MAPPER_SVC" --no-pager -n 6 2>/dev/null \
    || echo "  (无日志)"
  echo "--- 6. Python 依赖 ---"
  "$PYTHON" -c "import grpc,google.protobuf; print('  grpcio', grpc.__version__, '/ protobuf', google.protobuf.__version__)" 2>/dev/null \
    || echo "  grpcio/protobuf 缺失"
  if "$PYTHON" -c "import asyncua" 2>/dev/null; then
    echo "  asyncua   : OK (OPC-UA 可用)"
  else
    echo "  asyncua   : 未安装 (opcua 设备跳过, modbus 不受影响)"
  fi
  echo "--- 7. 协议支持 (mapper 自检) ---"
  "$PYTHON" - <<'EOF' 2>/dev/null || echo "  无法自检 (mapper 未部署或依赖缺失)"
import json, os
cfg = json.load(open("/opt/weight-bridge/config.json"))
protos = {}
for d in cfg.get("devices", []):
    protos.setdefault(d.get("protocol"), []).append(d.get("name"))
for p, names in protos.items():
    print("  %-12s: %s" % (p, ", ".join(names)))
EOF
  echo "=================================================="
}

# ----------------------------- 主流程 --------------------------------------
[ "$DO_CHECK" -eq 1 ] && { do_check; exit 0; }
[ "$DO_DEPS" -eq 1 ]   && install_deps
[ "$DO_MOSQ" -eq 1 ]   && deploy_mosquitto
[ "$DO_MAPPER" -eq 1 ] && deploy_mapper
log "部署完成 ✓  下一步: 云端确认 Device 已 apply 后, 触发一次 Device 更新让 edgecore 路由到 mapper"
log "提示: 改配置 -> vim $BOX_DIR/config.json && systemctl restart $MAPPER_SVC"
