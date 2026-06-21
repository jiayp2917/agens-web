/* ========================================================================
   agens — 文字修仙模拟器 / Web 前端
   单一游戏逻辑入口仍是后端 GameEngine；前端只负责呈现与触发。
   ======================================================================== */

const state = {
  user: null,
  session: null,
  prevCharacter: null,
  theme: "auto",
  authModalOpen: false,
};

const THEME_KEY = "agens.theme";
const THEME_CYCLE = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "自动", light: "浅色", dark: "深色" };

const SAVE_SLOTS = ["slot_1", "slot_2", "slot_3", "slot_4", "slot_5"];
const SAVE_SLOT_LABELS = { slot_1: "档位 1", slot_2: "档位 2", slot_3: "档位 3", slot_4: "档位 4", slot_5: "档位 5", autosave: "(自动)" };

const EVENT_BADGES = {
  narrative: "剧情",
  status: "状态",
  info: "提示",
  error: "错误",
  loading: "加载",
  stream: "推演",
  combat: "战斗",
  character_created: "角色",
  model_failure: "兜底",
  game_over: "终局",
  finale: "飞升",
};

const RENDERED_EVENT_TYPES = new Set(Object.keys(EVENT_BADGES));

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
const appShell = document.querySelector("#app");

/* ====================== 事件接线 ====================== */

document.querySelector("#newGameButton").addEventListener("click", async () => {
  if (!ensureAuthenticated()) return;
  state.session = null;
  state.prevCharacter = null;
  await ensureSession();
  showView("character");
});

document.querySelector("#tutorialButton").addEventListener("click", showTutorial);

document.querySelector("#settingsButton").addEventListener("click", () => showUnifiedSettings({ initialTab: "settings" }));
document.querySelector("#gameSettingsButton").addEventListener("click", () => showUnifiedSettings({ initialTab: "settings" }));

document.querySelector("#modalCloseButton").addEventListener("click", () => modal.close());

document.querySelector("#authButton").addEventListener("click", () => {
  if (state.user) showAccountModal();
  else showAuthModal();
});

document.querySelector("#exitButton").addEventListener("click", () => {
  state.session = null;
  state.prevCharacter = null;
  modal.close();
  renderSession(null);
  showView("home");
  notify("已返回首页。");
});

document.querySelector("#saveGameButton").addEventListener("click", () => showUnifiedSettings({ initialTab: "saves", mode: "save" }));
document.querySelector("#loadGameButton").addEventListener("click", () => showUnifiedSettings({ initialTab: "saves", mode: "load" }));
document.querySelector("#loadHomeButton").addEventListener("click", () => showUnifiedSettings({ initialTab: "saves", mode: "load" }));

document.querySelectorAll("[data-nav]").forEach((button) => {
  button.addEventListener("click", () => {
    state.prevCharacter = null;
    showView(button.dataset.nav);
  });
});

document.querySelectorAll("[data-panel]").forEach((button) => {
  button.addEventListener("click", () => showPanel(button.dataset.panel));
});

document.querySelector("#toTopButton").addEventListener("click", () => {
  const log = document.querySelector("#narrativeLog");
  if (log) log.scrollTop = log.scrollHeight;
  document.querySelector("#toTopButton").setAttribute("hidden", "");
});

/* 角色创建：随机属性、预览、表单提交 */

document.querySelector("#randomAttributes").addEventListener("change", (event) => {
  const disabled = event.currentTarget.checked;
  const inputs = document.querySelectorAll("#attributeInputs input[type='range']");
  inputs.forEach((input) => {
    input.setAttribute("aria-disabled", String(disabled));
    input.disabled = disabled;
  });
  document
    .querySelector("#attributeInputs")
    .setAttribute("aria-disabled", String(disabled));
  document.querySelector("#attrHint").textContent = disabled
    ? "勾选『随机属性』后将由开局生成。"
    : "拖动滑杆自定义六维属性。";
  refreshCharacterPreview();
});

document.querySelectorAll("#attributeInputs input[type='range']").forEach((input) => {
  // 原生已支持 ArrowLeft/Right (±1)、ArrowUp/Down (±1)。
  // 显式增强：Home/End 跳到边界，PageUp/PageDown ±10。
  input.addEventListener("keydown", (event) => {
    const step = 10;
    let next = null;
    if (event.key === "Home") next = Number(input.min || 0);
    else if (event.key === "End") next = Number(input.max || 100);
    else if (event.key === "PageUp") next = Number(input.value) + step;
    else if (event.key === "PageDown") next = Number(input.value) - step;
    if (next === null) return;
    event.preventDefault();
    const max = Number(input.max || 100);
    const min = Number(input.min || 0);
    input.value = String(Math.max(min, Math.min(max, next)));
    const output = input.closest(".attr-row")?.querySelector("output");
    if (output) output.textContent = String(input.value);
    refreshCharacterPreview();
  });
  input.addEventListener("input", () => {
    const output = input.closest(".attr-row")?.querySelector("output");
    if (output) output.textContent = String(input.value);
    refreshCharacterPreview();
  });
});

[
  "game_name",
  "char_name",
  "talent",
  "spirit_root",
  "family_background",
  "difficulty",
].forEach((name) => {
  const el = document.querySelector(`[name="${name}"]`);
  if (el) el.addEventListener("input", refreshCharacterPreview);
  if (el && el.tagName === "SELECT") el.addEventListener("change", refreshCharacterPreview);
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
  await runTurn(`/api/sessions/${state.session.session_id}/start`, payload);
});

/* D 输入提交 */

document.querySelector("#actionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#actionInput");
  const action = input.value.trim();
  if (!action || !state.session) return;
  input.value = "";
  await runTurn(`/api/sessions/${state.session.session_id}/action`, { action });
});

document.querySelector("#narrativeLog").addEventListener("scroll", updateToTopVisibility);

/* 主题切换（首页按钮 + 游戏页内联按钮） */

["#themeToggle", "#themeToggleInline"].forEach((sel) => {
  const button = document.querySelector(sel);
  if (!button) return;
  button.addEventListener("click", () => {
    const idx = THEME_CYCLE.indexOf(state.theme);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
    applyTheme(next);
  });
});

/* ====================== 启动 ====================== */

async function init() {
  loadTheme();
  // 默认随机属性开启 → 滑杆禁用
  document
    .querySelectorAll("#attributeInputs input[type='range']")
    .forEach((input) => {
      input.setAttribute("aria-disabled", "true");
      input.disabled = true;
    });
  refreshCharacterPreview();
  await loadCurrentUser();
  updateAuthButton();
  if (!state.user) {
    showAuthModal();
    return;
  }
  await loadModelSettings().catch(() => null);
}

/* ====================== 主题 ====================== */

function loadTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") {
      applyTheme(stored);
      return;
    }
  } catch (_error) {
    /* localStorage 不可用，忽略 */
  }
  applyTheme("auto");
}

function applyTheme(value) {
  const next = THEME_CYCLE.includes(value) ? value : "auto";
  state.theme = next;
  const html = document.documentElement;
  html.setAttribute("data-theme", next);
  try {
    if (next === "auto") {
      window.localStorage.removeItem(THEME_KEY);
    } else {
      window.localStorage.setItem(THEME_KEY, next);
    }
  } catch (_error) {
    /* 忽略 */
  }
  // 同步两个按钮的视觉态
  ["#themeToggle", "#themeToggleInline"].forEach((sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return;
    btn.setAttribute("aria-pressed", next === "auto" ? "false" : "true");
    const icon = btn.querySelector(".theme-toggle__icon");
    if (icon) {
      icon.classList.remove("theme-toggle__icon--auto", "theme-toggle__icon--light", "theme-toggle__icon--dark");
      icon.classList.add(`theme-toggle__icon--${next}`);
    }
  });
  const label = document.querySelector("#themeToggleLabel");
  if (label) label.textContent = `当前：${THEME_LABELS[next]}`;
}

// 系统主题变化时仅在 auto 模式下响应
if (window.matchMedia) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    if (state.theme === "auto") {
      // 仅触发一次：CSS 会自动响应；这里只需确认 body 仍处于 auto 状态
      document.documentElement.setAttribute("data-theme", "auto");
    }
  };
  if (mq.addEventListener) mq.addEventListener("change", handler);
  else if (mq.addListener) mq.addListener(handler);
}

/* ====================== 网络 ====================== */

async function loadCurrentUser() {
  try {
    const payload = await api("/api/auth/me", { authQuiet: true });
    state.user = payload.user;
  } catch (_error) {
    state.user = null;
  }
}

function ensureAuthenticated() {
  if (state.user) return true;
  showAuthModal();
  notify("请先登录。");
  return false;
}

async function ensureSession() {
  if (!ensureAuthenticated()) throw new Error("请先登录。");
  if (state.session) return state.session;
  const session = await api("/api/sessions", {
    method: "POST",
    body: { title: "新局" },
  });
  state.session = session;
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

async function api(url, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_error) {
      /* keep status text */
    }
    if (response.status === 401 && !options.authQuiet) {
      state.user = null;
      updateAuthButton();
      showAuthModal();
    }
    if (!options.authQuiet) notifyError(String(detail));
    throw new Error(String(detail));
  }
  return response.json();
}

async function loadModelSettings() {
  return api("/api/settings/model");
}

function updateAuthButton() {
  const button = document.querySelector("#authButton");
  if (!button) return;
  button.textContent = state.user ? `${state.user.username}` : "登录";
  button.setAttribute("aria-label", state.user ? "账户" : "登录或注册");
}

/* ====================== 视图路由 ====================== */

function showView(name) {
  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("is-active", key === name);
  });
  if (name === "character") refreshCharacterPreview();
  if (name === "game") {
    const log = document.querySelector("#narrativeLog");
    if (log) {
      requestAnimationFrame(() => {
        log.scrollTop = log.scrollHeight;
        updateToTopVisibility();
      });
    }
  }
}

/* ====================== 渲染：会话 → DOM ====================== */

function renderSession(session) {
  if (!session) {
    state.prevCharacter = null;
    setText("#gameTitle", "尚未开局");
    setText("#characterSummary", "等待角色创建");
    setText("#turnCount", "0");
    setText("#charName", "尚未开局");
    setText("#charSummaryLine", "—");
    setHidden("#charRealmChip", true);
    setText("#charAvatar", "·");
    document.querySelector("#narrativeLog").innerHTML = "";
    document.querySelector("#choices").innerHTML = "";
    resetVitals();
    document.querySelector("#statusList").innerHTML = "";
    setText("#narrativeMeta", "尚未开局");
    setHidden("#streamingIndicator", true);
    setHidden("#toTopButton", true);
    renderFallbackBanner(null);
    return;
  }

  const character = session.character || {};
  const world = session.world || {};

  setText("#gameTitle", character.name || "无名");
  setText(
    "#characterSummary",
    `${character.realm || "练气"}${character.realm_stage || 1}层 · ${character.spirit_root || "未明灵根"} · ${character.talent || "平平无奇"}`
  );
  setText("#turnCount", String(session.turn_count || 0));

  setText("#charName", character.name || "无名");
  setText(
    "#charSummaryLine",
    `${character.family_background || "未定"} · ${world.location || world.region || "未定"}`
  );
  const realmText = `${character.realm || "练气"}${character.realm_stage || 1}层`;
  setText("#charRealmChip", realmText);
  setHidden("#charRealmChip", false);
  setText("#charAvatar", (character.name || "·").slice(0, 1));

  flashVitals(state.prevCharacter, character);
  state.prevCharacter = character;

  renderVitals(character);
  renderStatusList(character, world);
  renderEvents(session.events || []);

  setText("#narrativeMeta", `回合 ${session.turn_count || 0}`);

  renderStreamingIndicator(session.events || []);
  renderFallbackBanner(session.fallback_prompt || null);
  renderChoices(session.choices || []);

  if (session.game_over || session.finale) {
    setEndingState(session);
  }
}

function resetVitals() {
  setText("#hpValue", "0");
  setText("#hpMax", "0");
  setText("#mpValue", "0");
  setText("#mpMax", "0");
  setBar("#hpBar", 0, 0);
  setBar("#mpBar", 0, 0);
}

/* ====================== 渲染：状态条 ====================== */

function renderVitals(character) {
  const hp = Number(character.hp || 0);
  const hpMax = Number(character.hp_max || 0);
  const mp = Number(character.mp || 0);
  const mpMax = Number(character.mp_max || 0);

  setText("#hpValue", String(hp));
  setText("#hpMax", String(hpMax));
  setText("#mpValue", String(mp));
  setText("#mpMax", String(mpMax));

  setBar("#hpBar", hp, hpMax);
  setBar("#mpBar", mp, mpMax);
}

function setBar(selector, value, max) {
  const bar = document.querySelector(selector);
  if (!bar) return;
  const fill = bar.querySelector("span");
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  if (fill) fill.style.setProperty("--bar-fill", String(ratio));
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", String(max));
  bar.setAttribute("aria-valuenow", String(value));
  bar.classList.toggle("is-low", max > 0 && ratio < 0.25);
}

function flashVitals(prev, next) {
  if (!prev || !next) return;
  const flashOnce = (key, oldVal, newVal, selector) => {
    if (oldVal > newVal) {
      const node = document.querySelector(selector);
      if (!node) return;
      node.classList.remove("is-decreasing");
      void node.offsetWidth;
      node.classList.add("is-decreasing");
      window.setTimeout(() => node.classList.remove("is-decreasing"), 1600);
    }
  };
  flashOnce("hp", prev.hp || 0, next.hp || 0, "#hpValue");
  flashOnce("mp", prev.mp || 0, next.mp || 0, "#mpValue");
}

function renderStatusList(character, world) {
  const rows = [];
  const push = (key, value) => {
    if (value === undefined || value === null || value === "") return;
    rows.push([key, value]);
  };
  push("境界", `${character.realm || "练气"}${character.realm_stage || 1}层`);
  push("灵根", character.spirit_root || "");
  if (character.spirit_root_grade) push("灵根品", character.spirit_root_grade);
  push("寿元", character.lifespan ? `${character.lifespan} 岁` : "");
  push("年龄", character.age || "");
  push("悟性", `${character.attributes?.comprehension ?? "—"}`);
  push("根骨", `${character.attributes?.root_bone ?? "—"}`);
  push("心性", `${character.attributes?.willpower ?? "—"}`);
  push("体魄", `${character.attributes?.physique ?? "—"}`);
  push("神识", `${character.attributes?.spiritual_sense ?? "—"}`);
  push("气运", character.luck || "");
  push("灵石", character.gold ?? "");
  push("修为", `${character.experience ?? 0} / ${character.experience_to_next ?? "—"}`);
  push("机缘", character.insight ?? "");
  push("地点", world.location || world.region || "");

  document.querySelector("#statusList").innerHTML = rows
    .map(
      ([key, value]) =>
        `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>`
    )
    .join("");
}

/* ====================== 渲染：叙事 ====================== */

function renderEvents(events) {
  const log = document.querySelector("#narrativeLog");
  if (!log) return;

  const wasNearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 32;

  const visible = events.filter((item) => RENDERED_EVENT_TYPES.has(item.type));
  log.innerHTML = visible
    .map((item) => {
      const text = item.text || item.status || "";
      const badge = escapeHtml(EVENT_BADGES[item.type] || item.type);
      const turn = item.turn ? `回合 ${item.turn}` : "";
      const meta = [badge, turn].filter(Boolean).map((t) => `<span>${escapeHtml(t)}</span>`).join("");
      return `<article class="event event--${escapeHtml(item.type)}" data-turn="${escapeHtml(item.turn || "")}">
        <header class="event-meta">${meta}</header>
        <div class="event-body">${escapeHtml(text)}</div>
      </article>`;
    })
    .join("");

  if (wasNearBottom) {
    log.scrollTop = log.scrollHeight;
    setHidden("#toTopButton", true);
  } else {
    setHidden("#toTopButton", false);
  }
}

function updateToTopVisibility() {
  const log = document.querySelector("#narrativeLog");
  if (!log) return;
  const distance = log.scrollHeight - log.scrollTop - log.clientHeight;
  setHidden("#toTopButton", distance < 32);
}

function renderStreamingIndicator(events) {
  const indicator = document.querySelector("#streamingIndicator");
  if (!indicator) return;
  const last = events[events.length - 1];
  const streaming =
    last &&
    (last.type === "stream" || last.type === "loading") &&
    last.done === false;
  setHidden("#streamingIndicator", !streaming);
}

/* ====================== 渲染：兜底横幅 ====================== */

function renderFallbackBanner(prompt) {
  const panel = document.querySelector(".narrative-panel");
  if (!panel) return;
  const existing = panel.querySelector(".fallback-banner");
  if (existing) existing.remove();
  // 兜底未激活：清除页面 fallback 状态
  if (!prompt || !prompt.active) {
    document.body.classList.remove("is-fallback");
    return;
  }
  document.body.classList.add("is-fallback");

  const banner = document.createElement("aside");
  banner.className = "fallback-banner fallback-banner--hero";
  banner.setAttribute("role", "status");

  const plaque = document.createElement("aside");
  plaque.className = "fallback-plaque";
  plaque.setAttribute("aria-hidden", "true");
  plaque.innerHTML = `<span>浮生若梦</span>`;

  const warningText = prompt.text || "模型暂不可用，当前以本地故事继续。";
  banner.innerHTML = `
    <div class="fallback-banner__row">
      <span class="badge badge--model_failure">兜底</span>
      <span class="fallback-banner__text">${escapeHtml(warningText)}</span>
    </div>
    <div class="fallback-banner__actions">
      <button class="command-button ghost fallback-action" id="fallbackContinueButton" type="button">继续本局</button>
      <button class="command-button danger fallback-action" id="fallbackEndButton" type="button">结束本局</button>
    </div>
  `;
  panel.insertBefore(banner, panel.firstChild.nextSibling); // after toolbar
  panel.insertBefore(plaque, panel.firstChild); // 浮生若梦 ribbon at very top

  banner.querySelector("#fallbackContinueButton").addEventListener("click", async () => {
    if (!state.session) return;
    const submit = document.querySelector("#fallbackContinueButton");
    submit.classList.add("is-busy");
    try {
      await runTurn(`/api/sessions/${state.session.session_id}/action`, {
        action: "继续本局",
      });
    } finally {
      submit.classList.remove("is-busy");
    }
  });
  banner.querySelector("#fallbackEndButton").addEventListener("click", async () => {
    if (!state.session) return;
    const session = await api(`/api/sessions/${state.session.session_id}/end`, {
      method: "POST",
      body: { reason: "玩家结束本局。" },
    });
    state.session = session;
    renderSession(session);
    showView("ending");
  });
}

/* ====================== 渲染：选项 ====================== */

function renderChoices(choices) {
  const html = choices
    .map((choice, index) => {
      const label = String.fromCharCode(65 + index);
      return `<button class="choice" type="button" data-choice-index="${index}" aria-label="${escapeAttr("选项 " + label + "：" + choice)}">
        <span class="choice__art" aria-hidden="true"></span>
        <span class="choice-key" aria-hidden="true">${label}</span>
        <span class="choice-text">${escapeHtml(choice)}</span>
      </button>`;
    })
    .join("");
  ["#choices", "#choicesSidebar"].forEach((sel) => {
    const container = document.querySelector(sel);
    if (!container) return;
    container.innerHTML = html;
    container.querySelectorAll("[data-choice-index]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!state.session) return;
        // 双容器时同时给两个按钮加 busy
        document
          .querySelectorAll(`[data-choice-index="${button.dataset.choiceIndex}"]`)
          .forEach((b) => b.classList.add("is-busy"));
        try {
          await runTurn(
            `/api/sessions/${state.session.session_id}/choice`,
            { choice_index: Number(button.dataset.choiceIndex) }
          );
        } finally {
          document
            .querySelectorAll(`[data-choice-index="${button.dataset.choiceIndex}"]`)
            .forEach((b) => b.classList.remove("is-busy"));
        }
      });
    });
  });
}

/* ====================== 渲染：终局 ====================== */

function setEndingState(session) {
  const view = document.querySelector("#endingView");
  const character = session.character || {};
  const world = session.world || {};

  let kind = "ended";
  let title = "尘埃落定";
  let reason = session.error || "因果已定。";

  if (session.finale) {
    kind = "ascension";
    title = "飞升";
    reason = session.error || "飞升成仙，超脱凡尘，修仙之路圆满。";
  } else if (session.error && session.error.includes("生命值")) {
    kind = "death";
    title = "陨落";
    reason = session.error;
  } else if (session.error && session.error.includes("模型不可用")) {
    kind = "ended";
    title = "本局结束";
    reason = session.error;
  } else if (session.error) {
    kind = "ended";
    title = "本局结束";
    reason = session.error;
  } else if (session.game_over) {
    kind = "death";
    title = "陨落";
  }

  view.dataset.ending = kind;
  setText("#endingKind", kind === "ascension" ? "飞升" : kind === "death" ? "陨落" : "离开");
  setText("#endingTitle", title);
  setText("#endingReason", reason);

  setText("#endName", character.name || "—");
  setText("#endRealm", `${character.realm || "练气"}${character.realm_stage || 1}层`);
  setText("#endTurns", String(session.turn_count || 0));
  setText("#endDays", String(world.day_count || "—"));
  setText("#endCompanions", String((world.npcs_present || []).length));
  setText("#endTechniques", String((character.techniques || []).length));
}

/* ====================== 角色创建预览 ====================== */

function refreshCharacterPreview() {
  const form = document.querySelector("#characterForm");
  if (!form) return;
  const fd = new FormData(form);
  const charName = text(fd.get("char_name")) || "未填";
  const root = text(fd.get("spirit_root")) || "金灵根";
  const family = text(fd.get("family_background")) || "农家";
  const diff = text(fd.get("difficulty")) || "普通";

  setText("#previewName", charName);
  setText("#previewRoot", root);
  setText("#previewFamily", family);
  setText("#previewDifficulty", diff);
}

/* ====================== 模态 ====================== */

function showPanel(name) {
  if (!state.session) return;
  const panels = state.session.panels || {};
  const titles = {
    inventory: "背包",
    skills: "功法",
    quests: "任务",
    map: "地图",
  };
  const body = panels[name];
  const bodyHtml = body
    ? `<pre class="field-hint" style="white-space:pre-wrap">${escapeHtml(body)}</pre>`
    : `<p class="field-hint">暂无内容。</p>`;
  openModal(titles[name] || "信息", bodyHtml);
}

function showTutorial() {
  openModal(
    "教程",
    `<div class="stack">
      <p>开局后，天道会给出 A / B / C 三个行动方向；你也可以在底部 D 输入框写下自己的行动。</p>
      <p>存档、读档、背包、功法、任务、地图都在游戏页工具区。气血、灵力和回合数会随状态更新。</p>
      <p>模型暂不可用时，本局可以切入本地故事继续，也可随时结束本局。</p>
      <p class="muted-line">
        当前仅开放引导模式；
        <span aria-disabled="true">小说模式</span> 与
        <span aria-disabled="true">游戏模式</span> 暂不开放。
      </p>
    </div>`
  );
}

async function showUnifiedSettings({ initialTab = "settings", mode = "save" } = {}) {
  if (!ensureAuthenticated()) return;
  let settings = {};
  let settingsError = "";
  let saves = [];
  try {
    settings = await loadModelSettings();
  } catch (error) {
    settingsError = error.message || "只有管理员可以管理模型设置。";
  }
  try {
    await ensureSession();
    saves = await api("/api/saves");
  } catch (_error) {
    /* 存档未加载；表格为空 */
  }

  // 把存档按 slot 名归并
  const saveBySlot = {};
  saves.forEach((s) => {
    saveBySlot[s.name] = s;
  });

  const providerOptions = ["Agens", "OpenAI", "Anthropic", "Custom"]
    .map(
      (p) =>
        `<option value="${escapeAttr(p)}" ${p === (settings.provider || "Agens") ? "selected" : ""}>${escapeHtml(p)}</option>`
    )
    .join("");

  const settingsPane = settingsError
    ? `
    <div class="auth-note" role="status">
      <strong>模型设置受保护</strong>
      <p>${escapeHtml(settingsError)}</p>
    </div>
  `
    : `
    <form id="settingsForm" class="stack">
      <label>
        <span>服务商</span>
        <select name="provider">${providerOptions}</select>
      </label>
      <label>
        <span>Base URL</span>
        <input name="base_url" type="url" value="${escapeAttr(settings.base_url || "")}" autocomplete="off" />
      </label>
      <label>
        <span>模型</span>
        <input name="model" type="text" value="${escapeAttr(settings.model || "")}" autocomplete="off" />
      </label>
      <label>
        <span>API Key</span>
        <input name="api_key" type="password" autocomplete="off" placeholder="${escapeAttr(settings.api_key_masked || "<unset>")}" />
        <span class="field-hint">
          当前 Key 状态：<span class="key-chip ${settings.api_key_set ? "is-set" : "is-empty"}">${settings.api_key_set ? "已配置" : "未配置"}</span>，前端不会显示明文。
        </span>
      </label>
      <p class="muted-line">
        当前仅开放引导模式：A / B / C 由模型生成，D 为自由输入；
        <span aria-disabled="true">小说模式</span> 与
        <span aria-disabled="true">游戏模式</span> 暂不开放。
      </p>
    </form>
  `;

  // 存档表：5 槽 + 自动槽
  const allSlotNames = [...SAVE_SLOTS, "autosave"];
  const savesRows = allSlotNames
    .map((slotName) => {
      const save = saveBySlot[slotName];
      const empty = !save;
      const label = SAVE_SLOT_LABELS[slotName] || slotName;
      const cls = empty ? "saves-table__row is-empty" : "saves-table__row";
      return `<div class="${cls}" data-slot="${escapeAttr(slotName)}" ${empty ? "" : `data-load-name="${escapeAttr(slotName)}"`} role="button" tabindex="0" aria-selected="false">
        <div class="saves-table__cell">${escapeHtml(label)}</div>
        <div class="saves-table__cell">${empty ? "—" : escapeHtml(save.char_name || "—")}</div>
        <div class="saves-table__cell">${empty ? "—" : escapeHtml(save.realm || "—")}</div>
        <div class="saves-table__cell">${empty ? "—" : escapeHtml(String(save.turn_count || 0))}</div>
        <div class="saves-table__cell">${empty ? "—" : escapeHtml(save.updated_at || save.created_at || "—")}</div>
      </div>`;
    })
    .join("");

  const savesPane = `
    <div class="saves-table" role="grid" aria-label="存档列表">
      <div class="saves-table__row saves-table__head" role="row">
        <div class="saves-table__cell" role="columnheader">档位</div>
        <div class="saves-table__cell" role="columnheader">角色</div>
        <div class="saves-table__cell" role="columnheader">境界</div>
        <div class="saves-table__cell" role="columnheader">回合</div>
        <div class="saves-table__cell" role="columnheader">更新时间</div>
      </div>
      ${savesRows}
    </div>
    <p class="field-hint">点击已存在的存档行直接读档；当前局未开始时不能存档。</p>
  `;

  const body = `
    <div class="unified-tabs" role="tablist">
      <button class="unified-tab ${initialTab === "settings" ? "is-active" : ""}" data-tab="settings" type="button" role="tab" aria-selected="${initialTab === "settings"}">设置</button>
      <button class="unified-tab ${initialTab === "saves" ? "is-active" : ""}" data-tab="saves" type="button" role="tab" aria-selected="${initialTab === "saves"}">存档</button>
    </div>
    <div class="unified-pane ${initialTab === "settings" ? "is-active" : ""}" data-pane="settings">${settingsPane}</div>
    <div class="unified-pane ${initialTab === "saves" ? "is-active" : ""}" data-pane="saves">${savesPane}</div>
    <div class="unified-footer">
      <button id="unifiedSaveButton" class="command-button primary" type="button" data-active-tab="${initialTab}">
        <span class="spinner" aria-hidden="true"></span>
        <span class="label">${initialTab === "settings" ? "保存设置" : "保存到选中档"}</span>
      </button>
      <button class="command-button ghost" data-close-modal type="button">关闭</button>
    </div>
  `;

  openModal("设置与存档", body);

  // Tab 切换
  document.querySelectorAll(".unified-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      document.querySelectorAll(".unified-tab").forEach((t) => {
        const active = t === tab;
        t.classList.toggle("is-active", active);
        t.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll(".unified-pane").forEach((p) => {
        p.classList.toggle("is-active", p.dataset.pane === target);
      });
      const saveBtn = document.querySelector("#unifiedSaveButton");
      if (saveBtn) {
        saveBtn.dataset.activeTab = target;
        const label = saveBtn.querySelector(".label");
        if (label) label.textContent = target === "settings" ? "保存设置" : "保存到选中档";
      }
    });
  });

  // 关闭
  document.querySelectorAll("[data-close-modal]").forEach((b) =>
    b.addEventListener("click", () => modal.close())
  );

  // 保存（按当前 tab）
  const saveButton = document.querySelector("#unifiedSaveButton");
  saveButton.addEventListener("click", async () => {
    const activeTab = saveButton.dataset.activeTab;
    saveButton.classList.add("is-busy");
    try {
      if (activeTab === "settings") {
        const settingsForm = document.querySelector("#settingsForm");
        if (!settingsForm) {
          notify("只有管理员可以保存模型设置。");
          return;
        }
        const form = new FormData(settingsForm);
        const saved = await api("/api/settings/model", {
          method: "POST",
          body: {
            provider: text(form.get("provider")),
            base_url: text(form.get("base_url")),
            model: text(form.get("model")),
            api_key: text(form.get("api_key")),
          },
        });
        notify(`设置已保存：${saved.provider} / ${saved.model}`);
      } else if (activeTab === "saves") {
        if (!state.session) {
          notify("尚未创建会话，无法存档。");
          return;
        }
        if (mode === "load") {
          notify("当前是读档页；如需存档，请切换到上一局后使用存档。");
          return;
        }
        const selectedSlot = document.querySelector("[data-slot].is-active")?.dataset.slot;
        // 默认选第一个空槽
        const slotName = selectedSlot || SAVE_SLOTS[0];
        const result = await api(`/api/sessions/${state.session.session_id}/save`, {
          method: "POST",
          body: { name: slotName },
        });
        state.session = result.session;
        renderSession(state.session);
        notify(`已保存：${result.save.name}`);
      }
    } finally {
      saveButton.classList.remove("is-busy");
    }
  });

  // 存档行选择
  document.querySelectorAll(".saves-table__row[data-slot]").forEach((row) => {
    row.addEventListener("click", () => selectSaveRow(row));
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectSaveRow(row);
      }
    });
  });

  // 读档行点击
  document.querySelectorAll(".saves-table__row[data-load-name]").forEach((row) => {
    const handler = async () => {
      if (mode !== "load") return;
      if (!state.session) {
        await ensureSession();
      }
      const session = await api(`/api/sessions/${state.session.session_id}/load`, {
        method: "POST",
        body: { name: row.dataset.loadName },
      });
      state.session = session;
      state.prevCharacter = null;
      renderSession(session);
      modal.close();
      showView("game");
    };
    row.addEventListener("dblclick", handler);
    row.addEventListener("keydown", (e) => {
      if (mode === "load" && e.key === "Enter") {
        e.preventDefault();
        handler();
      }
    });
  });
}

function selectSaveRow(row) {
  document.querySelectorAll(".saves-table__row[data-slot]").forEach((item) => {
    const selected = item === row;
    item.classList.toggle("is-active", selected);
    item.setAttribute("aria-selected", selected ? "true" : "false");
  });
}

function showAuthModal() {
  state.authModalOpen = true;
  const body = `
    <div class="auth-layout">
      <form id="loginForm" class="auth-card stack">
        <div>
          <p class="eyebrow">登录</p>
          <h3>继续修行</h3>
        </div>
        <label>
          <span>用户名</span>
          <input name="username" type="text" autocomplete="username" required minlength="2" maxlength="40" />
        </label>
        <label>
          <span>密码</span>
          <input name="password" type="password" autocomplete="current-password" required />
        </label>
        <button class="command-button primary" type="submit">
          <span class="spinner" aria-hidden="true"></span>
          <span class="label">登录</span>
        </button>
      </form>
      <form id="registerForm" class="auth-card stack">
        <div>
          <p class="eyebrow">邀请码注册</p>
          <h3>创建道号</h3>
        </div>
        <label>
          <span>用户名</span>
          <input name="username" type="text" autocomplete="username" required minlength="2" maxlength="40" />
        </label>
        <label>
          <span>密码</span>
          <input name="password" type="password" autocomplete="new-password" required minlength="8" />
        </label>
        <label>
          <span>邀请码</span>
          <input name="invite_code" type="password" autocomplete="off" required minlength="8" />
        </label>
        <button class="command-button" type="submit">
          <span class="spinner" aria-hidden="true"></span>
          <span class="label">注册并登录</span>
        </button>
      </form>
    </div>
  `;
  openModal("登录 / 注册", body);

  document.querySelector("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    button.classList.add("is-busy");
    try {
      const form = new FormData(event.currentTarget);
      const payload = await api("/api/auth/login", {
        method: "POST",
        body: {
          username: text(form.get("username")),
          password: String(form.get("password") || ""),
        },
      });
      state.user = payload.user;
      updateAuthButton();
      modal.close();
      notify("已登录。");
    } finally {
      button.classList.remove("is-busy");
    }
  });

  document.querySelector("#registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    button.classList.add("is-busy");
    try {
      const form = new FormData(event.currentTarget);
      const payload = await api("/api/auth/register", {
        method: "POST",
        body: {
          username: text(form.get("username")),
          password: String(form.get("password") || ""),
          invite_code: String(form.get("invite_code") || ""),
        },
      });
      state.user = payload.user;
      updateAuthButton();
      modal.close();
      notify("已注册并登录。");
    } finally {
      button.classList.remove("is-busy");
    }
  });
}

function showAccountModal() {
  const username = state.user?.username || "未登录";
  const role = state.user?.is_admin ? "管理员" : "玩家";
  openModal(
    "账户",
    `<div class="stack">
      <p class="auth-note"><strong>${escapeHtml(username)}</strong><br /><span>${escapeHtml(role)}</span></p>
      <button id="logoutButton" class="command-button danger" type="button">退出登录</button>
    </div>`
  );
  document.querySelector("#logoutButton").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST", body: {} });
    state.user = null;
    state.session = null;
    state.prevCharacter = null;
    updateAuthButton();
    renderSession(null);
    modal.close();
    showView("home");
    notify("已退出登录。");
  });
}

function openModal(title, body) {
  modalTitle.textContent = title;
  modalBody.innerHTML = body;
  if (typeof modal.showModal === "function") {
    modal.showModal();
  } else {
    modal.setAttribute("open", "");
  }
}

/* ====================== 工具：吐司、忙碌 ====================== */

function notify(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
}

function notifyError(message) {
  // F-109: 错误信息用 assertive live region，screen reader 立即打断当前朗读
  const errEl = document.querySelector("#toastError");
  if (!errEl) {
    // 后备：退回普通 toast
    notify(message);
    return;
  }
  errEl.textContent = message;
  errEl.removeAttribute("hidden");
  errEl.classList.add("is-visible");
  window.setTimeout(() => {
    errEl.classList.remove("is-visible");
    errEl.setAttribute("hidden", "");
  }, 4500);
}

function setBusy(busy) {
  appShell.classList.toggle("is-busy", busy);
  document.querySelectorAll("button, input, select, textarea").forEach((element) => {
    if (element.closest("#modal")) return;
    if (busy) {
      element.setAttribute("data-prev-disabled", String(element.disabled));
      element.disabled = true;
    } else if (element.hasAttribute("data-prev-disabled")) {
      element.disabled = element.getAttribute("data-prev-disabled") === "true";
      element.removeAttribute("data-prev-disabled");
    }
  });
  const submit = document.querySelector("#actionSubmit");
  if (submit) {
    submit.classList.toggle("is-busy", busy);
    const label = submit.querySelector(".label");
    if (label) label.textContent = busy ? "推演中…" : "发送";
  }
}

/* ====================== DOM 小工具 ====================== */

function setText(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.textContent = String(value);
}

function setHidden(selector, hidden) {
  const el = document.querySelector(selector);
  if (!el) return;
  if (hidden) el.setAttribute("hidden", "");
  else el.removeAttribute("hidden");
}

function text(value) {
  return String(value || "").trim();
}

function number(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 50;
  return Math.max(0, Math.min(100, Math.round(parsed)));
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
