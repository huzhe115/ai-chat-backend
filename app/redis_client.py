import redis.asyncio as aioredis

from app.config import settings

# decode_responses=True:读写都是 str,不用手动 decode
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


def message_cache_key(chat_id: int) -> str:
    return f"chat:{chat_id}:messages"
