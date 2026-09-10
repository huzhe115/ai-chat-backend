import time

import redis.asyncio as aioredis

from app.config import settings

# Redis 探到挂了之后,多久内直接跳过它(熔断窗口)
REDIS_DOWN_FOR = 30


class RedisCircuit:
    """带熔断的 Redis 客户端:一次调用失败后 30 秒内全部跳过,直走降级查库。

    为什么:Redis 没开时,每次读消息列表都白等 1 秒连接超时,
    切会话/登录都会卡一下。熔断后只有第一次探活付 1 秒,后面全是毫秒级。
    """

    def __init__(self, url: str):
        self._client = aioredis.from_url(
            url,
            decode_responses=True,  # 读写都是 str,不用手动 decode
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        self._down_until = 0.0

    def _skip(self) -> bool:
        return time.monotonic() < self._down_until

    async def _call(self, method: str, *args, **kwargs):
        if self._skip():
            return None
        try:
            return await getattr(self._client, method)(*args, **kwargs)
        except Exception:
            self._down_until = time.monotonic() + REDIS_DOWN_FOR
            return None

    async def get(self, key: str):
        return await self._call("get", key)

    async def set(self, key: str, value: str, ex: int | None = None):
        return await self._call("set", key, value, ex=ex)

    async def delete(self, key: str):
        return await self._call("delete", key)


redis_client = RedisCircuit(settings.redis_url)


def message_cache_key(chat_id: int) -> str:
    return f"chat:{chat_id}:messages"
