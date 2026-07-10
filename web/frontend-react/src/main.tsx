import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogOut, UserRound } from "lucide-react";
import {
  api,
  ApiError,
  mutationBody,
  type AuthMode,
  type DialogMode,
  type Session,
  type User,
  type View,
} from "./lib/api";
import { BgmToggle } from "./components/BgmToggle";
import { TutorialDialog } from "./components/TutorialDialog";
import { SettingsSaveDialog } from "./components/SettingsSaveDialog";
import { HomePage } from "./pages/HomePage";
import { AuthPage } from "./pages/AuthPage";
import { CharacterCreatePage } from "./pages/CharacterCreatePage";
import { GamePage } from "./pages/GamePage";
import { EndingPage } from "./pages/EndingPage";
import { assetUrl } from "./lib/assets";
import "./styles.css";

const assetVars = {
  "--paper-texture": `url("${assetUrl("assets/paper_texture.png")}")`,
  "--ink-gate": `url("${assetUrl("assets/ink_mountain_gate.png")}")`,
  "--home-bg": `url("${assetUrl("assets/bg_home_xianxia.png")}")`,
  "--character-bg": `url("${assetUrl("assets/bg_character_create.png")}")`,
  "--game-bg": `url("${assetUrl("assets/bg_chronicle_game.png")}")`,
} as React.CSSProperties;

const ACTIVE_SESSION_KEY = "agens-web.active-session-id";

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<View>("home");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialogMode, setDialogMode] = useState<DialogMode | null>(null);
  const [tutorialOpen, setTutorialOpen] = useState(false);
  const mutationInFlight = useRef(false);

  useEffect(() => {
    api<{ user: User }>("/api/auth/me")
      .then((payload) => setUser(payload.user))
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    const sessionId = readActiveSessionId();
    if (!sessionId) return;
    api<Session>(`/api/sessions/${sessionId}`)
      .then((restored) => {
        setSession(restored);
        if (restored.game_over || restored.finale) {
          setView("ending");
        } else if (restored.game_started) {
          setView("game");
        } else {
          setView("character");
        }
      })
      .catch(() => clearActiveSessionId());
  }, []);

  useEffect(() => {
    if (session?.session_id) {
      writeActiveSessionId(session.session_id);
    }
  }, [session?.session_id]);

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
    if (mutationInFlight.current || !session) return;
    mutationInFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const payload = body && typeof body === "object" ? body as Record<string, unknown> : {};
      const next = await api<Session>(path, {
        method: "POST",
        body: JSON.stringify(mutationBody(session, payload)),
      });
      setSession(next);
      setView(next.game_over || next.finale ? "ending" : "game");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          const refreshed = await api<Session>(`/api/sessions/${session.session_id}`);
          setSession(refreshed);
          setView(refreshed.game_over || refreshed.finale ? "ending" : refreshed.game_started ? "game" : "character");
        } catch {
          setError("局面已更新，但刷新失败，请返回首页重试。");
        }
      } else {
        setError(err instanceof Error ? err.message : "请求失败。");
      }
    } finally {
      mutationInFlight.current = false;
      setBusy(false);
    }
  };

  const authenticated = (nextUser: User) => {
    clearActiveSessionId();
    setSession(null);
    setDialogMode(null);
    setUser(nextUser);
    setView("home");
    setError("");
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    clearActiveSessionId();
    setUser(null);
    setSession(null);
    setDialogMode(null);
    setView("home");
  };

  const returnHome = () => {
    clearActiveSessionId();
    setDialogMode(null);
    setSession(null);
    setView("home");
  };

  return (
    <main className={`app view-${view}`} style={assetVars}>
      <header className="topbar">
        <a className="brand page-brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">
          jiayp
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
          onAuthenticated={authenticated}
          setView={setView}
          setError={setError}
        />
      )}
      {view === "character" && session && (
        <CharacterCreatePage
          session={session}
          runTurn={runTurn}
          busy={busy}
          onBack={() => setView("home")}
        />
      )}
      {view === "game" && session && (
        <GamePage
          session={session}
          busy={busy}
          runTurn={runTurn}
          openDialog={openDialog}
          onHome={returnHome}
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

const rootElement = document.getElementById("root");
if (rootElement) createRoot(rootElement).render(<App />);

function readActiveSessionId() {
  try {
    return localStorage.getItem(ACTIVE_SESSION_KEY) || "";
  } catch {
    return "";
  }
}

function writeActiveSessionId(sessionId: string) {
  try {
    localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
  } catch {
    // Browser storage can be unavailable in restricted contexts.
  }
}

function clearActiveSessionId() {
  try {
    localStorage.removeItem(ACTIVE_SESSION_KEY);
  } catch {
    // Browser storage can be unavailable in restricted contexts.
  }
}
