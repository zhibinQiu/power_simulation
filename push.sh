#!/usr/bin/env bash
# 仓库根 · 通用推送脚本（纯 git 操作，不含服务器部署）。
#
# 供仓库协作者 / 开发机 / 服务器统一使用：把代码改动提交并推送到 GitHub。
# platform/update.sh push 与 platform/bs-deploy/update.sh push 均调用本脚本。
#
# 用法（仓库根任意位置执行）：
#   ./push.sh                                    仅推送（要求工作树已提交）
#   ./push.sh "fix: xxx"                         提交 + 推送
#   ./push.sh "fix: xxx" --tag v1.0.0            提交 + 打 tag + 推送（触发 GitHub Actions 打包发布 Release）
#
# 流程：拉取远端最新并 rebase -> 推送到 GitHub 当前分支 -> （可选）推 tag 触发打包。
set -euo pipefail
cd "$(dirname "$0")"   # 本脚本位于仓库根（git 根）

# 推送目标：GitHub 远端（命名约定为 github）
GIT_REMOTE="github"
if ! git remote | grep -qx "$GIT_REMOTE"; then
  echo "❌ 未找到名为 '$GIT_REMOTE' 的远端，请先添加 GitHub 仓库："
  echo "   git remote add github https://github.com/zhibinQiu/power_simulation.git"
  exit 1
fi

# ---- 解析参数：MSG 为提交信息，--tag <版本> 触发打包发布 ----
MSG=""
TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag)
      if [ $# -lt 2 ]; then
        echo "❌ --tag 需要一个版本号，如：./push.sh \"msg\" --tag v1.0.0"
        exit 1
      fi
      TAG="$2"
      shift 2
      ;;
    *)
      MSG="$1"
      shift
      ;;
  esac
done

if [ -n "$TAG" ]; then
  if ! [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ tag 格式应为 v1.2.3，当前: $TAG"
    exit 1
  fi
  if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "❌ tag '$TAG' 已存在（本地），如需覆盖请先手动删除：git tag -d $TAG"
    exit 1
  fi
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> 当前分支: $BRANCH"

# ---- 提交 ----
if [ -n "$MSG" ]; then
  git add -A
  git commit -q -m "$MSG"
  echo "    已提交: $MSG"
else
  # 无提交信息：要求工作树已提交，避免把半成品推上去
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "⚠️ 工作树有未提交改动。请先 'git commit'，或用 './push.sh \"提交信息\"' 一键提交并推送。"
    git status --short
    exit 1
  fi
fi

# ---- 拉取远端最新并 rebase ----
echo "==> 拉取远端最新并 rebase"
git fetch "$GIT_REMOTE"
if git rebase "$GIT_REMOTE/$BRANCH"; then
  echo "    rebase 完成"
else
  echo "❌ rebase 产生冲突，请手动解决后 'git rebase --continue'，再运行本脚本。"
  exit 1
fi

# ---- 推代码 ----
echo "==> 推送到 GitHub ($BRANCH)"
git push "$GIT_REMOTE" "$BRANCH"

# ---- 可选：打 tag 并推送，触发 GitHub Actions 自动打包发布 ----
if [ -n "$TAG" ]; then
  echo "==> 打 tag $TAG 并推送（将触发 GitHub Actions 打包并发布 Release）"
  git tag "$TAG"
  git push "$GIT_REMOTE" "$TAG"
  echo "✅ 已推送 tag ${TAG}。约 10-15 分钟后可在仓库 Release 页面下载安装包。"
else
  echo "✅ 推送完成。若是功能分支，请到 GitHub 发起 Pull Request 合并到 master。"
  echo "   （需要打包发布时加 --tag，如：./push.sh \"msg\" --tag v1.0.0）"
fi
