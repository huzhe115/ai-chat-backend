import json


async def test_create_and_list_chats(client, auth_headers):
    resp = await client.post("/chats", json={"title": "学习计划"}, headers=auth_headers)
    assert resp.status_code == 201
    chat_id = resp.json()["id"]

    resp = await client.get("/chats", headers=auth_headers)
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [chat_id]


async def test_send_message_saves_user_message_when_llm_fails(client, auth_headers):
    # LLM key 为空 → 回复失败 502,但用户消息必须落库(不丢数据)
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    resp = await client.post(f"/chats/{chat_id}/messages", json={"content": "hi"}, headers=auth_headers)
    assert resp.status_code == 502

    history = (await client.get(f"/chats/{chat_id}/messages", headers=auth_headers)).json()
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hi"


async def test_cannot_access_others_chat(client, auth_headers):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    # 另一个用户访问同一会话 → 404(不暴露存在性)
    await client.post("/auth/register", json={"name": "mallory", "password": "secret123"})
    login = await client.post("/auth/login", json={"name": "mallory", "password": "secret123"})
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/chats/{chat_id}/messages", headers=other)
    assert resp.status_code == 404


async def test_empty_message_rejected(client, auth_headers):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]
    resp = await client.post(f"/chats/{chat_id}/messages", json={"content": ""}, headers=auth_headers)
    assert resp.status_code == 422


async def test_send_message_stream(client, auth_headers, monkeypatch):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    async def fake_stream(messages):
        # 确认拼给 LLM 的历史里最后一条就是刚发的用户消息
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "hi"
        yield "你好"
        yield ",世界"

    monkeypatch.setattr("app.api.chats.stream_reply", fake_stream)

    async with client.stream(
        "POST", f"/chats/{chat_id}/messages/stream", json={"content": "hi"}, headers=auth_headers
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = (await resp.aread()).decode()

    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert events[0]["user_msg"]["content"] == "hi"
    assert "".join(e["delta"] for e in events if "delta" in e) == "你好,世界"
    assert events[-1]["assistant_msg"]["content"] == "你好,世界"

    # 流结束后两条消息都应落库
    history = (await client.get(f"/chats/{chat_id}/messages", headers=auth_headers)).json()
    assert [m["role"] for m in history] == ["user", "assistant"]


async def test_first_message_renames_default_chat_title(client, auth_headers, monkeypatch):
    chat_id = (await client.post("/chats", json={}, headers=auth_headers)).json()["id"]  # 默认标题"新会话"

    async def fake_stream(messages):
        yield "ok"

    monkeypatch.setattr("app.api.chats.stream_reply", fake_stream)
    async with client.stream(
        "POST", f"/chats/{chat_id}/messages/stream", json={"content": "帮我写一份周报"}, headers=auth_headers
    ) as resp:
        await resp.aread()

    chats = (await client.get("/chats", headers=auth_headers)).json()
    assert chats[0]["title"] == "帮我写一份周报"


async def test_first_message_keeps_custom_title(client, auth_headers, monkeypatch):
    chat_id = (await client.post("/chats", json={"title": "我的自定义标题"}, headers=auth_headers)).json()["id"]

    async def fake_stream(messages):
        yield "ok"

    monkeypatch.setattr("app.api.chats.stream_reply", fake_stream)
    async with client.stream(
        "POST", f"/chats/{chat_id}/messages/stream", json={"content": "你好"}, headers=auth_headers
    ) as resp:
        await resp.aread()

    chats = (await client.get("/chats", headers=auth_headers)).json()
    assert chats[0]["title"] == "我的自定义标题"


async def test_delete_chat_removes_chat_and_messages(client, auth_headers, monkeypatch):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    async def fake_stream(messages):
        yield "ok"

    monkeypatch.setattr("app.api.chats.stream_reply", fake_stream)
    async with client.stream(
        "POST", f"/chats/{chat_id}/messages/stream", json={"content": "hi"}, headers=auth_headers
    ) as resp:
        await resp.aread()

    resp = await client.delete(f"/chats/{chat_id}", headers=auth_headers)
    assert resp.status_code == 204

    # 会话和消息都没了;任务表被 CASCADE 连带清理
    assert (await client.get("/chats", headers=auth_headers)).json() == []
    resp = await client.get(f"/chats/{chat_id}/messages", headers=auth_headers)
    assert resp.status_code == 404


async def test_cannot_delete_others_chat(client, auth_headers):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    await client.post("/auth/register", json={"name": "mallory", "password": "secret123"})
    login = await client.post("/auth/login", json={"name": "mallory", "password": "secret123"})
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.delete(f"/chats/{chat_id}", headers=other)
    assert resp.status_code == 404


async def test_send_message_stream_llm_error_still_saves_user_msg(client, auth_headers, monkeypatch):
    chat_id = (await client.post("/chats", json={"title": "t"}, headers=auth_headers)).json()["id"]

    async def broken_stream(messages):
        raise RuntimeError("boom")
        yield  # pragma: no cover - 让函数成为生成器

    monkeypatch.setattr("app.api.chats.stream_reply", broken_stream)

    async with client.stream(
        "POST", f"/chats/{chat_id}/messages/stream", json={"content": "hi"}, headers=auth_headers
    ) as resp:
        body = (await resp.aread()).decode()

    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert events[0]["user_msg"]["content"] == "hi"
    assert events[-1]["error"] == "LLM 调用失败,请稍后重试"

    history = (await client.get(f"/chats/{chat_id}/messages", headers=auth_headers)).json()
    assert len(history) == 1
    assert history[0]["role"] == "user"
