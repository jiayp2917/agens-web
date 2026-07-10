import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import {
  api,
  ApiError,
  ModelSettings,
  SaveRow,
  Session,
  User,
  type AuthMode,
  type DialogMode,
  type View,
  mutationBody,
} from "../lib/api";
import { ModelSettingsPanel } from "./ModelSettingsPanel";
import { SaveSlotsPanel } from "./SaveSlotsPanel";
import { useDialogA11y } from "../lib/useDialogA11y";

export function SettingsSaveDialog({
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
    if (user) {
      api<ModelSettings>("/api/settings/model").then(setSettings).catch(() => setSettings(null));
    } else {
      setSettings(null);
    }
  }, [user?.id]);

  const save = async (name: string) => {
    try {
      const payload = await api<{ save: SaveRow; session: Session }>(`/api/sessions/${session.session_id}/save`, {
        method: "POST",
        body: JSON.stringify(mutationBody(session, { name })),
      });
      setSession(payload.session);
      await refreshSaves();
      setMessage(`已保存：${payload.save.name}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const refreshed = await api<Session>(`/api/sessions/${session.session_id}`);
        setSession(refreshed);
      }
      setMessage(err instanceof Error ? err.message : "保存失败。");
    }
  };

  const load = async (name: string) => {
    try {
      const loaded = await api<Session>(`/api/sessions/${session.session_id}/load`, {
        method: "POST",
        body: JSON.stringify(mutationBody(session, { name })),
      });
      setSession(loaded);
      setView(loaded.game_over || loaded.finale ? "ending" : "game");
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const refreshed = await api<Session>(`/api/sessions/${session.session_id}`);
        setSession(refreshed);
      }
      setMessage(err instanceof Error ? err.message : "读档失败。");
    }
  };

  const { scrimRef, onScrimClick } = useDialogA11y(onClose);
  return (
    <div className="modal-scrim" ref={scrimRef} role="dialog" aria-modal="true" aria-label="设置与存档" onClick={onScrimClick}>
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
            <ModelSettingsPanel
              user={user}
              settings={settings}
              setSettings={setSettings}
              setMessage={setMessage}
              onAuth={onAuth}
            />
          )}
          {activeTab === "saves" && (
            <SaveSlotsPanel
              user={user}
              saves={saves}
              session={session}
              onSave={save}
              onLoad={load}
              onAuth={onAuth}
            />
          )}
        </section>
        {message && <p className="dialog-message"><CheckCircle2 size={16} />{message}</p>}
      </div>
    </div>
  );
}
