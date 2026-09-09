async def test_register_success(client):
    resp = await client.post("/auth/register", json={"name": "alice", "password": "secret123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "alice"
    assert "password" not in body  # 响应里不能有密码字段


async def test_register_duplicate(client):
    await client.post("/auth/register", json={"name": "alice", "password": "secret123"})
    resp = await client.post("/auth/register", json={"name": "alice", "password": "secret123"})
    assert resp.status_code == 409


async def test_register_invalid_payload(client):
    # 非法参数被 Pydantic 拦下,422 而不是 500
    resp = await client.post("/auth/register", json={"name": "", "password": "123"})
    assert resp.status_code == 422


async def test_login_ok_and_wrong_password(client):
    await client.post("/auth/register", json={"name": "bob", "password": "secret123"})
    ok = await client.post("/auth/login", json={"name": "bob", "password": "secret123"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await client.post("/auth/login", json={"name": "bob", "password": "nope"})
    assert bad.status_code == 401


async def test_chats_require_auth(client):
    resp = await client.get("/chats")
    assert resp.status_code == 401
