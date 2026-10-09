#!/bin/bash
# edgecore-watchdog：检测边缘 edgecore 消息链路卡死并自动恢复（自愈）
# 症状：twin message channel is full / metaclient send sync message ... timeout
# 恢复：先只重启 box-mapper（消息源），仍未缓解才重启 edgecore。
#
# 部署：/usr/local/bin/edgecore-watchdog.sh + /etc/systemd/system/edgecore-watchdog.service
#       （Type=simple + Restart=always + RestartSec=30，即每 30s 巡检一次）
#
# 2026-09-28 修复「断电上电后终端无法自动上线」时发现本脚本有三个误判/误伤：
#   ① 原实现用 journalctl -u edgecore --since "120 seconds ago"（不带 -b），刚重启完
#      的第一次巡检会读到**上一个 boot** 的旧日志——而每次重启前通道必然是满的，
#      于是开机 10 秒内必定误触发一次自愈，把刚起来的 edgecore + box-mapper 又打断
#      一次（冷启动最需要稳定的时刻被打断）。现改为 -b 只看本次启动。
#   ② edgecore 本次启动未满 GRACE 秒不触发：冷启动期要重新注册节点、同步 device，
#      通道短暂拥堵是常态，此时重启只会延长上线时间。
#   ③ 原实现无条件「停 mapper → 重启 edgecore → 起 mapper」。重启 edgecore 会断开
#      CloudHub 会话、节点立刻 NotReady，是把「通道堵」放大成「终端离线」的动作。
#      现改为分级：先只重启 box-mapper（twin 消息的生产者），未缓解才升级重启 edgecore。

COOL=900          # 冷却秒数（两次恢复动作之间的最小间隔）
WIN=120           # 检测窗口（最近 N 秒日志）
MIN_HITS=6        # 窗口内命中阈值（30s 巡检 × 2 窗口 = 约 1 分钟内持续异常才触发）
GRACE=300         # edgecore 本次启动后的宽限期（秒），期间不触发
STAMP=/run/edgecore-watchdog.last
STAMP_HEAVY=/run/edgecore-watchdog.heavy
LOG=/var/log/edgecore-watchdog.log

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

# 冷却检查
if [ -f "$STAMP" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  now=$(date +%s)
  if [ $((now - last)) -lt "$COOL" ]; then
    exit 0
  fi
fi

# 宽限期：edgecore 本次启动未满 GRACE 秒不触发（含冷启动与上一次自愈后的重启）
started=$(systemctl show edgecore -p ActiveEnterTimestamp --value 2>/dev/null)
if [ -n "$started" ]; then
  st=$(date -d "$started" +%s 2>/dev/null || echo 0)
  age=$(( $(date +%s) - st ))
  if [ "$st" -gt 0 ] && [ "$age" -lt "$GRACE" ]; then
    log "SKIP 宽限期：edgecore 本次启动仅 ${age}s（< ${GRACE}s），冷启动期通道拥堵属正常"
    exit 0
  fi
fi

# 只看本次启动的日志（关键：不带 -b 会把上一个 boot 的旧日志算进来）
hits=$(journalctl -u edgecore -b --no-pager --since "${WIN} seconds ago" 2>/dev/null \
  | grep -cE 'twin message channel is full|metaclient\.go.*send sync message.*(failed|timeout)')

if [ "$hits" -ge "$MIN_HITS" ]; then
  # 分级恢复：若上一轮已经重启过 mapper 却仍异常，才升级为重启 edgecore
  heavy=0
  if [ -f "$STAMP_HEAVY" ]; then
    hlast=$(cat "$STAMP_HEAVY" 2>/dev/null || echo 0)
    if [ $(( $(date +%s) - hlast )) -lt $((COOL * 2)) ]; then
      heavy=1
    fi
  fi
  date +%s > "$STAMP"
  if [ "$heavy" -eq 1 ]; then
    log "DETECT 命中 $hits 次（窗口 ${WIN}s）；上轮重启 mapper 未缓解 → 升级重启 edgecore"
    systemctl stop box-mapper 2>/dev/null
    systemctl restart edgecore
    sleep 20
    systemctl start box-mapper 2>/dev/null
    rm -f "$STAMP_HEAVY"
  else
    log "DETECT 命中 $hits 次（窗口 ${WIN}s）；先只重启 box-mapper（twin 消息源）"
    systemctl restart box-mapper 2>/dev/null
    date +%s > "$STAMP_HEAVY"
  fi
  sleep 10
  if systemctl is-active --quiet edgecore && systemctl is-active --quiet box-mapper; then
    log "RECOVER OK：edgecore + box-mapper 均已运行"
  else
    log "RECOVER WARN：恢复后服务状态异常，请人工介入"
  fi
fi
