import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpen,
  CheckCircle2,
  Home,
  KeyRound,
  LogOut,
  RotateCcw,
  Save,
  ScrollText,
  Send,
  Settings,
  ShieldAlert,
  Upload,
  UserRound,
  Volume2,
  VolumeX,
} from "lucide-react";
import { api, ModelSettings, SaveRow, Session, User } from "./api/client";
import "./styles.css";

type View = "home" | "auth" | "character" | "game" | "ending";
type AuthMode = "login" | "register";
type DialogMode = "settings" | "saves";

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
  const [dialogMode, setDialogMode] = useState<DialogMode | null>(null);
  const [tutorialOpen, setTutorialOpen] = useState(false);

  useEffect(() => {
    api<{ user: User }>("/api/auth/me")
      .then((payload) => setUser(payload.user))
      .catch(() => setUser(null));
  }, []);

  const openAuth = (mode: AuthMode = "login") => {
    setAuthMode(mode);
    setDialogMode(null);
    setView("auth");
  };

  const createSession = async (title = "新局") => {
    const created = await api<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    setSession(created);
    return created;
  };

  const ensureSession = async (title = "临时局") => session || createSession(title);

  const startNewGame = async () => {
    setError("");
    try {
      const created = await createSession();
      if (created) setView("character");
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建新局失败。");
    }
  };

  const openDialog = async (mode: DialogMode) => {
    setError("");
    try {
      const current = await ensureSession(mode === "saves" ? "读档" : "设置");
      if (current) setDialogMode(mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开面板失败。");
    }
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
    setDialogMode(null);
    setView("home");
  };

  return (
    <main className="app">
      <header className="topbar">
        <a className="brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">
          jiayp2917
        </a>
        <div className="topbar-actions">
          <BgmToggle />
          {user ? (
            <>
              <span className="user-chip" title={user.username}><UserRound size={16} />{user.username}</span>
              <button className="icon-btn" onClick={logout} aria-label="退出登录"><LogOut size={18} /></button>
            </>
          ) : (
            <button className="plain-btn" onClick={() => openAuth("login")}>登录</button>
          )}
        </div>
      </header>
      {error && <div className="toast" role="alert">{error}</div>}
      {view === "home" && (
        <HomePage
          onStart={startNewGame}
          onLoad={() => openDialog("saves")}
          onSettings={() => openDialog("settings")}
          onTutorial={() => setTutorialOpen(true)}
          onAuth={openAuth}
        />
      )}
      {view === "auth" && (
        <AuthPage
          mode={authMode}
          setMode={setAuthMode}
          setUser={setUser}
          setView={setView}
          setError={setError}
        />
      )}
      {view === "character" && session && (
        <CharacterCreatePage
          session={session}
          runTurn={runTurn}
          onBack={() => setView("home")}
        />
      )}
      {view === "game" && session && (
        <GamePage
          session={session}
          busy={busy}
          runTurn={runTurn}
          openDialog={openDialog}
        />
      )}
      {view === "ending" && session && (
        <EndingPage session={session} onHome={() => setView("home")} onRestart={startNewGame} />
      )}
      {dialogMode && session && (
        <SettingsSaveDialog
          mode={dialogMode}
          session={session}
          onClose={() => setDialogMode(null)}
          setSession={setSession}
          setView={setView}
          user={user}
          onAuth={openAuth}
        />
      )}
      {tutorialOpen && <TutorialDialog onClose={() => setTutorialOpen(false)} />}
    </main>
  );
}

function BgmToggle() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (enabled) {
      audio.pause();
      setEnabled(false);
      return;
    }
    try {
      audio.volume = 0.42;
      await audio.play();
      setBlocked(false);
      setEnabled(true);
    } catch {
      setBlocked(true);
      setEnabled(false);
    }
  };

  return (
    <>
      <button
        className={`icon-btn bgm-btn ${enabled ? "is-on" : ""}`}
        onClick={toggle}
        aria-label={enabled ? "关闭背景音乐" : "播放背景音乐"}
        title={blocked ? "浏览器阻止自动播放，请再点一次" : enabled ? "关闭背景音乐" : "播放背景音乐"}
      >
        {enabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
      </button>
      <audio
        ref={audioRef}
        src="/assets/audio/bgm.flac"
        preload="none"
        loop
        onPlay={() => setEnabled(true)}
        onPause={() => setEnabled(false)}
      />
    </>
  );
}

function HomePage({
  onStart,
  onLoad,
  onSettings,
  onTutorial,
  onAuth,
}: {
  onStart: () => void;
  onLoad: () => void;
  onSettings: () => void;
  onTutorial: () => void;
  onAuth: (mode: AuthMode) => void;
}) {
  return (
    <section className="home">
      <div className="home-shell">
        <div className="hero">
          <p className="eyebrow">WEB · 文字修仙模拟器</p>
          <h1>文字修仙模拟器<span className="seal">道</span></h1>
          <p>从山门晨雾开始。A/B/C 推进天道选项，D 写下自己的行动。</p>
          <div className="play-modes" aria-label="游玩方式">
            <span>访客新局：立即开玩，不提供云端存档</span>
            <span>邀请码账号：登录后可保存和读档</span>
          </div>
          <div className="home-actions">
            <button className="primary-btn" onClick={onStart}><BookOpen size={18} />新游戏</button>
            <button onClick={onLoad}><Upload size={18} />读档</button>
            <button onClick={onTutorial}><ScrollText size={18} />教程</button>
            <button onClick={onSettings}><Settings size={18} />设置</button>
            <button onClick={() => onAuth("register")}><KeyRound size={18} />邀请码注册</button>
          </div>
        </div>
        <figure className="home-preview">
          <img src="/assets/ink_mountain_gate.png" alt="水墨山门视觉" />
        </figure>
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

function CharacterCreatePage({
  session,
  runTurn,
  onBack,
}: {
  session: Session;
  runTurn: (path: string, body: unknown) => Promise<void>;
  onBack: () => void;
}) {
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
        <div className="form-topline">
          <p className="eyebrow">开局设定</p>
          <button className="plain-btn" type="button" onClick={onBack}><Home size={16} />返回首页</button>
        </div>
        <h2>角色信息<span className="seal">始</span></h2>
        <div className="mode-grid" aria-label="游玩模式">
          <button type="button" className="active-mode">引导模式</button>
          <button type="button" disabled>小说模式</button>
          <button type="button" disabled>游戏模式</button>
        </div>
        <div className="form-grid">
          <label>游戏名称<input name="game_name" placeholder="本局世界种子" /></label>
          <label>角色名<input name="char_name" placeholder="留空则自动生成" /></label>
          <label>天赋<select name="talent"><option>平平无奇</option><option>剑心微明</option><option>天命道胎</option></select></label>
          <label>灵根<select name="spirit_root"><option>金灵根</option><option>木灵根</option><option>水灵根</option><option>火灵根</option><option>雷灵根</option></select></label>
          <label>家世<select name="family_background"><option>农家</option><option>寒门</option><option>小族</option><option>宗门旁支</option></select></label>
          <label>难度<select name="difficulty"><option>简单</option><option>普通</option><option>困难</option></select></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={randomize} onChange={(event) => setRandomize(event.target.checked)} />随机属性</label>
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
  openDialog,
}: {
  session: Session;
  busy: boolean;
  runTurn: (path: string, body: unknown) => Promise<void>;
  openDialog: (mode: DialogMode) => void;
}) {
  const character = session.character || {};
  const world = session.world || {};
  const [action, setAction] = useState("");
  const [panel, setPanel] = useState<keyof Session["panels"]>("status");
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
          <span className="session-mode">{session.guest ? "访客局 · 不提供云端存档" : "账号局 · 可存档"}</span>
        </div>
        <div className="summary-actions">
          <button className="icon-btn" onClick={() => openDialog("saves")} aria-label="存档"><Save size={20} /></button>
          <button className="icon-btn" onClick={() => openDialog("settings")} aria-label="设置"><Settings size={20} /></button>
        </div>
      </header>
      <div className="game-grid">
        <aside className="status-panel">
          <strong>{world.location || "山门"}</strong>
          <p>气血 {character.hp || 0}/{character.hp_max || 0}</p>
          <p>灵力 {character.mp || 0}/{character.mp_max || 0}</p>
          <div className="tool-grid">
            {([
              ["status", "状态"],
              ["inventory", "背包"],
              ["skills", "功法"],
              ["map", "地图"],
              ["quests", "任务"],
              ["realm", "境界"],
            ] as Array<[keyof Session["panels"], string]>).map(([key, label]) => (
              <button key={key} className={panel === key ? "selected-tool" : ""} onClick={() => setPanel(key)}>{label}</button>
            ))}
          </div>
          <pre className="panel-output">{String(session.panels?.[panel] || "暂无内容。")}</pre>
        </aside>
        <section className="story-panel">
          {session.fallback_prompt?.active && <FallbackBanner session={session} busy={busy} runTurn={runTurn} />}
          <div className="story-log">
            {events.length === 0 ? <p>叙事将在这里展开。</p> : events.map((event, idx) => <article key={idx}>{event.text}</article>)}
          </div>
          <div className="choice-list">
            {session.choices.map((choice, index) => (
              <button key={`${choice}-${index}`} disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/choice`, { choice_index: index })}>
                <span>{String.fromCharCode(65 + index)}</span>{choice}
              </button>
            ))}
          </div>
        </section>
      </div>
      <form className="action-bar-react" onSubmit={submit}>
        <label>D 自由行动</label>
        <input disabled={busy} value={action} onChange={(event) => setAction(event.target.value)} placeholder="例如：前往悬赏榜、请教师兄、尝试突破" />
        <button className="primary-btn" disabled={busy} type="submit"><Send size={18} />{busy ? "推演中" : "发送"}</button>
      </form>
    </section>
  );
}

function FallbackBanner({ session, busy, runTurn }: { session: Session; busy: boolean; runTurn: (path: string, body: unknown) => Promise<void> }) {
  return (
    <aside className="fallback">
      <ShieldAlert size={20} />
      <span>{session.fallback_prompt?.text || "模型暂不可用，当前以本地故事继续。"}</span>
      <button disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/action`, { action: "继续本局" })}>继续本局</button>
      <button disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/end`, { reason: "玩家结束本局。" })}>结束本局</button>
    </aside>
  );
}

function SettingsSaveDialog({
  mode,
  session,
  user,
  onClose,
  setSession,
  setView,
  onAuth,
}: {
  mode: DialogMode;
  session: Session;
  user: User | null;
  onClose: () => void;
  setSession: (session: Session) => void;
  setView: (view: View) => void;
  onAuth: (mode: AuthMode) => void;
}) {
  const [saves, setSaves] = useState<SaveRow[]>([]);
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [message, setMessage] = useState("");
  const [activeTab, setActiveTab] = useState<DialogMode>(mode);

  const refreshSaves = () => {
    if (!user) {
      setSaves([]);
      return Promise.resolve();
    }
    return api<SaveRow[]>("/api/saves").then(setSaves).catch(() => setSaves([]));
  };

  useEffect(() => {
    refreshSaves();
    if (user?.is_admin) {
      api<ModelSettings>("/api/settings/model").then(setSettings).catch(() => setSettings(null));
    }
  }, [user?.id, user?.is_admin]);

  const save = async (name: string) => {
    try {
      const payload = await api<{ save: SaveRow; session: Session }>(`/api/sessions/${session.session_id}/save`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setSession(payload.session);
      await refreshSaves();
      setMessage(`已保存：${payload.save.name}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败。");
    }
  };

  const load = async (name: string) => {
    try {
      const loaded = await api<Session>(`/api/sessions/${session.session_id}/load`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setSession(loaded);
      setView(loaded.game_over || loaded.finale ? "ending" : "game");
      onClose();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "读档失败。");
    }
  };

  const saveSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const saved = await api<ModelSettings>("/api/settings/model", {
      method: "POST",
      body: JSON.stringify({
        provider: String(form.get("provider") || ""),
        base_url: String(form.get("base_url") || ""),
        model: String(form.get("model") || ""),
        api_key: String(form.get("api_key") || ""),
      }),
    });
    setSettings(saved);
    setMessage("模型设置已保存。");
    const apiKeyInput = event.currentTarget.elements.namedItem("api_key");
    if (apiKeyInput instanceof HTMLInputElement) {
      apiKeyInput.value = "";
    }
  };

  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="设置与存档">
      <div className="settings-dialog">
        <header>
          <h2>设置与存档</h2>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">×</button>
        </header>
        <div className="dialog-tabs">
          <button className={activeTab === "saves" ? "active-tab" : ""} onClick={() => setActiveTab("saves")}>存档</button>
          <button className={activeTab === "settings" ? "active-tab" : ""} onClick={() => setActiveTab("settings")}>设置</button>
        </div>
        <section className="settings-grid">
          {activeTab === "settings" && (
            <div className="protected-settings">
              <Settings size={22} />
              {user?.is_admin ? (
                <form
                  key={`${settings?.provider || ""}:${settings?.base_url || ""}:${settings?.model || ""}`}
                  className="settings-form"
                  onSubmit={saveSettings}
                >
                  <strong>模型设置</strong>
                  <label>服务商<input name="provider" defaultValue={settings?.provider || "Agens"} /></label>
                  <label>Base URL<input name="base_url" defaultValue={settings?.base_url || "https://apihub.agnes-ai.com/v1"} /></label>
                  <label>模型<input name="model" defaultValue={settings?.model || "agnes-2.0-flash"} /></label>
                  <label>API Key<input name="api_key" type="password" placeholder="留空则保持当前 Key" /></label>
                  <p>当前 Key 状态：{settings?.api_key_set ? "已配置" : "未配置"}</p>
                  <button className="primary-btn" type="submit"><CheckCircle2 size={18} />保存设置</button>
                </form>
              ) : (
                <div className="guest-save-state">
                  <strong>模型设置</strong>
                  <p>{user ? "模型设置仅管理员可用。当前前端不会显示真实 Key。" : "访客可以直接游玩；模型配置由管理员维护，不需要在浏览器输入 Key。"}</p>
                  {!user && (
                    <div className="inline-actions">
                      <button onClick={() => onAuth("login")}>登录</button>
                      <button className="primary-btn" onClick={() => onAuth("register")}>邀请码注册</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {activeTab === "saves" && (
            user ? (
              <div className="save-list">
                {[1, 2, 3, 4, 5].map((slot) => {
                  const name = `slot_${slot}`;
                  const row = saves.find((item) => item.name === name);
                  return (
                    <div className="save-row" key={name}>
                      <Save size={18} />
                      <div>
                        <strong>{`档位 ${slot}`}</strong>
                        <small>{row ? `${row.char_name} · ${row.realm} · 回合 ${row.turn_count} · ${formatTime(row.updated_at)}` : "空档"}</small>
                      </div>
                      <div className="save-row-actions">
                        {row && <button onClick={() => load(name)}><Upload size={16} />读档</button>}
                        <button onClick={() => save(name)}>{row ? <RotateCcw size={16} /> : <Save size={16} />}{row ? "覆盖保存" : "保存到此档"}</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="guest-save-state">
                <Save size={22} />
                <strong>访客游玩不提供云端存档</strong>
                <p>当前局可以继续玩；登录或使用邀请码注册后的新局可保存和读档。</p>
                <div className="inline-actions">
                  <button onClick={() => onAuth("login")}>登录读档</button>
                  <button className="primary-btn" onClick={() => onAuth("register")}>邀请码注册</button>
                </div>
              </div>
            )
          )}
        </section>
        {message && <p className="dialog-message"><CheckCircle2 size={16} />{message}</p>}
      </div>
    </div>
  );
}

function TutorialDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="教程">
      <div className="settings-dialog compact-dialog">
        <header><h2>教程</h2><button className="icon-btn" onClick={onClose} aria-label="关闭">×</button></header>
        <section className="settings-grid">
          <p>A/B/C 是当前回合选项。D 输入框可以写自由行动，例如探索、交谈、修炼、战斗或尝试突破。</p>
          <p>模型暂不可用时，本局会切到本地故事继续；访客局仍可继续玩，但不提供云端存档。</p>
          <button className="primary-btn" onClick={onClose}>知道了</button>
        </section>
      </div>
    </div>
  );
}

function EndingPage({ session, onHome, onRestart }: { session: Session; onHome: () => void; onRestart: () => void }) {
  const character = session.character || {};
  const recap = session.events.filter((event) => event.text).slice(-6);
  return (
    <section className="ending-page">
      <div className="ending-card">
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
      </div>
      <aside className="ending-recap">
        <h3>本局记录</h3>
        {recap.length ? recap.map((event, index) => <article key={index}>{event.text}</article>) : <p>暂无记录。</p>}
      </aside>
    </section>
  );
}

function formatTime(value: number) {
  if (!value) return "未更新";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

createRoot(document.getElementById("root")!).render(<App />);
