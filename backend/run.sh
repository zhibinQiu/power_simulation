#!/usr/bin/env bash
# 启动后端服务（含前端静态托管，前端需先 npm run build）
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -r requirements.txt
fi
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
