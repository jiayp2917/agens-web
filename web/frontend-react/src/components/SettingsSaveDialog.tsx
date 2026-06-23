import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, RotateCcw, Save, Settings, Upload } from "lucide-react";
import {
  api,
  ModelSettings,
  SaveRow,
  Session,
  User,
  type AuthMode,
  type DialogMode,
  type View,
} from "../lib/api";
import { modelPresets } from "../lib/catalog";
import { formatTime } from "../lib/util";

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
  const [modelForm, setModelForm] = useState({
    provider: "Agens",
    base_url: "https://apihub.agnes-ai.com/v1",
    model: "agnes-2.0-flash",
  });

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

  useEffect(() => {
    if (!settings) return;
    setModelForm({
      provider: settings.provider || "Agens",
      base_url: settings.base_url || "https://apihub.agnes-ai.com/v1",
      model: settings.model || "agnes-2.0-flash",
    });
  }, [settings]);

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
    setModelForm({
      provider: saved.provider || "Agens",
      base_url: saved.base_url || "https://apihub.agnes-ai.com/v1",
      model: saved.model || "agnes-2.0-flash",
    });
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
                  className="settings-form"
                  onSubmit={saveSettings}
                >
                  <strong>模型设置</strong>
                  <div className="preset-grid" aria-label="模型服务商预设">
                    {modelPresets.map((preset) => (
                      <button
                        type="button"
                        key={preset.provider}
                        className={modelForm.provider === preset.provider ? "selected-tool" : ""}
                        onClick={() => setModelForm(preset)}
                      >
                        {preset.provider}
                      </button>
                    ))}
                  </div>
                  <p className="field-help">可选择预设，也可自行填写兼容 OpenAI 的 Base URL、模型名和 API Key；真实 Key 不会回显。</p>
                  <label>服务商<input name="provider" value={modelForm.provider} onChange={(event) => setModelForm((current) => ({ ...current, provider: event.target.value }))} /></label>
                  <label>Base URL<input name="base_url" value={modelForm.base_url} onChange={(event) => setModelForm((current) => ({ ...current, base_url: event.target.value }))} /></label>
                  <label>模型<input name="model" value={modelForm.model} onChange={(event) => setModelForm((current) => ({ ...current, model: event.target.value }))} /></label>
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