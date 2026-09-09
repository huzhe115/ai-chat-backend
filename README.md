# AI Chat Backend

AI 聊天应用后端服务——比特鹰成长计划「项目实战:AI 服务后端系统」。

FastAPI + PostgreSQL + Redis + RabbitMQ 的完整异步后端,支持注册登录、多轮对话(LLM 回复)、异步任务(会话摘要)和任务状态查询。

## 架构

```
浏览器/客户端
    │  HTTP
    ▼
┌─────────────┐   发布任务    ┌──────────────┐
│  api (FastAPI) │ ──────────▶ │ RabbitMQ 队列 │
│  - auth       │              │ chat_summary │
│  - chats      │              └──────┬───────┘
│  - tasks      │                     │ 消费
└──┬───────┬───┘                ┌────▼─────────┐
   │       │                    │    worker    │ ──▶ LLM API
   ▼       ▼                    └──────┬───────┘
┌────────┐ ┌───────┐                  │ 回写
│PostgreSQL│ │ Redis  │   ┌────────────────▼────┐
│ 用户/会话  │ │ 消息缓存 │   │ tasks 表 + Redis 缓存 │
│ /消息/任务 │ │ 任务缓存 │   └─────────────────────┘
└────────┘ └───────┘
```

**设计要点**

- **消息列表缓存**:`GET /chats/{id}/messages` 先查 Redis(TTL 60s),未命中查库回填;新消息落库后主动失效缓存。Redis 不可用时自动降级查库,不影响主流程。
- **异步任务**:`POST /chats/{id}/summary` 秒回 202 并返回任务 id,worker 从 RabbitMQ 消费、调 LLM 生成摘要、回写 `tasks` 表并缓存结果。durable 队列 + persistent 消息 + ack 确认,重启不丢任务。
- **错误处理**:MQ 不可用 → 接口 503 且任务标记 `failed`;LLM 失败 → 502 但用户消息已落库;缓存失败 → 降级,只记日志。
- **安全**:bcrypt 密码哈希(不存明文)、JWT 无状态鉴权、会话归属校验(越权返回 404)、Pydantic 参数校验。

## 快速开始

### 方式一:Docker Compose(一条命令)

```bash
cp .env.example .env        # 填入 LLM_API_KEY
docker compose up -d --build
```

- API 文档:http://localhost:8000/docs
- RabbitMQ 管理界面:http://localhost:15672 (guest/guest)
- 注意:宿主 5432/6379 被占用时,compose 里 PG 映射 5433、Redis 映射 6380

### 方式二:本地开发(已有本机 PostgreSQL)

```bash
# 1. 准备依赖环境:PostgreSQL + Redis + RabbitMQ(Docker 单独起)
docker run -d --name redis -p 6379:6379 redis:7
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# 2. 创建数据库并迁移
createdb ai_chat
uv sync
uv run alembic upgrade head

# 3. 起 API 和 worker(两个终端)
uv run uvicorn app.main:app --reload
uv run python -m app.worker
```

> 国内网络拉不动 Docker 镜像时:用宿主机 curl 直连镜像源下载、`docker load` 导入,或直接换网络。

## 接口示例

```bash
# 注册 / 登录
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"name":"alice","password":"secret123"}'
TOKEN=$(curl -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"name":"alice","password":"secret123"}' | jq -r .access_token)

# 建会话、发消息(LLM 回复)
CHAT=$(curl -X POST localhost:8000/chats -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"title":"闲聊"}' | jq -r .id)
curl -X POST localhost:8000/chats/$CHAT/messages -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"content":"你好"}'

# 触发异步摘要任务,轮询结果
TASK=$(curl -X POST localhost:8000/chats/$CHAT/summary \
  -H "Authorization: Bearer $TOKEN" | jq -r .id)
curl localhost:8000/tasks/$TASK -H "Authorization: Bearer $TOKEN"
```

## 测试

```bash
uv run pytest          # 16 个测试:单元 + 接口 + worker 降级路径
uv run ruff check .    # lint
```

测试设计:使用独立数据库 `ai_chat_test`(每个测试重建表,不污染数据),Redis/MQ/LLM 指向不可用的端口,**正好覆盖降级路径**——MQ 挂了返回 503、LLM 挂了消息不丢、缓存挂了查库兜底。

## Prompt 工程实践

本项目两处调用 LLM,提示词设计各有侧重:

**1. 多轮对话(`POST /chats/{id}/messages`,见 `app/api/chats.py`)**

- 每次从数据库取最近 20 条消息(`HISTORY_LIMIT`),按时间正序拼成 `messages`,保留 user/assistant 角色交替——多轮上下文是"聊得起来"的关键。
- 超长对话截断到最近 20 条:先保证上下文窗口不溢出,再谈记忆长度。
- 不硬编码人设;`app/llm.py` 的 `chat_reply` 只认 OpenAI 兼容的 `messages` 格式,换 DeepSeek/OpenAI 改 `.env` 即可,提示词与业务代码解耦。

**2. 会话摘要(worker 消费 MQ 任务,见 `app/worker.py`)**

- 固定 system 提示词:`你是会话摘要助手。用简洁中文总结下面的对话要点,不超过 200 字。`
- 一条提示词写清三件事:**角色**(摘要助手)、**任务**(总结对话要点)、**输出约束**(中文、≤200 字)——约束交给模型自己控制,比事后截断字符串省事且效果更好。
- 对话原文逐行拼成 `user: xxx` / `assistant: xxx` 作为单条 user 消息传入,让模型明确知道每句话是谁说的。

**3. 容错原则**:LLM 失败返回 502 但用户消息已落库,不会丢数据;提示词是模块级常量,调整措辞不动业务逻辑。

## 数据库表设计

| 表 | 字段 | 说明 |
|---|---|---|
| users | id, name(唯一索引), password_hash, created_at | bcrypt 哈希,不存明文 |
| chats | id, user_id(FK→users), title, created_at | 一对多:一个用户多个会话 |
| messages | id, chat_id(FK→chats), role, content, created_at | 复合索引 (chat_id, created_at) 加速历史查询 |
| tasks | id, chat_id(FK→chats), type, status, result, error, created_at, finished_at | 异步任务记录,状态 pending/running/done/failed |

外键全部 `ON DELETE CASCADE`,删用户/会话自动清理下游数据。

## CI

push / PR 时自动跑 ruff + pytest(PG 用 GitHub Actions 的 postgres service),见 `.github/workflows/ci.yml`。
