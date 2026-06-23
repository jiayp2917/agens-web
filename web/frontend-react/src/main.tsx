import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { LogOut, UserRound } from "lucide-react";
import {
  api,
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
  "--game-bg": `url("${assetUrl("assets/game_desktop_bg.png")}")`,
  "--ascension-bg": `url("${assetUrl("assets/ascension_gate.png")}")`,
} as React.CSSProperties;

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

  const returnHome = () => {
    setDialogMode(null);
    setSession(null);
    setView("home");
  };

  return (
    <main className="app" style={assetVars}>
      <header className="topbar">
        <a className="brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">
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
          setUser={setUser}
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

createRoot(document.getElementById("root")!).render(<App />);
