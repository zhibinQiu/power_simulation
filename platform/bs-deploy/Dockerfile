# 能碳智控平台 · 后端运行环境镜像（源码卷挂载 + uvicorn --reload 模式）
#
# 本镜像只固化「Python 运行环境 + 依赖」，不含业务代码与前端产物：
#   - backend/       由 docker-compose 卷挂载到 /app/backend
#                     （改 .py → uvicorn --reload 秒级生效，无需重建镜像）
#   - frontend/dist  卷挂载到 /app/frontend/dist（后端静态托管；
#                     前端改 → 本地 npx vite build 后随 rsync 同步即可）
# 因此日常更新代码后容器无需重建；仅当 requirements.txt / Dockerfile /
# docker-compose.yml 变更时才需 docker compose up -d --build。
#
# 构建（build context 恒为仓库根；.dockerignore 也在仓库根）：
#   cd <仓库根>/platform/bs-deploy && docker compose up -d --build
#   （或：cd <仓库根> && docker build -f platform/bs-deploy/Dockerfile -t steel-carbon-twin:latest .）
# 运行：见同目录 docker-compose.yml
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 仅拷贝依赖清单并安装（requirements 不变时命中镜像层缓存，build 秒级）
COPY backend/config/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

EXPOSE 8010

# 源码卷挂载模式：--reload 监视 /app/backend（卷挂载，宿主编译/同步即自动重载），
# 仅监视后端目录，不因前端静态产物变化而重启；
# FastAPI 事件循环 + MQTT 后台线程共用单 worker。
CMD ["sh", "-c", "cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload --reload-dir /app/backend --no-access-log"]
