const state = {
  user: null,
  session: null,
  sound: false,
  theme: "paper",
};

const views = {
  home: document.querySelector("#homeView"),
  character: document.querySelector("#characterView"),
  game: document.querySelector("#gameView"),
  ending: document.querySelector("#endingView"),
};

const modal = document.querySelector("#modal");
const modalTitle = document.querySelector("#modalTitle");
const modalBody = document.querySelector("#modalBody");
const toast = document.querySelector("#toast");

document.querySelector("#newGameButton").addEventListener("click", async () => {
  await ensureSession();
  showView("character");
});
document.querySelector("#loadHomeButton").addEventListener("click", () => showLoadDialog());
document.querySelector("#tutorialButton").addEventListener("click", showTutorial);
document.querySelector("#settingsButton").addEventListener("click", showSettings);
document.querySelector("#gameSettingsButton").addEventListener("click", showSettings);
document.querySelector("#modalCloseButton").addEventListener("click", () => modal.close());
document.querySelector("#exitButton").addEventListener("click", () => {
  state.session = null;
  renderSession(null);
  notify("已返回首页。");
});
document.querySelector("#restartButton").addEventListener("click", () => showView("character"));
document.querySelector("#saveGameButton").addEventListener("click", () => showSaveDialog());
document.querySelector("#loadGameButton").addEventListener("click", () => showLoadDialog());
document.querySelector("#soundToggle").addEventListener("click", () => {
  state.sound = !state.sound;
  document.querySelector("#soundToggle").setAttribute("aria-pressed", String(state.sound));
  notify(state.sound ? "背景音乐已开启。" : "背景音乐已关闭。");
});

document.querySelectorAll("[data-nav]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.nav));
});

document.querySelectorAll("[data-panel]").forEach((button) => {
  button.addEventListener("click", () => showPanel(button.dataset.panel));
});

document.querySelector("#randomAttributes").addEventListener("change", (event) => {
  const disabled = event.currentTarget.checked;
  document.querySelector("#attributeInputs").setAttribute("aria-disabled", String(disabled));
  document.querySelectorAll("#attributeInputs input").forEach((input) => {
    input.disabled = disabled;
  });
});

document.querySelector("#characterForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await ensureSession();
  const form = new FormData(event.currentTarget);
  const randomize = Boolean(form.get("randomize_attributes"));
  const payload = {
    game_name: text(form.get("game_name")),
    char_name: text(form.get("char_name")),
    talent: text(form.get("talent")),
    spirit_root: text(form.get("spirit_root")),
    family_background: text(form.get("family_background")),
    difficulty: text(form.get("difficulty")),
    randomize_attributes: randomize,
    attributes: randomize
      ? {}
      : {
          root_bone: number(form.get("root_bone")),
          comprehension: number(form.get("comprehension")),
          luck: number(form.get("luck")),
          willpower: number(form.get("willpower")),
          physique: number(form.get("physique")),
          spiritual_sense: number(form.get("spiritual_sense")),
        },
  };
  const session = await api(`/api/sessions/${state.session.session_id}/start`, {
    method: "POST",
    body: payload,
  });
  state.session = session;
  renderSession(session);
  showView(session.game_over || session.finale ? "ending" : "game");
});

document.querySelector("#actionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#actionInput");
  const action = input.value.trim();
  if (!action || !state.session) return;
  input.value = "";
  await runTurn(`/api/sessions/${state.session.session_id}/action`, { action });
});

async function init() {
  document.querySelectorAll("#attributeInputs input").forEach((input) => {
    input.disabled = true;
  });
  await login();
  await loadModelSettings();
}

async function login() {
  state.user = await api("/api/users/login", { method: "POST", body: { username: "local" } });
}

async function ensureSession() {
  if (state.session) return state.session;
  const session = await api("/api/sessions", {
    method: "POST",
    body: { user_id: state.user?.id || "", title: "新局" },
  });
  state.session = session;
  renderSession(session);
  return session;
}

async function runTurn(url, body) {
  try {
    setBusy(true);
    const session = await api(url, { method: "POST", body });
    state.session = session;
    renderSession(session);
    showView(session.game_over || session.finale ? "ending" : "game");
  } finally {
    setBusy(false);
  }
}

function renderSession(session) {
  if (!session) {
    document.querySelector("#gameTitle").textContent = "尚未开局";
    document.querySelector("#characterSummary").textContent = "等待角色创建";
    document.querySelector("#turnCount").textContent = "0";
    document.querySelector("#narrativeLog").innerHTML = "";
    document.querySelector("#choices").innerHTML = "";
    return;
  }

  const character = session.character || {};
  document.querySelector("#gameTitle").textContent = character.name || "无名";
  document.querySelector("#characterSummary").textContent =
    `${character.realm || "练气"}${character.realm_stage || 1}层 · ${character.spirit_root || "未明灵根"} · ${character.talent || "平平无奇"}`;
  document.querySelector("#turnCount").textContent = String(session.turn_count || 0);

  renderStats(character, session.world || {});
  renderEvents(session.events || []);
  renderChoices(session.choices || [], session.fallback_prompt || {});

  if (session.game_over || session.finale) {
    document.querySelector("#endingTitle").textContent = session.finale ? "飞升" : "本局结束";
    document.querySelector("#endingReason").textContent = session.error || "因果已定。";
  }
}

function renderStats(character, world) {
  const rows = [
    ["境界", `${character.realm || "练气"}${character.realm_stage || 1}层`],
    ["气血", `${character.hp || 0}/${character.hp_max || 0}`],
    ["灵力", `${character.mp || 0}/${character.mp_max || 0}`],
    ["年龄", character.age || 16],
    ["家世", character.family_background || "未定"],
    ["地点", world.location || "未定"],
  ];
  document.querySelector("#statusList").innerHTML = rows
    .map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>`)
    .join("");
}

function renderEvents(events) {
  const visible = events.filter((item) => ["narrative", "info", "error", "status", "game_over", "finale"].includes(item.type));
  document.querySelector("#narrativeLog").innerHTML = visible
    .map((item) => {
      const textValue = item.text || item.status || "";
      return `<article class="event ${escapeHtml(item.type)}">${escapeHtml(textValue)}</article>`;
    })
    .join("");
  const log = document.querySelector("#narrativeLog");
  log.scrollTop = log.scrollHeight;
}

function renderChoices(choices, fallbackPrompt = {}) {
  const promptHtml = fallbackPrompt.active
    ? `<div class="fallback-choice" role="status">
        <p>${escapeHtml(fallbackPrompt.text || "模型暂不可用，当前以本地故事兜底继续。")}</p>
        <div class="fallback-actions">
          <button id="fallbackContinueButton" class="command-button" type="button">继续本局</button>
          <button id="fallbackEndButton" class="command-button danger" type="button">结束本局</button>
        </div>
      </div>`
    : "";
  document.querySelector("#choices").innerHTML = promptHtml + choices
    .map((choice, index) => {
      const label = String.fromCharCode(65 + index);
      return `<button type="button" data-choice-index="${index}">${label}. ${escapeHtml(choice)}</button>`;
    })
    .join("");
  document.querySelector("#fallbackContinueButton")?.addEventListener("click", () => {
    notify("继续当前本地故事。");
  });
  document.querySelector("#fallbackEndButton")?.addEventListener("click", async () => {
    if (!state.session) return;
    const session = await api(`/api/sessions/${state.session.session_id}/end`, {
      method: "POST",
      body: { reason: "玩家结束本局。" },
    });
    state.session = session;
    renderSession(session);
    showView("ending");
  });
  document.querySelectorAll("[data-choice-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.session) return;
      await runTurn(`/api/sessions/${state.session.session_id}/choice`, {
        choice_index: Number(button.dataset.choiceIndex),
      });
    });
  });
}

function showPanel(name) {
  if (!state.session) return;
  const panels = state.session.panels || {};
  const titles = {
    inventory: "背包",
    skills: "功法",
    quests: "任务",
    map: "地图",
  };
  openModal(titles[name] || "信息", `<pre class="plain-text">${escapeHtml(panels[name] || "暂无内容。")}</pre>`);
}

function showTutorial() {
  openModal(
    "教程",
    `<div class="stack">
      <p>开局后，天道会给出 A/B/C 三个行动方向。你也可以在底部 D 输入框写下自己的行动。</p>
      <p>存档、读档、背包、功法、任务、地图都在游戏页工具区。模型不可用时，本局可以切入本地故事继续。</p>
      <p>小说模式和游戏模式暂不开放，当前版本只运行引导模式。</p>
    </div>`
  );
}

async function showSettings() {
  const settings = await loadModelSettings();
  openModal(
    "设置",
    `<form id="settingsForm">
      <label><span>服务商</span><input name="provider" value="${escapeAttr(settings.provider || "Agens")}" /></label>
      <label><span>Base URL</span><input name="base_url" value="${escapeAttr(settings.base_url || "")}" /></label>
      <label><span>模型</span><input name="model" value="${escapeAttr(settings.model || "")}" /></label>
      <label><span>API Key</span><input name="api_key" type="password" autocomplete="off" placeholder="${escapeAttr(settings.api_key_masked || "<unset>")}" /></label>
      <label><span>主题色</span><select name="theme"><option value="paper">宣纸暖色</option><option value="teal">青玉色</option></select></label>
      <fieldset class="mode-fieldset">
        <legend>游玩模式</legend>
        <label class="mode-option selected"><input type="radio" checked /><span>引导模式</span></label>
        <label class="mode-option disabled"><input type="radio" disabled /><span>小说模式</span></label>
        <label class="mode-option disabled"><input type="radio" disabled /><span>游戏模式</span></label>
      </fieldset>
      <button class="command-button primary wide" type="submit">保存设置</button>
      <p class="muted-line">当前 Key 状态：${settings.api_key_set ? "已配置" : "未配置"}，前端不会显示明文。</p>
    </form>`
  );
  document.querySelector("#settingsForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const saved = await api("/api/settings/model", {
      method: "POST",
      body: {
        provider: text(form.get("provider")),
        base_url: text(form.get("base_url")),
        model: text(form.get("model")),
        api_key: text(form.get("api_key")),
      },
    });
    state.theme = text(form.get("theme")) || "paper";
    notify(`设置已保存：${saved.provider} / ${saved.model}`);
    modal.close();
  });
}

async function showSaveDialog() {
  if (!state.session) return notify("尚未创建会话。");
  openModal(
    "存档",
    `<form id="saveForm">
      <label><span>档位名称</span><input name="name" value="slot_1" /></label>
      <button class="command-button primary wide" type="submit">保存</button>
    </form>`
  );
  document.querySelector("#saveForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = text(new FormData(event.currentTarget).get("name")) || "slot_1";
    const result = await api(`/api/sessions/${state.session.session_id}/save`, {
      method: "POST",
      body: { name },
    });
    state.session = result.session;
    renderSession(state.session);
    notify(`已保存：${result.save.name}`);
    modal.close();
  });
}

async function showLoadDialog() {
  await ensureSession();
  const saves = await api(`/api/saves?user_id=${encodeURIComponent(state.user?.id || "")}`);
  const body = saves.length
    ? `<div class="stack">${saves
        .map(
          (save) =>
            `<button class="command-button wide" data-load-name="${escapeAttr(save.name)}" type="button">
              ${escapeHtml(save.name)} · ${escapeHtml(save.char_name)} · ${escapeHtml(save.realm)} · T${save.turn_count}
            </button>`
        )
        .join("")}</div>`
    : `<p>暂无存档。</p>`;
  openModal("读档", body);
  document.querySelectorAll("[data-load-name]").forEach((button) => {
    button.addEventListener("click", async () => {
      const session = await api(`/api/sessions/${state.session.session_id}/load`, {
        method: "POST",
        body: { name: button.dataset.loadName },
      });
      state.session = session;
      renderSession(session);
      modal.close();
      showView("game");
    });
  });
}

async function loadModelSettings() {
  return api("/api/settings/model");
}

function showView(name) {
  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("is-active", key === name);
  });
}

function openModal(title, body) {
  modalTitle.textContent = title;
  modalBody.innerHTML = body;
  modal.showModal();
}

function notify(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
}

function setBusy(busy) {
  document.querySelectorAll("button, input, select").forEach((element) => {
    if (element.closest("#modal")) return;
    element.toggleAttribute("aria-busy", busy);
  });
}

async function api(url, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
  };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_error) {
      // Keep status text.
    }
    notify(String(detail));
    throw new Error(String(detail));
  }
  return response.json();
}

function text(value) {
  return String(value || "").trim();
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.min(100, Math.round(parsed))) : 50;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

init().catch((error) => notify(error.message));
