// 统一 fetch 封装:自动带 token,非 2xx 抛出后端 detail 信息
const TOKEN_KEY = "ai_chat_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `请求失败(${res.status})`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* 非 JSON 响应,保留默认错误 */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null; // 删除类接口无响应体
  return res.json();
}

// 流式请求:后端按 SSE 协议逐条发 data: {...} 事件,onEvent 每条回调一次
export async function streamApi(path, { body, onEvent }) {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `请求失败(${res.status})`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* 非 JSON 响应,保留默认错误 */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // 空行是 SSE 事件边界,按块拆出每个 data: 行
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }
}
