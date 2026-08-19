#!/usr/bin/env bash
# 协作者推送脚本（纯 git，不含服务器部署）。
# 用法：
#   ./push.sh              仅推送（要求工作树已提交）
#   ./push.sh "fix: xxx"   先把所有改动提交，再推送
# 流程：拉取远端最新并 rebase -> 推送到 Gitee 当前分支。
set -euo pipefail
cd "$(dirname "$0")"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> 当前分支: $BRANCH"

# 若带提交信息参数：先 stage + commit
if [ -n "${1:-}" ]; then
  git add -A
  git commit -q -m "$1"
  echo "    已提交: $1"
else
  # 无参数：要求工作树已提交，避免把半成品推上去
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "⚠️ 工作树有未提交改动。请先 'git commit'，或用 './push.sh \"提交信息\"' 一键提交并推送。"
    git status --short
    exit 1
  fi
fi

echo "==> 拉取远端最新并 rebase"
git fetch origin
if git rebase "origin/$BRANCH"; then
  echo "    rebase 完成"
else
  echo "❌ rebase 产生冲突，请手动解决后 'git rebase --continue'，再运行本脚本。"
  exit 1
fi

echo "==> 推送到 Gitee ($BRANCH)"
git push origin "$BRANCH"
echo "✅ 推送完成。若是功能分支，请到 Gitee 发起 Pull Request 合并到 master。"
