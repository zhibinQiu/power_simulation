#!/usr/bin/env bash
# 同步脚本：把源码 + 构建产物推送到服务器，同时提交并推送到 gitee 云端仓库。
# 用法：bash sync.sh
set -euo pipefail
cd "$(dirname "$0")"

SERVER="root@172.19.134.45"
SERVER_DIR="/root/qzb/jianpai"
GIT_REMOTE="origin"
GIT_BRANCH="master"

echo "==> [1/3] rsync 源码 + 构建产物到服务器 $SERVER:$SERVER_DIR"
rsync -az \
  -e "ssh -p 22 -o StrictHostKeyChecking=no -o BatchMode=yes" \
  --exclude='.DS_Store' --exclude='node_modules' --exclude='.playwright-cli' \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.workbuddy' \
  --exclude='outputs' --exclude='generated-images' --exclude='*.log' \
  --exclude='chrome_*' --exclude='diag_scene.png' --exclude='void_industrial.png' \
  ./ "$SERVER:$SERVER_DIR/"
echo "    rsync 完成"

echo "==> [2/3] git 提交本地改动（源码进 gitee，构建产物 dist 已被 .gitignore 忽略）"
git add .
if git diff --cached --quiet; then
  echo "    无本地改动，跳过提交"
else
  git commit -q -m " 增加windows/mac打包代码"
  echo "已提交"
fi

echo "==> [3/3] 推送到 gitee 云端仓库"
git push "$GIT_REMOTE" "$GIT_BRANCH"
echo "    推送完成"

echo "==> 全部完成。服务器: http://<服务器IP>:40014  云端: https://gitee.com/qiuzhibin/power_simulation"
