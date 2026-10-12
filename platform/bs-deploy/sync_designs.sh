#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 编排存档双向同步（platform/bs-deploy/sync_designs.sh）
#
# 用途：把服务器实例（40014）上的编排存档合回本地，并把合并结果推回服务器，
#       使「本地 8010」与「服务器 40014」的流程编排 / AI 群控编排始终一致。
#
# 同步口径（用户明确）：**以服务器上的为准**。
#   服务器是编排的权威侧 —— 其有的场景无条件覆盖本地（哪怕本地那份 updatedAt 更新）；
#   仅本地有的场景保留，并随本次推送一并上到服务器。
#   服务器存档缺失 / 为空 / 损坏时不覆盖（保持本地），避免取档失败清空开发机存档。
#   写回本地前留 <文件>.bak.<时间戳> 备份，可回滚。
#   与前端一致：stores/sim.js 的 _pullScheme、PidControlView 的 pullDesigns 同样是
#   「服务端有就用服务端」，localStorage 只作离线兜底。
#
# 用法：bash platform/bs-deploy/sync_designs.sh [--server root@<主机>] [--dir <远端仓库根>] [--no-push]
#       （统一入口：./update.sh designs）
#   --no-push：只把服务器存档合回本地，不回推（platform/bs-deploy/update.sh 加 --designs 时内部用，
#              合并结果由随后的主 rsync 统一推送，避免重复传输）
#
# 触发时机：编排存档**不随日常代码推送同步**（./update.sh all|bs 默认整目录排除，两端各自保留），
#   只在显式执行 ./update.sh designs（或 bs 更新加 --designs）时才做双向合并。
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SELF_DIR/../../lib.sh"
cd "$ROOT"

SERVER="${PLATFORM_SSH:-root@36.151.146.71}"
SERVER_DIR="${PLATFORM_DIR:-/root/qzb/jianpai}"
PUSH=1
while [ $# -gt 0 ]; do
  case "$1" in
    --server|--target) SERVER="${2:-$SERVER}"; shift 2 ;;
    --dir)             SERVER_DIR="${2:-$SERVER_DIR}"; shift 2 ;;
    --no-push)         PUSH=0; shift ;;
    -h|--help)         awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
    *) echo "[error] 未知参数：${1}（-h 查看头部注释）" >&2; exit 1 ;;
  esac
done

DESIGN_DIR="backend/data/designs"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> 编排存档双向同步：$SERVER:$SERVER_DIR/$DESIGN_DIR"
if ! ssh_run "$SERVER" "echo ok" >/dev/null 2>&1; then
  echo "    ⚠ 服务器 $SERVER 不可达 → 跳过（无免密时先 export QZB_SSH_PASS='<密码>'）"
  exit 1
fi

for b in flow agc; do
  LOCAL_F="$DESIGN_DIR/$b.json"
  REMOTE_F="$TMP_DIR/$b.json"
  # 服务器存档取不回来（文件不存在 / 全新部署）时只推本地版本，不阻断流程
  if ! ssh_run "$SERVER" "cat '$SERVER_DIR/$DESIGN_DIR/$b.json'" > "$REMOTE_F" 2>/dev/null; then
    rm -f "$REMOTE_F"
    echo "    · $b：服务器尚无存档 → 本次以本地版本为准"
    continue
  fi
  if [ ! -s "$REMOTE_F" ]; then
    rm -f "$REMOTE_F"
    echo "    · $b：服务器存档为空 → 保持本地版本"
    continue
  fi
  python3 "$SELF_DIR/designs_sync.py" "$b" "$LOCAL_F" "$REMOTE_F" || echo "    ⚠ $b 合并失败（保持本地版本）"
done

if [ "$PUSH" = "1" ]; then
  # --ignore-times：合并后内容可能与服务器一致但时间戳更旧，按内容为准强制收敛两端
  # *.bak.*：合并前留的本地备份不上传（避免服务器目录堆积历史备份件）
  rsync_run --ignore-times --exclude='*.bak.*' "$DESIGN_DIR/" "$SERVER:$SERVER_DIR/$DESIGN_DIR/"
  echo "    ✔ 合并结果已回推服务器"
fi
exit 0
