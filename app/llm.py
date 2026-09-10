import json

import httpx

from app.config import settings


async def chat_reply(messages: list[dict]) -> str:
    """OpenAI 兼容协议的对话补全,DeepSeek / OpenAI 等都能用。

    messages 格式: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY,请在 .env 里填写")
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client:
        resp = await client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": settings.llm_model, "messages": messages},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def stream_reply(messages: list[dict]):
    """流式对话补全,逐段 yield 文本增量。

    上游按 SSE 协议返回 data: {...} 行,[DONE] 表示结束;
    这里只把增量文本吐出去,SSE 包装交给接口层。
    """
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY,请在 .env 里填写")
    async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=60) as client, client.stream(
        "POST",
        "/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={"model": settings.llm_model, "messages": messages, "stream": True},
    ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
