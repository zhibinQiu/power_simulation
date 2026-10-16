#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · LoRaWAN 网络服务器（ChirpStack v4）离线部署脚本
#
# 适用：外置 LoRaWAN 网关（Semtech UDP Packet Forwarder）经网线接入一体机，
#       由一体机上运行的网关桥 + ChirpStack 完成 LoRaWAN 解码，
#       解码后的应用上行经本地 MQTT(41884) 交给 box_mapper LoraReader。
#
# 用法（在盒子上以 root 执行）：
#   bash deploy_chirpstack.sh install [--region cn470_0] [--images /path/images.tar.gz]
#   bash deploy_chirpstack.sh start | stop | restart | status | logs | uninstall | check
#
# 用法（从开发机推送到盒子）：
#   bash deploy_chirpstack.sh install --server root@<盒子IP> [--images /path/images.tar.gz]
#
# 云端版（部署到平台服务器，有网直接在线拉镜像；bridge 网络 + 4xxxx 端口）：
#   bash deploy_chirpstack.sh install --cloud --online
#
# 离线：盒子通常无外网，镜像需先在【有网 Linux 机器】执行同目录 fetch_images.sh 打包，
#       再用 --images 传入（自动 docker load）。
#
# 特性：
#   * 幂等：重复执行安全；已存在的 chirpstack.toml 只补 region 文件与占位符，不覆盖手工修改
#   * host 网络：盒子 docker 的 iptables=false，bridge 端口映射不可用，故全部 network_mode: host
#   * 端口：8080(UI/API) / 1700 udp(网关上行) / 5432(pg) / 6379(redis) / 41884(LoRa MQTT,仅回环)
# ============================================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CS_VER="${CS_VER:-4.19.1}"
BRIDGE_VER="${BRIDGE_VER:-4.1.2}"
INSTALL_DIR="${INSTALL_DIR:-/opt/nengtan-chirpstack}"
REGION="${REGION:-cn470_0}"
IMAGES_TAR=""
SERVER=""
ACTION="install"
CLOUD=0
ONLINE=0
CLOUD_FLAG=""
ONLINE_FLAG=""
COMPOSE_FILE="docker-compose.yml"

CS_IMG="chirpstack/chirpstack:${CS_VER}"
BRIDGE_IMG="chirpstack/chirpstack-gateway-bridge:${BRIDGE_VER}"
PG_IMG="postgres:14-alpine"
REDIS_IMG="redis:7-alpine"
MOSQ_IMG="eclipse-mosquitto:2.0.22"
ALL_IMGS="${CS_IMG} ${BRIDGE_IMG} ${PG_IMG} ${REDIS_IMG} ${MOSQ_IMG}"
SVC="nengtan-chirpstack.service"

log()  { echo -e "\033[32m[lora ]\033[0m $*"; }
warn() { echo -e "\033[33m[warn ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    install|start|stop|restart|status|logs|uninstall|check) ACTION="$1"; shift ;;
    --region) REGION="${2:-}"; shift 2 ;;
    --images) IMAGES_TAR="${2:-}"; shift 2 ;;
    --server) SERVER="${2:-}"; shift 2 ;;
    --dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    --cloud)  CLOUD=1; CLOUD_FLAG="--cloud"; shift ;;
    --online) ONLINE=1; ONLINE_FLAG="--online"; shift ;;
    *) err "未知参数: $1" ;;
  esac
done

if [ "$CLOUD" -eq 1 ]; then
  COMPOSE_FILE="docker-compose.cloud.yml"
fi

# --------------------------- 远程推送模式 ----------------------------------
if [ -n "$SERVER" ]; then
  [ "$ACTION" = "install" ] || err "--server 仅用于 install"
  log "推送部署包到 ${SERVER}:${INSTALL_DIR}"
  ssh "$SERVER" "mkdir -p ${INSTALL_DIR}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -avz --delete "$SELF_DIR"/ "$SERVER:${INSTALL_DIR}/" >/dev/null
  else
    scp -r "$SELF_DIR"/. "$SERVER:${INSTALL_DIR}/" >/dev/null
  fi
  if [ -n "$IMAGES_TAR" ]; then
    log "上传离线镜像包 $(basename "${IMAGES_TAR}")"
    scp "$IMAGES_TAR" "$SERVER:/tmp/$(basename "${IMAGES_TAR}")" >/dev/null
    IMAGES_TAR="/tmp/$(basename "${IMAGES_TAR}")"
  fi
  # shellcheck disable=SC2087
  ssh "$SERVER" "bash ${INSTALL_DIR}/deploy_chirpstack.sh install --region ${REGION} ${IMAGES_TAR:+--images ${IMAGES_TAR}} ${CLOUD_FLAG} ${ONLINE_FLAG}"
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  err "请以 root 运行（盒子默认 root）"
fi

# --------------------------- 环境检查 --------------------------------------
precheck() {
  command -v docker >/dev/null 2>&1 || err "未安装 docker"
  docker compose version >/dev/null 2>&1 || err "docker compose 插件不可用（需 v2）"
  local mem
  mem=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
  if [ "$mem" -gt 0 ] && [ "$mem" -lt 900 ]; then
    warn "可用内存仅 ${mem}MB，ChirpStack 全家桶建议 ≥1GB（可停掉非必要服务后再装）"
  fi
  for p in 8080 5432 6379 41884; do
    if (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${p}\b"; then
      warn "端口 ${p} 已被占用，容器可能无法启动（${INSTALL_DIR}/docker-compose.yml 可调整）"
    fi
  done
  if (ss -lnu 2>/dev/null || netstat -lnu 2>/dev/null) | grep -q ':1700\b'; then
    warn "UDP 1700 已被占用，网关上行可能收不到"
  fi
}

# --------------------------- 部署文件 --------------------------------------
sync_files() {
  if [ "$SELF_DIR" = "$INSTALL_DIR" ]; then
    log "就地部署（本脚本已在 ${INSTALL_DIR}）"
    return
  fi
  log "部署配置到 ${INSTALL_DIR}"
  mkdir -p "$INSTALL_DIR"
  cp -rf "$SELF_DIR"/. "$INSTALL_DIR/"
}

# 从官方镜像提取 region_*.toml（镜像自带全部频段文件，避免手写）
extract_regions() {
  local cfg="$INSTALL_DIR/configuration/chirpstack"
  if ls "$cfg"/region_*.toml >/dev/null 2>&1; then
    log "region 频段文件已存在，跳过提取"
    return
  fi
  log "从镜像 ${CS_IMG} 提取 region 频段文件..."
  local tmp cid
  tmp=$(mktemp -d)
  cid=$(docker create "$CS_IMG" 2>/dev/null) || { warn "无法创建临时容器（镜像缺失？），跳过 region 提取"; rm -rf "$tmp"; return; }
  docker cp "$cid:/etc/chirpstack/." "$tmp"/ >/dev/null 2>&1 || warn "镜像内 /etc/chirpstack 拷贝失败"
  docker rm "$cid" >/dev/null 2>&1 || true
  if ls "$tmp"/region_*.toml >/dev/null 2>&1; then
    mkdir -p "$cfg"
    cp -f "$tmp"/region_*.toml "$cfg"/
    log "已提取 $(ls "$cfg"/region_*.toml | wc -l | tr -d ' ') 个 region 文件"
  else
    warn "镜像内未找到 region_*.toml，ChirpStack 可能因缺少频段配置无法启动"
  fi
  rm -rf "$tmp"
}

render_config() {
  local cs="$INSTALL_DIR/configuration/chirpstack/chirpstack.toml"
  local gw="$INSTALL_DIR/configuration/chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml"
  [ -f "$cs" ] || err "缺少 $cs"
  log "渲染配置 region=${REGION}"
  sed -i "s/cn470_0/${REGION}/g" "$cs" "$gw"
  if grep -q "__CHIRPSTACK_SECRET__" "$cs"; then
    local sec
    sec=$(openssl rand -base64 32 2>/dev/null || echo "nengtan-${RANDOM}-$(date +%s)")
    sed -i "s|__CHIRPSTACK_SECRET__|${sec}|" "$cs"
    log "已生成 API secret"
  fi
  # 云端模式网关桥也在 bridge 网络内，用服务名连 broker；
  # 盒子模式网关桥是 host 网络，只能走宿主映射端口 127.0.0.1:41884
  if [ "$CLOUD" -eq 1 ]; then
    sed -i 's|tcp://127.0.0.1:41884|tcp://mosquitto-lora:1883|' "$gw"
    log "云端模式：网关桥改用服务名连接 mosquitto-lora"
  fi
  # region 文件存在性校验（镜像/网关两侧 region 必须同名）
  if ! ls "$INSTALL_DIR/configuration/chirpstack/region_${REGION}.toml" >/dev/null 2>&1; then
    warn "未找到 region_${REGION}.toml，可用频段："
    ls "$INSTALL_DIR/configuration/chirpstack"/region_*.toml 2>/dev/null | sed 's|.*/region_||;s|\.toml||' | tr '\n' ' ' || true
    echo ""
  fi
}

load_images() {
  if [ -n "$IMAGES_TAR" ]; then
    [ -f "$IMAGES_TAR" ] || err "镜像包不存在: ${IMAGES_TAR}"
    log "导入离线镜像 ${IMAGES_TAR} ..."
    if [[ "$IMAGES_TAR" == *.gz ]]; then
      gunzip -c "$IMAGES_TAR" | docker load
    else
      docker load -i "$IMAGES_TAR"
    fi
  fi
  local miss=0
  for img in $ALL_IMGS; do
    if docker image inspect "$img" >/dev/null 2>&1; then
      log "镜像就绪: ${img}"
    elif [ "$ONLINE" -eq 1 ]; then
      log "在线拉取: ${img}"
      docker pull "$img" || { warn "拉取失败: ${img}"; miss=1; }
    else
      warn "镜像缺失: ${img}"
      miss=1
    fi
  done
  if [ "$miss" -eq 1 ]; then
    err "有镜像缺失：请在本包目录下于【有网 Linux 机器】执行 bash fetch_images.sh，再用 --images 传入（云端装可加 --online 直接拉）"
  fi
}

install_service() {
  local dc
  dc=$(command -v docker)
  cat > "/etc/systemd/system/${SVC}" <<EOF
[Unit]
Description=NengTan ChirpStack LoRaWAN Network Server (docker compose)
After=docker.service network.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=${dc} compose -f ${COMPOSE_FILE} up -d
ExecStop=${dc} compose -f ${COMPOSE_FILE} down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$SVC" >/dev/null 2>&1 || true
}

# ChirpStack migrations 依赖 pg_trgm/hstore；initdb 脚本只在数据卷为空时执行，
# 这里兜底补一次，保证升级/重建场景也能创建（幂等）
ensure_pg_extensions() {
  local i
  for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U chirpstack >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  log "补齐 PostgreSQL 扩展（pg_trgm / hstore）..."
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U chirpstack -d chirpstack \
    -c "create extension if not exists pg_trgm;" \
    -c "create extension if not exists hstore;" >/dev/null 2>&1 \
    || warn "创建 PG 扩展失败：请手动执行 docker compose exec postgres psql -U chirpstack -d chirpstack -c 'create extension if not exists pg_trgm;'"
}

do_up() {
  cd "$INSTALL_DIR"
  local wait_port="8080"
  [ "$CLOUD" -eq 1 ] && wait_port="41080"
  log "启动容器栈（首次启动会初始化数据库，约需 1-2 分钟）..."
  docker compose -f "$COMPOSE_FILE" up -d
  systemctl restart "$SVC" >/dev/null 2>&1 || true
  local i
  for i in $(seq 1 30); do
    if (ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null) | grep -q ":${wait_port}\b"; then break; fi
    sleep 5
  done
  ensure_pg_extensions
  # 首次启动时 Postgres 往往还没就绪，chirpstack 会带着"迁移失败"的状态空转，
  # 这里重启一次让它重跑 schema migrations 并加载 region 配置
  log "重启 chirpstack（重跑数据库迁移 + 加载 region 配置）..."
  docker compose -f "$COMPOSE_FILE" restart chirpstack >/dev/null 2>&1 || true
  sleep 20
  do_status
}

do_status() {
  cd "$INSTALL_DIR"
  local ui_port="8080"
  [ "$CLOUD" -eq 1 ] && ui_port="41080"
  echo "================ ChirpStack 栈状态 ================"
  docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || docker ps -a | grep -E 'chirpstack|postgres|redis|mosquitto'
  echo "--- 端口 ---"
  for x in "${ui_port}:tcp" "1700:udp" "41884:tcp"; do
    local p="${x%%:*}" proto="${x##*:}"
    if (ss -ln"${proto:0:1}" 2>/dev/null || netstat -ln"${proto:0:1}" 2>/dev/null) | grep -q ":${p}\b"; then
      echo "  ${p}/${proto} : OK"
    else
      echo "  ${p}/${proto} : --"
    fi
  done
  echo "--- ChirpStack 最近日志 ---"
  docker compose -f "$COMPOSE_FILE" logs --tail 8 chirpstack 2>/dev/null | tail -8 || true
  echo "==================================================="
}

do_check() {
  do_status
  echo "--- 网关上行自检（等待 30s 看是否有 UDP 上行）---"
  echo "  查看网关桥日志: docker compose -f ${INSTALL_DIR}/${COMPOSE_FILE} logs -f chirpstack-gateway-bridge"
  echo "  在盒子执行: mosquitto_sub -h 127.0.0.1 -p 41884 -t '#' -v"
  echo "--- 若收不到网关数据，依次排查 ---"
  echo "  1) 网关 Packet Forwarder 的 server 地址是否为盒子 IP、端口 1700"
  echo "  2) 网关与盒子是否同网段、网线/交换机是否通（ping 盒子 IP）"
  echo "  3) ChirpStack UI 中网关是否注册（网关 EUI 需与网关侧一致）"
  echo "  4) 网关桥主题前缀 ${REGION} 与 chirpstack.toml 的 enabled_regions 是否一致"
}

do_logs() { cd "$INSTALL_DIR"; docker compose -f "$COMPOSE_FILE" logs -f --tail 100; }

do_down()   { cd "$INSTALL_DIR"; docker compose -f "$COMPOSE_FILE" down; }
do_stop()   { systemctl stop "$SVC" 2>/dev/null || true; cd "$INSTALL_DIR"; docker compose -f "$COMPOSE_FILE" stop; }
do_start()  { cd "$INSTALL_DIR"; docker compose -f "$COMPOSE_FILE" start; systemctl start "$SVC" >/dev/null 2>&1 || true; }
do_restart(){ cd "$INSTALL_DIR"; docker compose -f "$COMPOSE_FILE" restart; }

do_uninstall() {
  log "停止并移除容器栈..."
  systemctl stop "$SVC" >/dev/null 2>&1 || true
  systemctl disable "$SVC" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/${SVC}"
  systemctl daemon-reload
  cd "$INSTALL_DIR"
  docker compose -f "$COMPOSE_FILE" down -v
  log "已卸载（配置与数据卷保留在 ${INSTALL_DIR}；数据卷删除: docker volume rm nengtan-chirpstack_postgresqldata nengtan-chirpstack_redisdata）"
}

# --------------------------- 主流程 ----------------------------------------
case "$ACTION" in
  install)
    precheck
    sync_files
    load_images      # 必须先导入镜像：region 频段文件要从 chirpstack 镜像里提取
    extract_regions
    render_config
    install_service
    do_up
    log "部署完成 ✓  ChirpStack UI: http://<盒子IP>:8080  (admin/admin，首次登录请改密)"
    log "下一步：网关 Packet Forwarder 指向本机 1700；mapper 侧 lora.broker=127.0.0.1 lora.port=41884"
    ;;
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_restart ;;
  status)  do_status ;;
  logs)    do_logs ;;
  check)   do_check ;;
  uninstall) do_uninstall ;;
esac
