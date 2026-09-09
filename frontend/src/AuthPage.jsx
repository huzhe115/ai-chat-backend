import { useState } from "react";
import { api, setToken } from "./api.js";

// 登录/注册共用一个简易卡片,模式切换
export default function AuthPage({ onLogin }) {
  const [mode, setMode] = useState("login"); // login | register
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        // 注册接口只建用户不发 token,注册成功后自动登录
        await api("/auth/register", { method: "POST", body: { name, password } });
      }
      const { access_token } = await api("/auth/login", {
        method: "POST",
        body: { name, password },
      });
      setToken(access_token);
      onLogin(access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const isRegister = mode === "register";
  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1 className="auth-title">AI 聊天助手</h1>
        <div className="auth-divider" />
        <h2>{isRegister ? "注册新账号" : "欢迎回来"}</h2>
        <input
          placeholder="用户名"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          required
        />
        <input
          type="password"
          placeholder={isRegister ? "密码(至少6位)" : "密码"}
          value={password}
          minLength={6}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <div className="auth-error">{error}</div>}
        <button className="primary" disabled={busy}>
          {busy ? "请稍候..." : isRegister ? "注册并登录" : "登录"}
        </button>
        <div className="auth-switch">
          {isRegister ? "已有账号?" : "还没有账号?"}
          <a onClick={() => { setMode(isRegister ? "login" : "register"); setError(""); }}>
            {isRegister ? "去登录" : "去注册"}
          </a>
        </div>
      </form>
    </div>
  );
}
