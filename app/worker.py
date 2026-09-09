"""RabbitMQ 消费者:独立进程,消费 chat_summary 队列,调 LLM 生成会话摘要。

启动:uv run python -m app.worker
"""
import asyncio
import json
import logging
from datetime import UTC, datetime

import aio_pika
from sqlalchemy import select

from app.api.tasks import TASK_CACHE_TTL, task_cache_key
from app.config import settings
from app.db import async_session
from app.llm import chat_reply
from app.models import Message, Task
from app.mq import QUEUE_NAME
from app.redis_client import redis_client

SUMMARY_PROMPT = "你是会话摘要助手。用简洁中文总结下面的对话要点,不超过 200 字。"

logger = logging.getLogger(__name__)


async def process_summary(task_id: int) -> None:
    async with async_session() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return
        task.status = "running"
        await db.commit()

        messages = await db.scalars(
            select(Message).where(Message.chat_id == task.chat_id).order_by(Message.created_at)
        )
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages.all())

        try:
            summary = await chat_reply(
                [
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": transcript},
                ]
            )
            task.status = "done"
            task.result = summary
        except Exception as e:
            logger.error("摘要生成失败: %s", e)
            task.status = "failed"
            task.error = str(e)[:500]
        task.finished_at = datetime.now(UTC)
        await db.commit()

        # 结果写进 Redis 缓存,GET /tasks/{id} 轮询时直接命中
        if task.status == "done":
            try:
                from app.schemas import TaskOut

                cached = TaskOut.model_validate(task).model_dump(mode="json")
                await redis_client.set(task_cache_key(task_id), json.dumps(cached), ex=TASK_CACHE_TTL)
            except Exception as e:
                logger.warning("Redis 写入失败: %s", e)  # 缓存只是加速,失败不影响主流程


async def main() -> None:
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=1)  # 一次只取一条,防止单个 worker 堆积

    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    print(f"[worker] 监听队列 {QUEUE_NAME} ...")
    async with queue.iterator() as it:
        async for message in it:
            # with 块正常退出 = ack;抛异常 = nack 重新入队
            async with message.process():
                task_id = int(message.body)
                print(f"[worker] 开始处理任务 {task_id}")
                await process_summary(task_id)
                print(f"[worker] 任务 {task_id} 完成")


if __name__ == "__main__":
    asyncio.run(main())
