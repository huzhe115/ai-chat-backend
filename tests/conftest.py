import os

# 必须在导入 app 之前设置:测试用独立数据库 + 不存在的 Redis/MQ 端口
# (缓存和队列挂了代码会自动降级,正好测到降级路径)
# setdefault:CI 里注入的环境变量优先,本地没有才用默认值
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:123456@localhost:5432/ai_chat_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6399/0")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5999/")
os.environ.setdefault("LLM_API_KEY", "")  # 空 key:LLM 调用立即报错,测试不依赖外部服务

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import Base, async_session, engine
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """每个测试前重建所有表,测试之间互不污染。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    """注册一个用户并登录,返回带 token 的请求头。"""
    await client.post("/auth/register", json={"name": "tester", "password": "secret123"})
    resp = await client.post("/auth/login", json={"name": "tester", "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def db_session():
    async with async_session() as session:
        yield session
