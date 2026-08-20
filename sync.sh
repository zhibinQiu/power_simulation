#!/usr/bin/env bash
# 同步脚本：把源码 + 构建产物推送到服务器，同时提交并推送到 GitHub 云端仓库。
#
# 用法：
#   bash sync.sh                            rsync + 提交（默认提交信息）+ 推送
#   bash sync.sh "fix: xxx"                 rsync + 提交（指定信息）+ 推送
#   bash sync.sh "fix: xxx" --tag v1.0.0    rsync + 提交 + 打 tag + 推送（触发 GitHub Actions 打包发布 Release）
set -euo pipefail
cd "$(dirname "$0")"

SERVER="root@172.19.134.45"
SERVER_DIR="/root/qzb/jianpai"
GIT_REMOTE="github"
GIT_BRANCH="master"

if ! git remote | grep -qx "$GIT_REMOTE"; then
  echo "❌ 未找到名为 '$GIT_REMOTE' 的远端，请先添加 GitHub 仓库："
  echo "   git remote add github https://github.com/zhibinQiu/power_simulation.git"
  exit 1
fi

# ---- 解析参数：MSG 为提交信息（可选），--tag <版本> 触发打包发布 ----
MSG=""
TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag)
      if [ $# -lt 2 ]; then
        echo "❌ --tag 需要一个版本号，如：bash sync.sh \"msg\" --tag v1.0.0"
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

if [ -z "$MSG" ]; then
  MSG="sync: 更新代码"
fi

# echo "==> [1/3] rsync 源码 + 构建产物到服务器 $SERVER:$SERVER_DIR"
# rsync -az \
#   -e "ssh -p 22 -o StrictHostKeyChecking=no -o BatchMode=yes" \
#   --exclude='.DS_Store' --exclude='node_modules' --exclude='.playwright-cli' \
#   --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.workbuddy' \
#   --exclude='outputs' --exclude='generated-images' --exclude='*.log' \
#   --exclude='chrome_*' --exclude='diag_scene.png' --exclude='void_industrial.png' \
#   ./ "$SERVER:$SERVER_DIR/"
# echo "    rsync 完成"

echo "==> [2/3] git 提交本地改动（源码进 GitHub，构建产物 dist 已被 .gitignore 忽略）"
git add .
if git diff --cached --quiet; then
  echo "    无本地改动，跳过提交"
else
  git commit -q -m "$MSG"
  echo "    已提交: $MSG"
fi

echo "==> [3/3] 推送到 GitHub 云端仓库"
git pull --rebase "$GIT_REMOTE" "$GIT_BRANCH" 2>/dev/null || true
git push "$GIT_REMOTE" "$GIT_BRANCH"
echo "    推送完成"

if [ -n "$TAG" ]; then
  echo "==> 打 tag $TAG 并推送（将触发 GitHub Actions 打包并发布 Release）"
  git tag "$TAG"
  git push "$GIT_REMOTE" "$TAG"
  echo "✅ 已推送 tag。约 10-15 分钟后可在仓库 Release 页面下载安装包。"
fi

echo "==> 全部完成。"
