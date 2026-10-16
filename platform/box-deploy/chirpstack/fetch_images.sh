#!/usr/bin/env bash
# ============================================================================
# 离线镜像打包（在【有网的 Linux 机器】上执行，不能在 mac 本地执行 docker）
#
# 一体机（rk3568 / aarch64 / Ubuntu 22.04）现场通常无外网，ChirpStack 全家桶
# 镜像必须先在能上网的机器上按 arm64 拉取、打包，再拷到盒子用 docker load 导入。
#
# 用法：
#   bash fetch_images.sh                          # 默认打出 ./nengtan-chirpstack-images.tar.gz
#   bash fetch_images.sh --platform linux/arm64   # 明确指定架构（默认 linux/arm64）
#   bash fetch_images.sh --out /tmp/cs.tar.gz
#
# 产物用法：
#   scp nengtan-chirpstack-images.tar.gz root@<盒子IP>:/tmp/
#   bash deploy_chirpstack.sh install --images /tmp/nengtan-chirpstack-images.tar.gz
# ============================================================================
set -euo pipefail

PLATFORM="${PLATFORM:-linux/arm64}"
CS_VER="${CS_VER:-4.19.1}"
BRIDGE_VER="${BRIDGE_VER:-4.1.2}"
OUT="${OUT:-./nengtan-chirpstack-images.tar.gz}"

CS_IMG="chirpstack/chirpstack:${CS_VER}"
BRIDGE_IMG="chirpstack/chirpstack-gateway-bridge:${BRIDGE_VER}"
PG_IMG="postgres:14-alpine"
REDIS_IMG="redis:7-alpine"
MOSQ_IMG="eclipse-mosquitto:2.0.22"
ALL_IMGS="${CS_IMG} ${BRIDGE_IMG} ${PG_IMG} ${REDIS_IMG} ${MOSQ_IMG}"

while [ $# -gt 0 ]; do
  case "$1" in
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --out)      OUT="${2:-}"; shift 2 ;;
    *) echo "[error] 未知参数: $1" >&2; exit 1 ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "[error] 本机无 docker（请在有网 Linux 服务器上执行）" >&2; exit 1; }

echo "==> 拉取 ${PLATFORM} 镜像"
for img in $ALL_IMGS; do
  echo "  pull ${img}"
  docker pull --platform "$PLATFORM" "$img"
done

echo "==> 打包到 ${OUT}"
TMP_TAR="${OUT%.gz}"
docker save -o "$TMP_TAR" $ALL_IMGS
gzip -f "$TMP_TAR"
ls -lh "${OUT}"

echo "==> 完成。拷贝到盒子并导入："
echo "    scp ${OUT} root@<盒子IP>:/tmp/"
echo "    bash deploy_chirpstack.sh install --images /tmp/$(basename "${OUT}")"
