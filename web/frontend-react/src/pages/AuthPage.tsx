import { FormEvent } from "react";
import { Home, KeyRound } from "lucide-react";
import { api, type AuthMode, type User, type View } from "../lib/api";

export function AuthPage({
  mode,
  setMode,
  onAuthenticated,
  setView,
  setError,
}: {
  mode: AuthMode;
  setMode: (mode: AuthMode) => void;
  onAuthenticated: (user: User) => void;
  setView: (view: View) => void;
  setError: (message: string) => void;
}) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    try {
      const payload = await api<{ user: User }>(path, {
        method: "POST",
        body: JSON.stringify({
          username: String(form.get("username") || ""),
          password: String(form.get("password") || ""),
          invite_code: String(form.get("invite_code") || ""),
        }),
      });
      onAuthenticated(payload.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "认证失败。");
    }
  };

  return (
    <section className="auth-screen">
      <form className="auth-panel" onSubmit={submit}>
        <button className="plain-btn back-home" type="button" onClick={() => setView("home")}>
          <Home size={16} />返回首页
        </button>
        <p className="eyebrow">{mode === "login" ? "登录" : "邀请码注册"}</p>
        <h2>{mode === "login" ? "继续修行" : "创建道号"}</h2>
        <p className="auth-note">也可以直接从首页新游戏访客游玩；访客局不提供云端存档。</p>
        <label>用户名<input name="username" autoComplete="username" required /></label>
        <label>
          密码
          <input
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 8 : 1}
          />
        </label>
        {mode === "register" && <label>邀请码<input name="invite_code" type="password" autoComplete="off" required /></label>}
        <button className="primary-btn" type="submit"><KeyRound size={18} />{mode === "login" ? "登录" : "注册并登录"}</button>
        <button className="plain-btn" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "使用邀请码注册" : "已有账号，去登录"}
        </button>
      </form>
    </section>
  );
}
