import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

export default function Chat({ onLogout }) {
  const [chats, setChats] = useState([]);
  const [current, setCurrent] = useState(null); // 当前会话 id
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [summary, setSummary] = useState(null); // { text, status }
  const listRef = useRef(null);

  // 载入会话列表,并默认选中第一个
  const loadChats = async (selectId) => {
    const list = await api("/chats");
    setChats(list);
    const target = list.find((c) => c.id === selectId) || list[0] || null;
    if (target) setCurrent(target.id);
  };

  const loadMessages = async (chatId) => {
    if (!chatId) return setMessages([]);
    const msgs = await api(`/chats/${chatId}/messages`);
    setMessages(msgs);
  };

  useEffect(() => {
    loadChats().catch(() => {});
  }, []);

  useEffect(() => {
    loadMessages(current).catch(() => {});
  }, [current]);

  // 新消息后自动滚到底部
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, thinking]);

  const newChat = async () => {
    const chat = await api("/chats", {
      method: "POST",
      body: { title: "新会话" },
    });
    await loadChats(chat.id);
  };

  const send = async (e) => {
    e.preventDefault();
    const content = input.trim();
    if (!content || !current || thinking) return;
    setInput("");
    setThinking(true);
    try {
      const [userMsg, aiMsg] = await api(`/chats/${current}/messages`, {
        method: "POST",
        body: { content },
      });
      setMessages((prev) => [...prev, userMsg, aiMsg]);
    } catch (err) {
      alert(err.message);
    } finally {
      setThinking(false);
    }
  };

  const generateSummary = async () => {
    if (!current) return;
    setSummary({ status: "生成中..." });
    const task = await api(`/chats/${current}/summary`, { method: "POST" });
    // 轮询任务状态,2 秒一次
    const timer = setInterval(async () => {
      const t = await api(`/tasks/${task.id}`);
      if (t.status === "done" || t.status === "failed") {
        clearInterval(timer);
        setSummary(
          t.status === "done"
            ? { status: "done", text: t.result }
            : { status: "failed", text: t.error || "摘要生成失败" }
        );
      }
    }, 2000);
  };

  return (
    <div className="layout">
      {/* 左侧会话列表 */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1 className="app-title">AI 聊天助手</h1>
          <div className="app-divider" />
        </div>
        <button className="primary full" onClick={newChat}>
          + 新建会话
        </button>
        <div className="chat-list">
          {chats.map((c) => (
            <div
              key={c.id}
              className={`chat-item ${c.id === current ? "active" : ""}`}
              onClick={() => setCurrent(c.id)}
            >
              {c.title}
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
            <div className="chat-topbar">
              <button className="ghost" onClick={generateSummary} disabled={summary?.status === "生成中..."}>
                ✨ 生成摘要
              </button>
            </div>

            {summary && (
              <div className={`summary-box ${summary.status}`}>
                <b>{summary.status === "生成中..." ? "摘要生成中,请稍候..." : "会话摘要"}</b>
                {summary.text && <p>{summary.text}</p>}
              </div>
            )}

            <div className="messages" ref={listRef}>
              {messages.length === 0 && !thinking && (
                <div className="empty-tip">你好呀,有什么可以帮助你的?</div>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`msg ${m.role}`}>
                  <span className="avatar">{m.role === "user" ? "👤" : "🤖"}</span>
                  <div className="bubble">{m.content}</div>
                </div>
              ))}
              {thinking && (
                <div className="msg assistant">
                  <span className="avatar">🤖</span>
                  <div className="bubble thinking">
                    <span className="spinner" /> AI 思考中...
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
              <button className="primary" disabled={!input.trim() || thinking}>
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
