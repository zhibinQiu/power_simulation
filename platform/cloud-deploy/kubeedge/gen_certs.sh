#!/usr/bin/env bash
# ============================================================================
# 能碳一体机 · 云端 KubeEdge CA/证书生成 (gen_certs.sh)
#
# 依据 kubeedge-console-ops.md 2.2/2.6：
#   - CA 私钥必须是 EC P-256 (prime256v1, SEC1 格式)，绝不是 RSA！
#     （根因: cloudcore 证书签发路径调 x509.ParseECPrivateKey，RSA 会报
#       x509: failed to parse private key (use ParsePKCS8/PKCS1PrivateKey instead)，
#       且两个报错随 key 格式 PKCS#1/PKCS#8 切换而反转，极具误导性）
#   - server 证书 SAN 必须含云端对外 IP，否则边缘 mTLS 报证书不匹配
#   - 证书预置宿主机 /etc/kubeedge，由 cloudcore-all.yaml 以 hostPath 挂载
#
# 用法:
#   ./gen_certs.sh [CLOUD_IP]          # 生成 CA + server 证书 (默认 IP 36.151.146.71)
#   ./gen_certs.sh --with-stream [IP]  # 额外生成 cloudStream 证书 (启用 10003)
#   ./gen_certs.sh --force [IP]        # 已存在证书时强制重新生成 (需重启 cloudcore)
#
# 特性: 幂等 (证书已存在且未加 --force 时跳过)
# ============================================================================
set -euo pipefail

CERT_DIR="/etc/kubeedge"
CLOUD_IP="${1:-36.151.146.71}"
WITH_STREAM=0
FORCE=0

for a in "$@"; do
  case "$a" in
    --with-stream) WITH_STREAM=1 ;;
    --force)       FORCE=1 ;;
    --*)           echo "[error] 未知参数: $a" >&2; exit 1 ;;
    *)             CLOUD_IP="$a" ;;
  esac
done

[ "$(id -u)" -ne 0 ] && { echo "[error] 请以 root 运行"; exit 1; }

log()  { echo -e "\033[32m[certs]\033[0m $*"; }
warn() { echo -e "\033[33m[warn  ]\033[0m $*"; }
err()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

mkdir -p "$CERT_DIR/ca" "$CERT_DIR/certs"

gen_ec_key() { openssl ecparam -genkey -name prime256v1 -noout -out "$1"; }

# ----------------------------- 1. CA ---------------------------------------
if [ -f "$CERT_DIR/ca/rootCA.key" ] && [ -f "$CERT_DIR/ca/rootCA.crt" ] && [ "$FORCE" -eq 0 ]; then
  log "CA 已存在, 跳过 (如需重签: $0 --force)"
else
  log "生成 CA (EC P-256) ..."
  gen_ec_key "$CERT_DIR/ca/rootCA.key"
  openssl req -x509 -new -nodes -key "$CERT_DIR/ca/rootCA.key" \
    -subj "/CN=kubeedge-ca" -days 3650 -out "$CERT_DIR/ca/rootCA.crt"
fi

# ----------------------------- 2. server 证书 ------------------------------
gen_server() {
  [ -f "$CERT_DIR/certs/server.key" ] && [ -f "$CERT_DIR/certs/server.crt" ] && [ "$FORCE" -eq 0 ] \
    && { log "server 证书已存在, 跳过"; return; }
  log "生成 server 证书 (SAN: IP:$CLOUD_IP, DNS:cloudcore.kubeedge.svc) ..."
  gen_ec_key "$CERT_DIR/certs/server.key"
  openssl req -new -key "$CERT_DIR/certs/server.key" -subj "/CN=cloudcore" -out /tmp/server.csr
  openssl x509 -req -in /tmp/server.csr -CA "$CERT_DIR/ca/rootCA.crt" \
    -CAkey "$CERT_DIR/ca/rootCA.key" -CAcreateserial -days 3650 \
    -extfile <(printf "subjectAltName=IP:%s,DNS:cloudcore.kubeedge.svc" "$CLOUD_IP") \
    -out "$CERT_DIR/certs/server.crt"
  rm -f /tmp/server.csr
}
gen_server

# ----------------------------- 3. stream 证书 (可选) ------------------------
gen_stream() {
  [ "$WITH_STREAM" -eq 0 ] && { warn "未指定 --with-stream, 跳过 stream 证书 (cloudStream 10003 将不监听)"; return; }
  [ -f "$CERT_DIR/certs/stream.key" ] && [ -f "$CERT_DIR/certs/stream.crt" ] && [ "$FORCE" -eq 0 ] \
    && { log "stream 证书已存在, 跳过"; return; }
  log "生成 stream 证书 (cloudStream 10003) ..."
  gen_ec_key "$CERT_DIR/certs/stream.key"
  openssl req -new -key "$CERT_DIR/certs/stream.key" -subj "/CN=stream" -out /tmp/stream.csr
  openssl x509 -req -in /tmp/stream.csr -CA "$CERT_DIR/ca/rootCA.crt" \
    -CAkey "$CERT_DIR/ca/rootCA.key" -CAcreateserial -days 3650 \
    -out "$CERT_DIR/certs/stream.crt"
  cp -f "$CERT_DIR/ca/rootCA.crt" "$CERT_DIR/ca/streamCA.crt"   # stream 复用同一 CA
  rm -f /tmp/stream.csr
}
gen_stream

# ----------------------------- 校验 ----------------------------------------
openssl x509 -in "$CERT_DIR/certs/server.crt" -noout -subject -ext subjectAltName >/dev/null 2>&1 \
  || err "server 证书生成失败"
log "完成:"
log "  CA     $CERT_DIR/ca/rootCA.{crt,key} (EC P-256)"
log "  server $CERT_DIR/certs/server.{crt,key} (SAN 含 IP:$CLOUD_IP)"
[ "$WITH_STREAM" -eq 1 ] && log "  stream $CERT_DIR/certs/stream.{crt,key} + streamCA.crt"
log "下一步: deploy_cloud.sh --control-only (apply cloudcore-all.yaml + CRD + 防火墙)"
log "改 CA 后注意: kubectl delete secret tokensecret -n kubeedge 并重启 cloudcore pod 重签 token"
