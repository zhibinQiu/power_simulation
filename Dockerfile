# 能碳智控平台 · 自包含生产镜像（多阶段）
#
# 与传统「源码卷挂载 + uvicorn --reload」开发式部署不同，本镜像将
# 后端代码 + Python 依赖 + 前端构建产物全部打进镜像：
#   - 服务器仅需 docker 构建/拉取一次，不再安装 python/node/npm/venv
#   - 容器内不带 --reload，单进程运行，省 CPU/内存
#   - 运行期可变数据（backend/data、backend/config、backend/knowledge）
#     由 docker-compose 以命名卷/目录挂载持久化，镜像更新不丢现场数据
#
# 构建：
#   docker build -t steel-carbon-twin:latest .
# 运行：见 docker-compose.yml

# ---- 阶段 1：构建前端产物（node） ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 阶段 2：运行时（python） ----
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 仅拷贝并安装依赖（先装依赖再拷代码，命中镜像层缓存）
COPY backend/config/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

# 后端代码 + 前端构建产物（由后端静态托管，FRONTEND_DIST=/app/frontend/dist）
COPY backend/ /app/backend/
COPY --from=fe /fe/dist /app/frontend/dist

EXPOSE 8010

# 生产模式：无 --reload、单进程、无 access log（FastAPI 事件循环 + MQTT 后台线程共用单 worker）
CMD ["sh", "-c", "cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8010"]
