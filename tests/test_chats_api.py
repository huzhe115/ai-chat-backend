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
