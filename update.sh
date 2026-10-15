#!/usr/bin/env bash
# ============================================================================
# 能碳全平台 · 一键更新总入口（仓库根 ./update.sh）
#
# 日常更新只用这一个脚本：一条指令同步到所有位置。GitHub 永不自动推送，
# 必须显式写 github 才会推代码。
#
# 用法：
#   ./update.sh all                                  同步到所有位置（不含 GitHub）
#   ./update.sh all github "feat: xxx"               同步到所有位置 + 推送 GitHub
#   ./update.sh all github "feat: xxx" --tag v1.2.3  同步 + 推送 + 打 tag（触发打包发布）
#   ./update.sh github "feat: xxx" [--tag v1.2.3]    仅推送 GitHub（可单独用）
#   ./update.sh bs                                   仅平台服务器（代码 + 前端产物 + 配置）
#   ./update.sh cloud                                仅云端（cloud-agent + 数据面 broker/collector/dashboard）
#   ./update.sh middleware                           仅数据中间件（/opt/nengtan-middleware）
#   ./update.sh docs                                 仅文档站 + 源文档
#   ./update.sh portal                               仅官网门户静态内容
#   ./update.sh nginx                                仅官网 nginx 反代网关
#   ./update.sh simsource start|status|stop|...      独立模拟数据源服务（非平台代码）
#   ./update.sh list                                 查看全部目标
#
# all 覆盖六个位置（按顺序，单步失败不中断，末尾汇总）：
#   ① 平台服务器（bs：本地构建前端/文档站 → rsync 源码+配置 → 容器 reload/重建 → 健康检查）
#   ② 云端（cloud-agent + 数据面 broker/collector/dashboard：md5 有变才覆盖并重启）
#   ③ 数据中间件（/opt/nengtan-middleware：rsync + restart nengtan-middleware）
#   ④ 文档站（docs-site 构建 + 容器生效）
#   ⑤ 官网门户（www.nengyousuan.com 静态内容）
#   ⑥ 官网 nginx 网关（配置下发 + reload）
#
# 目标地址集中配置在 platform/servers.conf（可用环境变量覆盖，见该文件）。
# 单目标的附加参数直接透传，例：./update.sh bs --skip-build / --skip-config
#
# 编排存档（backend/data/designs/{flow,agc}.json + workspace.json）**永不随推送同步**：
#   它是用户在官网平台上编辑出来的运行期内容（流程编排 / AI 群控策略 / 最后打开的工程），
#   官网实例即为唯一真源 —— 开发机不回填、不覆盖，否则一次代码推送就会抹掉线上数据。
#
# 全新部署（第一次装机）走 ./deploy.sh，不在本脚本范围内。
# ============================================================================
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 公共库（仓库根 lib.sh）：ROOT / servers.conf / ssh_run / rsync_run
. "$SELF_DIR/lib.sh"
cd "$ROOT"

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 0
}

[ $# -ge 1 ] || usage
TARGET="$1"
shift

# ---- 参数解析：github 关键字与 --tag 归 GitHub 步骤，其余透传给具体目标 ----
PASS_ARGS=()
DO_GH=0
GH_MSG=""
GH_TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    github|gh)  DO_GH=1; shift ;;
    --tag)      GH_TAG="${2:-}"; shift 2 ;;
    -h|--help)  usage ;;
    *)          PASS_ARGS+=("$1"); shift ;;
  esac
done
case "$TARGET" in
  github|gh) DO_GH=1 ;;
esac
# github 后的第一个透传参数视为提交信息，**消费掉**（不要再透传给具体目标：
# bs-deploy/update.sh 遇到非预期参数会 "[error] 未知参数" 直接 exit 1，导致 ① 步骤失败）。
if [ "$DO_GH" = "1" ] && [ ${#PASS_ARGS[@]} -gt 0 ]; then
  GH_MSG="${PASS_ARGS[0]}"
  PASS_ARGS=("${PASS_ARGS[@]:1}")
fi

FAILED=()          # 失败步骤汇总（all 模式不中断，最后统一报）
run_step() {       # run_step <显示名> <函数>
  local name="$1"; shift
  echo ""
  echo "────────────────────────────────────────────"
  echo "==> [$name]"
  if "$@"; then
    echo "    ✔ $name 完成"
  else
    echo "    ⚠ $name 失败（见上方输出）"
    FAILED+=("$name")
  fi
}

# ---------------------------------------------------------------- ① 平台服务器
step_bs() {
  # 注意：macOS bash 3.2 + set -u 下展开**空数组**（echo "${a[@]}"）会报
  # "a[@]: unbound variable"，所以每个分支都必须先判 ${#...[@]} 再展开，不能图省事统一展开。
  # 同理 lib.sh 的 LIB_EXCLUDE_STATE 保留了 *.swp 占位项而不是留空。
  if [ ${#PASS_ARGS[@]} -gt 0 ]; then
    bash "$ROOT/platform/bs-deploy/update.sh" "${PASS_ARGS[@]}"
  else
    bash "$ROOT/platform/bs-deploy/update.sh"
  fi
}

# ---------------------------------------------------------------- ② 云端服务
# 云端不在 rsync 覆盖范围（装在 /opt/cloud-agent 与数据面目录），按文件 md5
# 比对增量覆盖：无变更不动，有变更先备份远端再覆盖并重启对应服务。
CLOUD_SERVER="${PLATFORM_SSH:-root@36.151.146.71}"
CLOUD_AGENT_DIR="${CLOUD_AGENT_DIR:-/opt/cloud-agent}"
CLOUD_DATA_DIR="${DATA_TERMINAL_DIR:-/root/qzb/jianpai/data-terminal}"

_cloud_sync_one() {  # _cloud_sync_one <本地文件> <远端路径> <systemd 服务名>
  local src="$1" dst="$2" svc="$3" name lh rh ts
  name="$(basename "$dst")"
  if command -v md5sum >/dev/null 2>&1; then lh=$(md5sum "$src" | cut -d' ' -f1); else lh=$(md5 -q "$src"); fi
  rh=$(ssh_run "$CLOUD_SERVER" "md5sum '$dst' 2>/dev/null | cut -d' ' -f1" 2>/dev/null || true)
  if [ -z "$rh" ]; then
    echo "    · 远端无 ${dst}（该组件未部署？）→ 跳过；全新部署请用 ./deploy.sh cloud"
    return 0
  fi
  if [ "$lh" = "$rh" ]; then
    echo "    ✔ $name 无变更"
    return 0
  fi
  ts="$(date +%Y%m%d%H%M%S)"
  ssh_run "$CLOUD_SERVER" "cp -a '$dst' '$dst.bak.$ts'" || true
  rsync_run "$src" "$CLOUD_SERVER:$dst"
  ssh_run "$CLOUD_SERVER" "systemctl restart '$svc' && sleep 3 && systemctl is-active '$svc'"
  echo "    ↳ ${name} 已更新并重启 ${svc}（远端备份：${dst}.bak.${ts}）"
}

step_cloud() {
  ssh_run "$CLOUD_SERVER" "echo ok" >/dev/null 2>&1 || {
    echo "    ⚠ 云端 $CLOUD_SERVER 不可达 → 跳过（无免密时先 export QZB_SSH_PASS='<密码>'）"
    return 1
  }
  _cloud_sync_one "$ROOT/platform/cloud-deploy/agent/cloud_agent.py"        "$CLOUD_AGENT_DIR/cloud_agent.py" "cloud-agent"
  _cloud_sync_one "$ROOT/platform/cloud-deploy/datapath/collector.py"       "$CLOUD_DATA_DIR/collector.py"    "nengtan-collector"
  _cloud_sync_one "$ROOT/platform/cloud-deploy/datapath/broker.py"          "$CLOUD_DATA_DIR/broker.py"       "nengtan-cloud-broker"
  _cloud_sync_one "$ROOT/platform/cloud-deploy/datapath/dashboard.py"       "$CLOUD_DATA_DIR/dashboard.py"    "nengtan-cloud-dashboard"
}

# ---------------------------------------------------------------- ③~⑥ 其它目标
step_middleware() {
  bash "$ROOT/platform/cloud-deploy/middleware/deploy_middleware.sh" sync --server "${PLATFORM_SSH:-root@36.151.146.71}"
}
step_docs()    { bash "$ROOT/platform/doc-deploy/update.sh"; }
step_portal()  { bash "$ROOT/platform/portal-deploy/update.sh"; }
step_nginx()   { bash "$ROOT/platform/nginx-deploy/deploy.sh"; }
step_simsource() { # 独立模拟数据源（外部系统仿真，默认在开发机本地跑）
  if [ ${#PASS_ARGS[@]} -gt 0 ]; then
    bash "$ROOT/platform/cloud-deploy/sim-source/deploy_sim_source.sh" "${PASS_ARGS[@]}"
  else
    bash "$ROOT/platform/cloud-deploy/sim-source/deploy_sim_source.sh"
  fi
}

# ---------------------------------------------------------------- GitHub 推送
step_github() {  # step_github <提交信息> <tag（可空）>
  local msg="$1" tag="${2:-}" branch
  local remote="github"
  git remote | grep -qx "$remote" || {
    echo "❌ 未找到名为 github 的远端，请先添加："
    echo "   git remote add github https://github.com/zhibinQiu/power_simulation.git"
    return 1
  }
  if [ -n "$tag" ]; then
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "❌ tag 格式应为 v1.2.3，当前：$tag" >&2; return 1; }
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null && { echo "❌ tag ${tag} 已存在（如需覆盖请先 git tag -d ${tag}）" >&2; return 1; }
  fi
  branch="$(git rev-parse --abbrev-ref HEAD)"
  echo "    当前分支：$branch"
  if [ -n "$msg" ]; then
    git add -A
    if git diff --quiet && git diff --cached --quiet; then
      echo "    工作树无改动，跳过 commit"
    else
      git commit -q -m "$msg" && echo "    已提交：$msg"
    fi
  else
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "⚠️ 工作树有未提交改动。请先 git commit，或用 ./update.sh github \"提交信息\" 一键提交并推送。"
      git status --short
      return 1
    fi
  fi
  echo "==> 拉取远端最新并 rebase"
  git fetch "$remote"
  git rebase "$remote/$branch" || { echo "❌ rebase 冲突，请解决后 git rebase --continue，再重跑本脚本" >&2; return 1; }
  echo "==> 推送到 GitHub ($branch)"
  git push "$remote" "$branch"
  if [ -n "$tag" ]; then
    git tag "$tag"
    git push "$remote" "$tag"
    echo "✅ 已推送 tag ${tag}（约 10-15 分钟后可在 Release 页面下载安装包）"
  else
    echo "✅ 推送完成（需要打包发布时加 --tag v1.2.3）"
  fi
}

# ---------------------------------------------------------------- 执行
case "$TARGET" in
  all)
    echo "==> 全量更新：平台服务器 → 云端 → 文档站 → 官网门户 → 官网 nginx"
    run_step "① 平台服务器" step_bs
    run_step "② 云端（agent + 数据面）" step_cloud
    run_step "③ 数据中间件" step_middleware
    run_step "④ 文档站" step_docs
    run_step "⑤ 官网门户" step_portal
    run_step "⑥ 官网 nginx 网关" step_nginx
    if [ "$DO_GH" = "1" ]; then run_step "⑦ GitHub" step_github "$GH_MSG" "$GH_TAG"; fi
    echo ""
    echo "────────────────────────────────────────────"
    if [ ${#FAILED[@]} -gt 0 ]; then
      echo "⚠ 完成，但有步骤失败：${FAILED[*]}"
      exit 1
    fi
    echo "✅ 全部位置已更新（GitHub：$([ "$DO_GH" = "1" ] && echo 已推送 || echo 未推送)）"
    ;;
  bs|platform)  step_bs ;;
  cloud)        step_cloud ;;
  middleware|mw) step_middleware ;;
  docs)         step_docs ;;
  portal)       step_portal ;;
  nginx)        step_nginx ;;
  simsource|sim) step_simsource ;;
  github|gh)
    step_github "$GH_MSG" "$GH_TAG"
    ;;
  list|-l|--list|-h|--help|-help) usage ;;
  *)
    echo "[error] 未知目标：${TARGET}（./update.sh list 查看全部）" >&2
    exit 1
    ;;
esac
exit 0
