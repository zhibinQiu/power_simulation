# 钢铁碳监测数字孪生平台 - 后端镜像
# 源码通过 volume 映射进容器（见 docker-compose.yml），镜像本身只安装 Python 依赖，
# 因此修改映射目录里的源码后，容器内的 uvicorn --reload 会自动重启生效。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 仅拷贝并安装依赖；应用源码由挂载卷提供
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

EXPOSE 8010

# exec 使 uvicorn 成为 PID 1，便于接收 SIGTERM 优雅停机
# --reload 监听映射进容器的源码，改动即自动重启
CMD ["sh", "-c", "cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload"]
