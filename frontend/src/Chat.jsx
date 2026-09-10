import { useEffect, useRef, useState } from "react";
import { api, streamApi } from "./api.js";

export default function Chat({ onLogout }) {
  const [chats, setChats] = useState([]);
  const [current, setCurrent] = useState(null); // 当前会话 id
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(null); // null=空闲,""=等待首个字,非空=流式文本
  const [creating, setCreating] = useState(false); // 新建会话请求进行中
  const listRef = useRef(null);
  const currentRef = useRef(null); // 供流式回调判断"用户是否中途切了会话"

  // 首屏:载入会话列表并选中第一个
  const loadChats = async () => {
    const list = await api("/chats");
    setChats(list);
    if (list[0]) setCurrent(list[0].id);
  };

  // 只刷新侧栏列表,不动选中(发完消息刷标题用)
  const refreshChats = async () => {
    setChats(await api("/chats"));
  };

  const loadMessages = async (chatId) => {
    if (!chatId) return setMessages([]);
    const msgs = await api(`/chats/${chatId}/messages`);
    if (chatId === currentRef.current) setMessages(msgs); // 回复回来时已切走,丢弃
  };

  useEffect(() => {
    loadChats().catch(() => {});
  }, []);

  useEffect(() => {
    currentRef.current = current;
    setStreaming(null); // 切会话时丢弃进行中的流,回来看会从库里重新读到
    setMessages([]); // 立刻清空,别让上个会话的内容短暂残留在新会话里
    loadMessages(current).catch(() => {});
  }, [current]);

  // 新消息后自动滚到底部
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, streaming]);

  const deleteChat = async (e, id) => {
    e.stopPropagation(); // 别触发选中该会话
    if (!window.confirm("删除该会话?消息将一并删除")) return;
    try {
      await api(`/chats/${id}`, { method: "DELETE" });
    } catch (err) {
      alert(err.message);
      return;
    }
    const rest = chats.filter((c) => c.id !== id);
    setChats(rest);
    if (id === current) setCurrent(rest[0]?.id ?? null);
  };

  const newChat = async () => {
    if (creating) return; // 防双击重复创建
    setCreating(true);
    try {
      const chat = await api("/chats", {
        method: "POST",
        body: { title: "新会话" },
      });
      setChats((prev) => [chat, ...prev]); // POST 返回完整会话,直接插侧栏顶部
      setCurrent(chat.id); // 不等列表刷新,立刻切过去
    } finally {
      setCreating(false);
    }
  };

  const send = async (e) => {
    e.preventDefault();
    const content = input.trim();
    if (!content || !current || streaming !== null || creating) return; // 创建中不发,防发到旧会话
    const chatId = current;
    setInput("");
    setStreaming("");
    try {
      await streamApi(`/chats/${chatId}/messages/stream`, {
        body: { content },
        onEvent: (ev) => {
          if (chatId !== currentRef.current) return; // 中途切了会话,丢弃事件
          if (ev.user_msg) setMessages((prev) => [...prev, ev.user_msg]);
          else if (ev.delta) setStreaming((t) => t + ev.delta);
          else if (ev.assistant_msg) {
            setMessages((prev) => [...prev, ev.assistant_msg]);
            setStreaming(null);
          } else if (ev.error) {
            alert(ev.error);
            setStreaming(null);
          }
        },
      });
    } catch (err) {
      alert(err.message);
    } finally {
      setStreaming(null);
      refreshChats().catch(() => {}); // 首条消息后标题变了,刷新侧栏(不切选中)
    }
  };

  return (
    <div className="layout">
      {/* 左侧会话列表 */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1 className="app-title">AI 聊天助手</h1>
          <div className="app-divider" />
        </div>
        <button className="primary full" onClick={newChat} disabled={creating}>
          + 新建会话
        </button>
        <div className="chat-list">
          {chats.map((c) => (
            <div
              key={c.id}
              className={`chat-item ${c.id === current ? "active" : ""}`}
              onClick={() => setCurrent(c.id)}
            >
              <span className="chat-title">{c.title}</span>
              <button className="chat-del" title="删除会话" onClick={(e) => deleteChat(e, c.id)}>
                ✕
              </button>
            </div>
          ))}
        </div>
        <button className="ghost full" onClick={onLogout}>
          退出登录
        </button>
      </aside>

      {/* 右侧聊天区 */}
      <main className="chat-main">
        {current ? (
          <>
            <div className="messages" ref={listRef}>
              {messages.length === 0 && streaming === null && (
                <div className="empty-tip">你好呀,有什么可以帮助你的?</div>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`msg ${m.role}`}>
                  <span className="avatar">{m.role === "user" ? "👤" : "🤖"}</span>
                  <div className="bubble">{m.content}</div>
                </div>
              ))}
              {streaming !== null && (
                <div className="msg assistant">
                  <span className="avatar">🤖</span>
                  <div className={`bubble${streaming === "" ? " thinking" : ""}`}>
                    {streaming === "" ? <span className="spinner" /> : streaming}
                  </div>
                </div>
              )}
            </div>

            <form className="input-bar" onSubmit={send}>
              <textarea
                value={input}
                placeholder="输入消息,回车发送(Shift+Enter 换行)"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(e);
                  }
                }}
                rows={2}
              />
              <button className="primary" disabled={!input.trim() || streaming !== null || creating}>
                发送
              </button>
            </form>
          </>
        ) : (
          <div className="empty-tip">点击左侧「+ 新建会话」开始聊天</div>
        )}
      </main>
    </div>
  );
}
