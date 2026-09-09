import aio_pika

from app.config import settings

QUEUE_NAME = "chat_summary"


async def publish_task(task_id: int) -> None:
    """把任务 id 发到 RabbitMQ。durable 队列 + persistent 消息:重启不丢。

    用 connect(非 robust):broker 不可用时立即抛错,接口快速返回 503,
    而不是重试半天把用户挂住。
    """
    conn = await aio_pika.connect(settings.rabbitmq_url)
    async with conn:
        channel = await conn.channel()
        await channel.declare_queue(QUEUE_NAME, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                str(task_id).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=QUEUE_NAME,
        )
