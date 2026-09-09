import { useState } from "react";
import AuthPage from "./AuthPage.jsx";
import Chat from "./Chat.jsx";
import { getToken, clearToken } from "./api.js";

export default function App() {
  const [token, setToken] = useState(getToken());

  const onLogin = (t) => setToken(t);
  const onLogout = () => {
    clearToken();
    setToken(null);
  };

  if (!token) return <AuthPage onLogin={onLogin} />;
  return <Chat onLogout={onLogout} />;
}
