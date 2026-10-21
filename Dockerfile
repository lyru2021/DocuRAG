
# DocuRAG API 与 Celery Worker 共用的 Python 运行镜像。
FROM python:3.11-slim

# 运行时环境变量。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 设置工作目录。
WORKDIR /app

# 安装构建和运行所需的基础依赖。
# libmagic1 用于部分文件类型识别场景。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 优先复制依赖清单，利用 Docker 构建缓存。
COPY requirements.txt .

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# 复制项目代码及数据库迁移配置。
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 容器中的上传目录。
RUN mkdir -p /app/data/uploads

# API 默认监听端口。
EXPOSE 8000

# 后续 Compose 可覆盖此命令启动 Celery Worker/Beat。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
