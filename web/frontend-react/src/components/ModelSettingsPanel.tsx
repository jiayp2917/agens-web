import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, Settings } from "lucide-react";
import { api, ModelSettings, User, type AuthMode } from "../lib/api";
import { modelPresets } from "../lib/catalog";

export function ModelSettingsPanel({
  user,
  settings,
  setSettings,
  setMessage,
  onAuth,
}: {
  user: User | null;
  settings: ModelSettings | null;
  setSettings: (settings: ModelSettings) => void;
  setMessage: (message: string) => void;
  onAuth: (mode: AuthMode) => void;
}) {
  const [modelForm, setModelForm] = useState({
    provider: "Agens",
    base_url: "https://apihub.agnes-ai.com/v1",
    model: "agnes-2.0-flash",
  });

  useEffect(() => {
    if (!settings) return;
    setModelForm({
      provider: settings.provider || "Agens",
      base_url: settings.base_url || "https://apihub.agnes-ai.com/v1",
      model: settings.model || "agnes-2.0-flash",
    });
  }, [settings]);

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
  );
}
