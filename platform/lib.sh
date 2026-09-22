#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 部署脚本公共库（platform/lib.sh，被各 update/deploy 脚本 source）
#
# 统一四件事（此前在每个脚本里逐字重复，改一处要改三处）：
#   ① 仓库根定位 ROOT —— 无论从哪个目录被调用都能定位到仓库根
#   ② 服务器地址 —— 集中 source platform/servers.conf
#   ③ SSH / rsync 传输 —— 免密优先；设了 QZB_SSH_PASS 才经 sshpass 传密码
#   ④ 标准排除列表 —— 源码同步（构建缓存/密钥/运行数据）与运行期状态文件分开
#
# 用法（在各脚本顶部，self_dir 指向该脚本所在目录）：
#   SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   . "$SELF_DIR/../lib.sh"        # 或 . "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
#
# 注意：本文件只提供函数与变量，不做任何动作；被引用的脚本须自行 set -euo pipefail。
# ============================================================================

_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${_LIB_DIR}/.." && pwd)"

# ---- 服务器地址集中配置（platform/servers.conf，缺失则用各脚本内置默认值）----
CONF="${_LIB_DIR}/servers.conf"
[ -f "${CONF}" ] && . "${CONF}" || true

# ---- 传输通道：免密优先（BatchMode=yes 避免卡在密码输入），有密码才走 sshpass ----
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
[ -z "${QZB_SSH_PASS:-}" ] || SSH_OPTS="${SSH_OPTS} -o BatchMode=no"

ssh_run() { # 远程执行：ssh_run <user@host> <命令...>
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    sshpass -p "${QZB_SSH_PASS}" ssh ${SSH_OPTS} "$@"
  else
    ssh ${SSH_OPTS} -o BatchMode=yes "$@"
  fi
}

rsync_run() { # 远程同步：rsync_run <rsync 参数...>（与 ssh_run 同通道）
  local rsh
  if [ -n "${QZB_SSH_PASS:-}" ]; then
    rsh="sshpass -p '${QZB_SSH_PASS}' ssh ${SSH_OPTS}"
  else
    rsh="ssh ${SSH_OPTS} -o BatchMode=yes"
  fi
  rsync -az -e "${rsh}" "$@"
}

# ---- 排除列表 ----
# 通用：版本控制 / 依赖与构建缓存 / 密钥 / 日志（任何一次源码同步都该排除）
LIB_EXCLUDE_COMMON=(
  --exclude=.git --exclude=.venv --exclude=venv --exclude=node_modules
  --exclude=__pycache__ --exclude='*.pyc' --exclude=.DS_Store
  --exclude=.env --exclude='*.log'
)
# 运行期状态：服务器自有一份真源的开发机产物（避免被 rsync 抹成开发机状态）。
# 注：backend/config/（平台运行配置：设备定义 box_devices.json、数据源目录 data_sources.json、
#     box_config / middleware / llm / links / mcp / .env 等）**整个目录都不排除** ——
#     按「本地配置为准、每次推送都同步到服务器」的口径随代码一起同步，
#     保证多端清单一致（用户明确要求不排除）。前提是开发机那份必须是真源：
#     服务器上单独改设备/数据源会被下一次 update.sh 覆盖，生产侧增删改一律在平台界面
#     保存后回填开发机；update.sh 覆盖前会先把服务器现有文件备份到 <仓库根>/.devcfg-backup/。
# 本列表保留编辑器临时文件（不要置空：macOS bash 3.2 + set -u 下展开空数组会报 unbound variable）。
LIB_EXCLUDE_STATE=(
  --exclude='*.swp' --exclude='*~'
)

# lib_rsync <本地源目录> <user@host> <远端目录> [额外 exclude...]
# 在通用排除基础上叠加运行期状态排除，避免每个脚本各写一份导致漏项。
lib_rsync() {
  local src="${1:?lib_rsync: 缺少本地源目录}" host="${2:?lib_rsync: 缺少目标主机}" dst="${3:?lib_rsync: 缺少远端目录}"
  shift 3
  rsync_run "${LIB_EXCLUDE_COMMON[@]}" "${LIB_EXCLUDE_STATE[@]}" "$@" "${src}/" "${host}:${dst}/"
}

# ---- 小工具 ----
lib_need() { # lib_need <命令>...（缺一个就报错退出）
  local c
  for c in "$@"; do
    command -v "${c}" >/dev/null 2>&1 || { echo "❌ 缺少命令：${c}" >&2; exit 1; }
  done
}
lib_log()  { echo "==> $*"; }
lib_ok()   { echo "    ✔ $*"; }
lib_warn() { echo "    ⚠ $*"; }
lib_err()  { echo "❌ $*" >&2; }
