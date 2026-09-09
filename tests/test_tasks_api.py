from sqlalchemy import select

from app.db import async_session
from app.models import Chat, Task
from app.worker import process_summary


async def test_summary_task_503_when_mq_down(client, auth_headers, db_session):
    # MQ 端口不存在 → 接口 503,任务行标记为 failed(可追溯)
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    resp = await client.post(f"/chats/{chat_id}/summary", headers=auth_headers)
    assert resp.status_code == 503

    task = (await db_session.scalars(select(Task))).one()
    assert task.status == "failed"
    assert "消息队列" in task.error


async def test_get_task_404_and_ownership(client, auth_headers):
    # 不存在的任务 → 404
    assert (await client.get("/tasks/999", headers=auth_headers)).status_code == 404

    # 注册另一个用户 mallory,造一个属于她的任务,tester 访问应 404(归属校验)
    await client.post("/auth/register", json={"name": "mallory", "password": "secret123"})
    from app.models import User

    async with async_session() as s:
        mallory = (await s.execute(select(User).where(User.name == "mallory"))).scalar_one()
        chat = Chat(user_id=mallory.id, title="mallory 的会话")
        s.add(chat)
        await s.flush()
        task = Task(chat_id=chat.id, type="chat_summary", status="pending")
        s.add(task)
        await s.commit()
        await s.refresh(task)
        task_id = task.id

    resp = await client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_worker_marks_failed_without_llm(client, auth_headers):
    """worker 核心逻辑:LLM 不可用时任务置 failed 而不是卡死。"""
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]
    await client.post(f"/chats/{chat_id}/messages", json={"content": "hello"}, headers=auth_headers)

    async with async_session() as s:
        task = Task(chat_id=chat_id, type="chat_summary", status="pending")
        s.add(task)
        await s.commit()
        await s.refresh(task)
        task_id = task.id

    await process_summary(task_id)  # 不抛异常,内部兜住

    async with async_session() as s:
        task = await s.get(Task, task_id)
        assert task.status == "failed"
        assert task.finished_at is not None
