FROM python:3.13-slim

WORKDIR /app

# 先拷依赖清单再安装,利用构建缓存:代码改了不用重装依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# 拷代码
COPY app ./app
COPY static ./static
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# 容器启动时:先跑迁移再起服务(演示用;生产一般由发布流程单独跑迁移)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
