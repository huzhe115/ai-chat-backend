import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, get_owned_chat
from app.models import Task, User
from app.mq import publish_task
from app.redis_client import redis_client
from app.schemas import TaskOut

router = APIRouter(tags=["tasks"])

logger = logging.getLogger(__name__)

TASK_CACHE_TTL = 3600  # 任务结果在 Redis 里缓存 1 小时


def task_cache_key(task_id: int) -> str:
    return f"task:{task_id}"


@router.post("/chats/{chat_id}/summary", response_model=TaskOut, status_code=202)
async def create_summary_task(
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_chat(chat_id, user, db)
    task = Task(chat_id=chat_id, type="chat_summary", status="pending")
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        await publish_task(task.id)  # API 秒回,重活交给 worker
    except Exception as e:
        logger.error("投递消息失败: %s", e)
        task.status = "failed"
        task.error = "消息队列不可用"
        await db.commit()
        raise HTTPException(status_code=503, detail="消息队列不可用")
    return task


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    await get_owned_chat(task.chat_id, user, db)  # 校验任务归属

    # 先查 Redis 缓存(worker 完成时写入);缓存不可用则退回 DB,不报错
    try:
        cached = await redis_client.get(task_cache_key(task_id))
        if cached:
            return TaskOut(**json.loads(cached))
    except Exception as e:
        logger.warning("Redis 读取失败,降级查库: %s", e)
    return task
