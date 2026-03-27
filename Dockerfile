# ── 阶段 1：构建前端 ──
FROM node:18-alpine AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# ── 阶段 2：后端 ──
FROM python:3.12-slim AS backend
WORKDIR /app

# 安装系统依赖
# curl 用于 healthcheck；adb 用于控制 USB 连接的安卓设备
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖声明，利用 Docker 缓存层
COPY pyproject.toml .

# 复制源码（pip install 需要完整包结构）
COPY core/ core/
COPY api/ api/
COPY cli/ cli/
COPY plugins/ plugins/
COPY main.py .
COPY config.yaml .

# 仅安装生产依赖
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── 阶段 3：Nginx 带前端产物 ──
FROM nginx:alpine AS nginx
RUN mkdir -p /etc/nginx/snippets
COPY --from=frontend /web/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
