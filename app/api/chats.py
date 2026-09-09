import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, get_owned_chat
from app.llm import chat_reply
from app.models import Chat, Message, User
from app.redis_client import message_cache_key, redis_client
from app.schemas import ChatCreate, ChatOut, MessageCreate, MessageOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chats"])

HISTORY_LIMIT = 20  # 每次带进 LLM 的最近消息条数,超了截断
MESSAGE_CACHE_TTL = 60  # 消息列表缓存 60 秒


@router.post("/chats", response_model=ChatOut, status_code=201)
async def create_chat(
    body: ChatCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chat = Chat(user_id=user.id, title=body.title)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/chats", response_model=list[ChatOut])
async def list_chats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(Chat).where(Chat.user_id == user.id).order_by(Chat.created_at.desc())
    )
    return result.all()


@router.get("/chats/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_chat(chat_id, user, db)

    # 先查 Redis 缓存;缓存挂了只降级,不报错
    try:
        cached = await redis_client.get(message_cache_key(chat_id))
        if cached:
            return [MessageOut(**m) for m in json.loads(cached)]
    except Exception as e:
        logger.warning("Redis 读取失败,降级查库: %s", e)

    result = await db.scalars(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    messages = result.all()
    try:
        await redis_client.set(
            message_cache_key(chat_id),
            json.dumps([MessageOut.model_validate(m).model_dump(mode="json") for m in messages]),
            ex=MESSAGE_CACHE_TTL,
        )
    except Exception as e:
        logger.warning("Redis 回填失败: %s", e)
    return messages


@router.post("/chats/{chat_id}/messages", response_model=list[MessageOut], status_code=201)
async def send_message(
    chat_id: int,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_chat(chat_id, user, db)

    # 1. 保存用户消息
    user_msg = Message(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()

    # 2. 取最近历史,拼成 LLM 消息格式
    history = await db.scalars(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    llm_messages = [
        {"role": m.role, "content": m.content} for m in reversed(history.all())
    ]

    # 3. 调 LLM,失败则 502 但用户消息已落库
    try:
        reply = await chat_reply(llm_messages)
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        await db.commit()  # 保住用户消息
        raise HTTPException(status_code=502, detail="LLM 调用失败,请稍后重试")

    assistant_msg = Message(chat_id=chat_id, role="assistant", content=reply)
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    # 新消息落库,失效该会话的消息缓存
    try:
        await redis_client.delete(message_cache_key(chat_id))
    except Exception as e:
        logger.warning("Redis 失效失败: %s", e)
    return [user_msg, assistant_msg]
