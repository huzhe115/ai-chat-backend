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
  return res.json();
}
