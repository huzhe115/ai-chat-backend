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
