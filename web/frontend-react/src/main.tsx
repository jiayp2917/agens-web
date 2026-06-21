import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  CheckCircle2,
  KeyRound,
  LogOut,
  Save,
  ScrollText,
  Send,
  Settings,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { api, SaveRow, Session, User } from "./api/client";
import "./styles.css";

type View = "home" | "auth" | "character" | "game" | "ending";
type AuthMode = "login" | "register";

const attributes = [
  ["root_bone", "根骨"],
  ["comprehension", "悟性"],
  ["luck", "气运"],
  ["willpower", "心性"],
  ["physique", "体魄"],
  ["spiritual_sense", "神识"],
] as const;

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<View>("home");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    api<{ user: User }>("/api/auth/me")
      .then((payload) => setUser(payload.user))
      .catch(() => setUser(null));
  }, []);

  const requireAuth = () => {
    if (user) return true;
    setAuthMode("login");
    setView("auth");
    return false;
  };

  const createSession = async () => {
    if (!requireAuth()) return null;
    const created = await api<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "新局" }),
    });
    setSession(created);
    return created;
  };

  const startNewGame = async () => {
    const created = await createSession();
    if (created) setView("character");
  };

  const runTurn = async (path: string, body: unknown) => {
    setBusy(true);
    setError("");
    try {
      const next = await api<Session>(path, { method: "POST", body: JSON.stringify(body) });
      setSession(next);
      setView(next.game_over || next.finale ? "ending" : "game");
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败。");
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    setUser(null);
    setSession(null);
    setView("home");
  };

  return (
    <main className="app">
      <header className="topbar">
        <span className="brand">agens<span>web</span></span>
        <div className="topbar-actions">
          {user ? (
            <>
              <span className="user-chip"><UserRound size={16} />{user.username}</span>
              <button className="icon-btn" onClick={logout} aria-label="退出登录"><LogOut size={18} /></button>
            </>
          ) : (
            <button className="plain-btn" onClick={() => setView("auth")}>登录</button>
          )}
        </div>
      </header>
      {error && <div className="toast" role="alert">{error}</div>}
      {view === "home" && <HomePage onStart={startNewGame} onAuth={() => setView("auth")} />}
      {view === "auth" && <AuthPage mode={authMode} setMode={setAuthMode} setUser={setUser} setView={setView} setError={setError} />}
      {view === "character" && session && <CharacterCreatePage session={session} runTurn={runTurn} />}
      {view === "game" && session && (
        <GamePage
          session={session}
          busy={busy}
          runTurn={runTurn}
          openSettings={() => setSettingsOpen(true)}
        />
      )}
      {view === "ending" && session && <EndingPage session={session} onHome={() => setView("home")} onRestart={startNewGame} />}
      {settingsOpen && session && <SettingsSaveDialog session={session} onClose={() => setSettingsOpen(false)} setSession={setSession} user={user} />}
    </main>
  );
}

function HomePage({ onStart, onAuth }: { onStart: () => void; onAuth: () => void }) {
  return (
    <section className="home">
      <div className="hero">
        <p className="eyebrow">Web · 文字修仙模拟器</p>
        <h1>文字修仙模拟器<span className="seal">道</span></h1>
        <p>从山门晨雾开始。A/B/C 推进天道选项，D 写下自己的行动。</p>
        <div className="home-actions">
          <button className="primary-btn" onClick={onStart}><BookOpen size={18} />新游戏</button>
          <button onClick={onAuth}>读档</button>
          <button>教程</button>
          <button>设置</button>
        </div>
      </div>
    </section>
  );
}

function AuthPage({
  mode,
  setMode,
  setUser,
  setView,
  setError,
}: {
  mode: AuthMode;
  setMode: (mode: AuthMode) => void;
  setUser: (user: User) => void;
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
      setUser(payload.user);
      setView("home");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "认证失败。");
    }
  };
  return (
    <section className="auth-screen">
      <form className="auth-panel" onSubmit={submit}>
        <p className="eyebrow">{mode === "login" ? "登录" : "邀请码注册"}</p>
        <h2>{mode === "login" ? "继续修行" : "创建道号"}</h2>
        <label>用户名<input name="username" autoComplete="username" required /></label>
        <label>密码<input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 8 : 1} /></label>
        {mode === "register" && <label>邀请码<input name="invite_code" type="password" autoComplete="off" required /></label>}
        <button className="primary-btn" type="submit"><KeyRound size={18} />{mode === "login" ? "登录" : "注册并登录"}</button>
        <button className="plain-btn" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "使用邀请码注册" : "已有账号，去登录"}
        </button>
      </form>
    </section>
  );
}

function CharacterCreatePage({ session, runTurn }: { session: Session; runTurn: (path: string, body: unknown) => Promise<void> }) {
  const [randomize, setRandomize] = useState(true);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const attrs = Object.fromEntries(attributes.map(([key]) => [key, Number(form.get(key) || 50)]));
    await runTurn(`/api/sessions/${session.session_id}/start`, {
      game_name: String(form.get("game_name") || ""),
      char_name: String(form.get("char_name") || ""),
      talent: String(form.get("talent") || ""),
      spirit_root: String(form.get("spirit_root") || ""),
      family_background: String(form.get("family_background") || ""),
      difficulty: String(form.get("difficulty") || "普通"),
      randomize_attributes: randomize,
      attributes: randomize ? {} : attrs,
    });
  };
  return (
    <section className="character-page">
      <form className="character-form" onSubmit={submit}>
        <p className="eyebrow">开局设定</p>
        <h2>角色信息<span className="seal">始</span></h2>
        <div className="form-grid">
          <label>游戏名称<input name="game_name" placeholder="本局世界种子" /></label>
          <label>角色名<input name="char_name" placeholder="留空则自动生成" /></label>
          <label>天赋<select name="talent"><option>平平无奇</option><option>剑心微明</option><option>天命道胎</option></select></label>
          <label>灵根<select name="spirit_root"><option>金灵根</option><option>木灵根</option><option>水灵根</option><option>火灵根</option><option>雷灵根</option></select></label>
          <label>家世<select name="family_background"><option>农家</option><option>寒门</option><option>小族</option><option>宗门旁支</option></select></label>
          <label>难度<select name="difficulty"><option>简单</option><option>普通</option><option>困难</option></select></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={randomize} onChange={(e) => setRandomize(e.target.checked)} />随机属性</label>
        <div className="attr-grid">
          {attributes.map(([key, label]) => <label key={key}>{label}<input disabled={randomize} name={key} type="range" min="0" max="100" defaultValue="50" /></label>)}
        </div>
        <button className="primary-btn" type="submit">开始修行</button>
      </form>
    </section>
  );
}

function GamePage({
  session,
  busy,
  runTurn,
  openSettings,
}: {
  session: Session;
  busy: boolean;
  runTurn: (path: string, body: unknown) => Promise<void>;
  openSettings: () => void;
}) {
  const character = session.character || {};
  const world = session.world || {};
  const [action, setAction] = useState("");
  const events = useMemo(() => session.events.filter((event) => event.text), [session.events]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!action.trim()) return;
    const text = action.trim();
    setAction("");
    await runTurn(`/api/sessions/${session.session_id}/action`, { action: text });
  };
  return (
    <section className="game-page">
      <header className="game-summary">
        <div>
          <h2>{character.name || "无名"}</h2>
          <p>{character.realm || "练气"}{character.realm_stage || 1}层 · 回合 {session.turn_count}</p>
        </div>
        <button className="icon-btn" onClick={openSettings} aria-label="设置与存档"><Settings size={20} /></button>
      </header>
      <div className="game-grid">
        <aside className="status-panel">
          <strong>{world.location || "山门"}</strong>
          <p>气血 {character.hp || 0}/{character.hp_max || 0}</p>
          <p>灵力 {character.mp || 0}/{character.mp_max || 0}</p>
          <div className="tool-grid">
            <button>背包</button><button>功法</button><button>任务</button><button>地图</button>
          </div>
        </aside>
        <section className="story-panel">
          {session.fallback_prompt?.active && <FallbackBanner session={session} runTurn={runTurn} />}
          <div className="story-log">
            {events.length === 0 ? <p>叙事将在这里展开。</p> : events.map((event, idx) => <article key={idx}>{event.text}</article>)}
          </div>
          <div className="choice-list">
            {session.choices.map((choice, index) => (
              <button key={choice} onClick={() => runTurn(`/api/sessions/${session.session_id}/choice`, { choice_index: index })}>
                <span>{String.fromCharCode(65 + index)}</span>{choice}
              </button>
            ))}
          </div>
        </section>
      </div>
      <form className="action-bar-react" onSubmit={submit}>
        <label>D 自由行动</label>
        <input value={action} onChange={(event) => setAction(event.target.value)} placeholder="例如：前往悬赏榜、请教师兄、尝试突破" />
        <button className="primary-btn" disabled={busy} type="submit"><Send size={18} />{busy ? "推演中" : "发送"}</button>
      </form>
    </section>
  );
}

function FallbackBanner({ session, runTurn }: { session: Session; runTurn: (path: string, body: unknown) => Promise<void> }) {
  return (
    <aside className="fallback">
      <ShieldAlert size={20} />
      <span>{session.fallback_prompt?.text || "模型暂不可用，当前以本地故事继续。"}</span>
      <button onClick={() => runTurn(`/api/sessions/${session.session_id}/action`, { action: "继续本局" })}>继续本局</button>
      <button onClick={() => runTurn(`/api/sessions/${session.session_id}/end`, { reason: "玩家结束本局。" })}>结束本局</button>
    </aside>
  );
}

function SettingsSaveDialog({
  session,
  user,
  onClose,
  setSession,
}: {
  session: Session;
  user: User | null;
  onClose: () => void;
  setSession: (session: Session) => void;
}) {
  const [saves, setSaves] = useState<SaveRow[]>([]);
  const [message, setMessage] = useState("");
  useEffect(() => {
    api<SaveRow[]>("/api/saves").then(setSaves).catch(() => setSaves([]));
  }, []);
  const save = async (name: string) => {
    const payload = await api<{ save: SaveRow; session: Session }>(`/api/sessions/${session.session_id}/save`, {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    setSession(payload.session);
    setMessage(`已保存：${payload.save.name}`);
  };
  return (
    <div className="modal-scrim" role="dialog" aria-modal="true">
      <div className="settings-dialog">
        <header><h2>设置与存档</h2><button className="icon-btn" onClick={onClose}>×</button></header>
        <section className="settings-grid">
          <div className="protected-settings">
            <Settings size={22} />
            <div>
              <strong>模型设置</strong>
              <p>{user?.is_admin ? "管理员可在后端受控保存模型配置。" : "模型设置仅管理员可用。"}</p>
            </div>
          </div>
          <div className="save-list">
            {[1, 2, 3, 4, 5].map((slot) => {
              const name = `slot_${slot}`;
              const row = saves.find((item) => item.name === name);
              return (
                <button key={name} onClick={() => save(name)}>
                  <Save size={18} />
                  <span>{`档位 ${slot}`}</span>
                  <small>{row ? `${row.char_name} · ${row.realm} · 回合 ${row.turn_count}` : "空档"}</small>
                </button>
              );
            })}
          </div>
        </section>
        {message && <p className="dialog-message"><CheckCircle2 size={16} />{message}</p>}
      </div>
    </div>
  );
}

function EndingPage({ session, onHome, onRestart }: { session: Session; onHome: () => void; onRestart: () => void }) {
  const character = session.character || {};
  return (
    <section className="ending-page">
      <ScrollText size={36} />
      <h2>{session.finale ? "飞升" : "本局结束"}</h2>
      <p>{session.error || "尘埃落定。"}</p>
      <dl>
        <dt>角色</dt><dd>{character.name || "无名"}</dd>
        <dt>境界</dt><dd>{character.realm || "练气"}{character.realm_stage || 1}层</dd>
        <dt>回合</dt><dd>{session.turn_count}</dd>
      </dl>
      <div className="ending-actions">
        <button className="primary-btn" onClick={onRestart}>再开一局</button>
        <button onClick={onHome}>回首页</button>
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
