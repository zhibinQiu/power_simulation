#!/usr/bin/env bash
# 仓库根 · 拉取远端最新代码并以 rebase 方式合入本地分支。
#
# 用法（仓库根或任意位置执行）：
#   ./pull.sh                       拉取 github/当前分支 并 rebase（有未提交改动自动 stash 再恢复）
#   ./pull.sh --remote origin       指定远端（默认 github；origin 为 gitee 镜像）
#   ./pull.sh --branch master       指定远端分支（默认当前分支同名）
#   ./pull.sh --no-stash            有未提交改动时直接退出，不自动 stash
#   ./pull.sh --no-build            拉取后不自动构建前端产物
#   ./pull.sh --abort               放弃一次冲突中的 rebase（git rebase --abort）
#
# 流程：检查 rebase 状态 -> （可选）stash 本地改动 -> fetch -> rebase -> （可选）stash pop
#      -> 若前端/文档站源码有变更则自动 npx vite build
set -euo pipefail
cd "$(dirname "$0")"   # 本脚本位于仓库根（git 根）

# ---- 参数 ----
GIT_REMOTE=""
BRANCH=""
DO_STASH=1
DO_BUILD=1
DO_ABORT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --remote) GIT_REMOTE="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --no-stash) DO_STASH=0; shift ;;
    --no-build) DO_BUILD=0; shift ;;
    --abort) DO_ABORT=1; shift ;;
    -h|--help)
      awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
      exit 0 ;;
    *) echo "❌ 未知参数: $1（用 -h 查看用法）"; exit 1 ;;
  esac
done

# ---- 基础检查 ----
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ 当前目录不是 git 仓库"; exit 1
fi

# ---- 放弃冲突中的 rebase ----
if [ "$DO_ABORT" = "1" ]; then
  if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
    git rebase --abort
    echo "✅ 已放弃本次 rebase，工作树回到 rebase 前状态。"
  else
    echo "ℹ️ 当前没有进行中的 rebase，无需 --abort。"
  fi
  exit 0
fi

if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
  echo "❌ 存在未完成的 rebase。请先处理冲突后 'git rebase --continue'，或用 '$0 --abort' 放弃。"
  exit 1
fi

# ---- 远端 / 分支 ----
if [ -z "$GIT_REMOTE" ]; then
  if git remote | grep -qx "github"; then GIT_REMOTE="github"; else GIT_REMOTE="$(git remote | head -n 1)"; fi
fi
if ! git remote | grep -qx "$GIT_REMOTE"; then
  echo "❌ 未找到远端 '$GIT_REMOTE'。可用远端: $(git remote | tr '\n' ' ')"
  exit 1
fi
if [ -z "$BRANCH" ]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$BRANCH" = "HEAD" ]; then
    echo "❌ 当前处于 detached HEAD，请先用 --branch <分支名> 指定要 rebase 到的分支。"
    exit 1
  fi
fi

OLD_HEAD="$(git rev-parse HEAD)"
echo "==> 远端: ${GIT_REMOTE}/${BRANCH}   本地分支: $(git rev-parse --abbrev-ref HEAD)"

# ---- 暂存本地未提交改动（含未跟踪文件；.gitignore 忽略的 node_modules/dist 不受影响）----
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  if [ "$DO_STASH" = "0" ]; then
    echo "❌ 工作树有未提交改动，已按 --no-stash 要求中止。请先提交或 'git stash'。"
    git status --short
    exit 1
  fi
  echo "==> 发现未提交改动，自动暂存（git stash -u）"
  git stash push -u -m "pull.sh auto stash $(date '+%Y-%m-%d %H:%M:%S')" >/dev/null
  STASHED=1
fi

# ---- 拉取并 rebase ----
echo "==> fetch ${GIT_REMOTE}"
git fetch --prune "$GIT_REMOTE"

if ! git rev-parse --verify -q "${GIT_REMOTE}/${BRANCH}" >/dev/null; then
  echo "❌ 远端分支 ${GIT_REMOTE}/${BRANCH} 不存在。"
  [ "$STASHED" = "1" ] && echo "   本地改动仍在 stash 中，用 'git stash pop' 恢复。"
  exit 1
fi

if [ "$(git rev-parse HEAD)" = "$(git rev-parse "${GIT_REMOTE}/${BRANCH}")" ]; then
  echo "   已是最新，无需 rebase。"
else
  echo "==> rebase 到 ${GIT_REMOTE}/${BRANCH}"
  if ! git rebase "${GIT_REMOTE}/${BRANCH}"; then
    echo "❌ rebase 产生冲突。解决冲突后执行："
    echo "     git add -A && git rebase --continue"
    echo "   或放弃本次 rebase： git rebase --abort"
    [ "$STASHED" = "1" ] && echo "   注意：本地改动仍在 stash 中，rebase 结束后执行 'git stash pop' 恢复。"
    exit 1
  fi
fi

# ---- 恢复本地改动 ----
if [ "$STASHED" = "1" ]; then
  echo "==> 恢复暂存的本地改动"
  if ! git stash pop; then
    echo "❌ stash pop 冲突，本地改动仍在 stash（git stash list）。请手动解决后 'git stash drop'。"
    exit 1
  fi
fi

# ---- 结果摘要 ----
echo "==> 更新内容："
git --no-pager log --oneline "${OLD_HEAD}..HEAD" | sed 's/^/    /' || true
echo "   变更文件数: $(git diff --name-only "${OLD_HEAD}" HEAD | wc -l | tr -d ' ')"

# ---- 前端/文档站产物自动构建（源码有变更才构建，失败不阻断）----
if [ "$DO_BUILD" = "1" ]; then
  CHANGED="$(git diff --name-only "${OLD_HEAD}" HEAD)"
  if echo "$CHANGED" | grep -q '^frontend/src/' && [ -d frontend/node_modules ]; then
    echo "==> frontend/src 有变更，重新构建 frontend/dist"
    (cd frontend && npx vite build >/dev/null 2>&1) && echo "    frontend/dist 已构建" \
      || echo "    ⚠ frontend 构建失败（检查 node_modules / vite）"
  fi
  if echo "$CHANGED" | grep -q '^platform/doc-deploy/docs-site/src/' && [ -d platform/doc-deploy/docs-site/node_modules ]; then
    echo "==> docs-site/src 有变更，重新构建 docs-site/dist"
    (cd platform/doc-deploy/docs-site && npx vite build >/dev/null 2>&1) && echo "    docs-site/dist 已构建" \
      || echo "    ⚠ docs-site 构建失败（检查 node_modules / vite）"
  fi
fi

echo "✅ 完成：已同步到 ${GIT_REMOTE}/${BRANCH}"
