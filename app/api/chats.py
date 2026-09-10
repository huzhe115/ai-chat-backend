import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, get_owned_chat
from app.llm import chat_reply, stream_reply
from app.models import Chat, Message, User
from app.redis_client import message_cache_key, redis_client
from app.schemas import ChatCreate, ChatOut, MessageCreate, MessageOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chats"])

HISTORY_LIMIT = 20  # 每次带进 LLM 的最近消息条数,超了截断
MESSAGE_CACHE_TTL = 60  # 消息列表缓存 60 秒


def _sse(data: dict) -> str:
    """把一个事件包成 SSE 帧(空行是事件边界)。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _msg_dict(m: Message) -> dict:
    return MessageOut.model_validate(m).model_dump(mode="json")


async def _prepare_message(db: AsyncSession, chat_id: int, content: str):
    """保存用户消息,并返回拼给 LLM 的最近历史。"""
    user_msg = Message(chat_id=chat_id, role="user", content=content)
    db.add(user_msg)
    await db.flush()

    # 首条消息把默认标题"新会话"改成话题标题(截断前 16 字,像 DeepSeek 侧栏)
    chat = await db.get(Chat, chat_id)
    if chat is not None and chat.title == "新会话":
        flat = " ".join(content.split())
        chat.title = flat[:16] + ("…" if len(flat) > 16 else "")

    history = await db.scalars(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    llm_messages = [
        {"role": m.role, "content": m.content} for m in reversed(history.all())
    ]
    return user_msg, llm_messages


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


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除会话:消息/任务由外键 ondelete=CASCADE 在数据库层连带删除。"""
    chat = await get_owned_chat(chat_id, user, db)
    await db.delete(chat)
    await db.commit()
    try:
        await redis_client.delete(message_cache_key(chat_id))
    except Exception as e:
        logger.warning("Redis 失效失败: %s", e)


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
            json.dumps([_msg_dict(m) for m in messages]),
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

    # 1. 保存用户消息,并取最近历史拼成 LLM 消息格式
    user_msg, llm_messages = await _prepare_message(db, chat_id, body.content)

    # 2. 调 LLM,失败则 502 但用户消息已落库
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


@router.post("/chats/{chat_id}/messages/stream")
async def send_message_stream(
    chat_id: int,
    body: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式版发消息:SSE 逐段推给前端,边生成边显示。

    事件序列: {"user_msg": {...}} → {"delta": "..."} × N →
    正常: {"assistant_msg": {...}} / 出错: {"error": "..."}
    """
    await get_owned_chat(chat_id, user, db)
    user_msg, llm_messages = await _prepare_message(db, chat_id, body.content)
    await db.commit()  # 用户消息先落库,第一条事件就带真实 id
    await db.refresh(user_msg)

    async def event_gen():
        # ponytail: 一次流式占用一个 db session 直到结束,个人项目够用,
        # 并发上来再换独立 session/连接池
        yield _sse({"user_msg": _msg_dict(user_msg)})
        chunks: list[str] = []
        try:
            async for delta in stream_reply(llm_messages):
                chunks.append(delta)
                yield _sse({"delta": delta})
        except Exception as e:
            logger.error("LLM 流式调用失败: %s", e)
            yield _sse({"error": "LLM 调用失败,请稍后重试"})
            return  # 用户消息已落库,助手消息不保存

        assistant_msg = Message(chat_id=chat_id, role="assistant", content="".join(chunks))
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(assistant_msg)
        try:
            await redis_client.delete(message_cache_key(chat_id))
        except Exception as e:
            logger.warning("Redis 失效失败: %s", e)
        yield _sse({"assistant_msg": _msg_dict(assistant_msg)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")
