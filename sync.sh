#!/usr/bin/env bash
# 同步脚本：把源码 + 构建产物推送到服务器，同时提交并推送到 GitHub 云端仓库。
# 用法：bash sync.sh
set -euo pipefail
cd "$(dirname "$0")"

SERVER="root@172.19.134.45"
SERVER_DIR="/root/qzb/jianpai"
GIT_REMOTE="github"
GIT_BRANCH="master"

if ! git remote | grep -qx "$GIT_REMOTE"; then
  echo "❌ 未找到名为 '$GIT_REMOTE' 的远端，请先添加 GitHub 仓库："
  echo "   git remote add github https://github.com/<你的账号>/power_simulation.git"
  exit 1
fi

echo "==> [1/3] rsync 源码 + 构建产物到服务器 $SERVER:$SERVER_DIR"
rsync -az \
  -e "ssh -p 22 -o StrictHostKeyChecking=no -o BatchMode=yes" \
  --exclude='.DS_Store' --exclude='node_modules' --exclude='.playwright-cli' \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.workbuddy' \
  --exclude='outputs' --exclude='generated-images' --exclude='*.log' \
  --exclude='chrome_*' --exclude='diag_scene.png' --exclude='void_industrial.png' \
  ./ "$SERVER:$SERVER_DIR/"
echo "    rsync 完成"

echo "==> [2/3] git 提交本地改动（源码进 GitHub，构建产物 dist 已被 .gitignore 忽略）"
git add .
if git diff --cached --quiet; then
  echo "    无本地改动，跳过提交"
else
  git commit -q -m " 更新wrokflow逻辑，更新文档"
  echo "已提交"
fi

echo "==> [3/3] 推送到 GitHub 云端仓库"
git push "$GIT_REMOTE" "$GIT_BRANCH"
echo "    推送完成"

echo "==> 全部完成。服务器: http://<服务器IP>:40014  云端: https://github.com/zhibinQiu/power_simulation"
