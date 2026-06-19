/* ========================================================================
   agens — 文字修仙模拟器 / Web 前端
   单一游戏逻辑入口仍是后端 GameEngine；前端只负责呈现与触发。
   ======================================================================== */

const state = {
  user: null,
  session: null,
  prevCharacter: null,
};

const SAVE_SLOTS = ["slot_1", "slot_2", "slot_3", "slot_4", "slot_5"];

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
  state.session = null;
  state.prevCharacter = null;
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
  state.prevCharacter = null;
  modal.close();
  renderSession(null);
  showView("home");
  notify("已返回首页。");
});

document.querySelector("#restartButton").addEventListener("click", () => {
  state.session = null;
  state.prevCharacter = null;
  showView("character");
});

document.querySelector("#saveGameButton").addEventListener("click", () => showSaveDialog());
document.querySelector("#loadGameButton").addEventListener("click", () => showLoadDialog());

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

/* ====================== 启动 ====================== */

async function init() {
  // 默认随机属性开启 → 滑杆禁用
  document
    .querySelectorAll("#attributeInputs input[type='range']")
    .forEach((input) => {
      input.setAttribute("aria-disabled", "true");
      input.disabled = true;
    });
  refreshCharacterPreview();
  await login();
  await loadModelSettings();
}

/* ====================== 网络 ====================== */

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
    notify(String(detail));
    throw new Error(String(detail));
  }
  return response.json();
}

async function loadModelSettings() {
  return api("/api/settings/model");
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
  if (!prompt || !prompt.active) return;

  const banner = document.createElement("aside");
  banner.className = "fallback-banner";
  banner.setAttribute("role", "status");
  banner.innerHTML = `
    <span class="fallback-banner__dot" aria-hidden="true"></span>
    <span class="fallback-banner__text">${escapeHtml(prompt.text || "模型暂不可用，当前以本地故事兜底继续。")}</span>
    <span class="fallback-banner__actions">
      <button class="command-button ghost" id="fallbackContinueButton" type="button">继续本局</button>
      <button class="command-button danger" id="fallbackEndButton" type="button">结束本局</button>
    </span>
  `;
  panel.insertBefore(banner, panel.firstChild.nextSibling); // after toolbar

  banner.querySelector("#fallbackContinueButton").addEventListener("click", () => {
    notify("继续当前本地故事。");
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
  const container = document.querySelector("#choices");
  if (!container) return;
  container.innerHTML = choices
    .map((choice, index) => {
      const label = String.fromCharCode(65 + index);
      return `<button class="choice" type="button" data-choice-index="${index}" aria-label="${escapeAttr("选项 " + label + "：" + choice)}">
        <span class="choice-key" aria-hidden="true">${label}</span>
        <span class="choice-text">${escapeHtml(choice)}</span>
      </button>`;
    })
    .join("");
  container.querySelectorAll("[data-choice-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.session) return;
      button.classList.add("is-busy");
      try {
        await runTurn(
          `/api/sessions/${state.session.session_id}/choice`,
          { choice_index: Number(button.dataset.choiceIndex) }
        );
      } finally {
        button.classList.remove("is-busy");
      }
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

async function showSettings() {
  const settings = await loadModelSettings();
  openModal(
    "设置",
    `<form id="settingsForm">
      <label><span>服务商</span><input name="provider" value="${escapeAttr(settings.provider || "Agens")}" /></label>
      <label><span>Base URL</span><input name="base_url" value="${escapeAttr(settings.base_url || "")}" /></label>
      <label><span>模型</span><input name="model" value="${escapeAttr(settings.model || "")}" /></label>
      <label>
        <span>API Key</span>
        <input name="api_key" type="password" autocomplete="off" placeholder="${escapeAttr(settings.api_key_masked || "<unset>")}" />
        <span class="field-hint">当前 Key 状态：${settings.api_key_set ? "已配置" : "未配置"}，前端不会显示明文。</span>
      </label>
      <p class="muted-line">
        当前仅开放引导模式：A / B / C 由模型生成，D 为自由输入；
        <span aria-disabled="true">小说模式</span> 与
        <span aria-disabled="true">游戏模式</span> 暂不开放。
      </p>
      <button id="settingsSubmit" class="command-button primary wide" type="submit">
        <span class="spinner" aria-hidden="true"></span>
        <span class="label">保存设置</span>
      </button>
    </form>`
  );
  document.querySelector("#settingsForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.querySelector("#settingsSubmit");
    submit.classList.add("is-busy");
    try {
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
      notify(`设置已保存：${saved.provider} / ${saved.model}`);
      modal.close();
    } finally {
      submit.classList.remove("is-busy");
    }
  });
}

async function showSaveDialog() {
  if (!state.session) return notify("尚未创建会话。");
  const slotsHtml = SAVE_SLOTS.map(
    (slot, idx) => `<button class="save-slot ${idx === 0 ? "is-active" : ""}" type="button" data-slot="${escapeAttr(slot)}">
      <strong>${escapeHtml(slot.replace("_", " "))}</strong>
      <span>档位 ${idx + 1}</span>
    </button>`
  ).join("");

  openModal(
    "存档",
    `<form id="saveForm">
      <fieldset class="form-section">
        <legend>选择档位</legend>
        <div class="save-slots" role="radiogroup" aria-label="存档档位">${slotsHtml}</div>
        <label>
          <span>备注（可选）</span>
          <input name="note" type="text" autocomplete="off" placeholder="例如：第三回合前" />
          <span class="field-hint">备注仅在本机显示，不写入档名。</span>
        </label>
      </fieldset>
      <button id="saveSubmit" class="command-button primary wide" type="submit">
        <span class="spinner" aria-hidden="true"></span>
        <span class="label">保存</span>
      </button>
    </form>`
  );

  let selectedSlot = SAVE_SLOTS[0];
  document.querySelectorAll("[data-slot]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedSlot = button.dataset.slot;
      document.querySelectorAll("[data-slot]").forEach((b) =>
        b.classList.toggle("is-active", b === button)
      );
    });
  });

  document.querySelector("#saveForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.querySelector("#saveSubmit");
    submit.classList.add("is-busy");
    try {
      const note = text(new FormData(event.currentTarget).get("note"));
      const result = await api(`/api/sessions/${state.session.session_id}/save`, {
        method: "POST",
        body: { name: selectedSlot },
      });
      state.session = result.session;
      renderSession(state.session);
      notify(note ? `已保存：${result.save.name} · ${note}` : `已保存：${result.save.name}`);
      modal.close();
    } finally {
      submit.classList.remove("is-busy");
    }
  });
}

async function showLoadDialog() {
  await ensureSession();
  const saves = await api(`/api/saves?user_id=${encodeURIComponent(state.user?.id || "")}`);
  const body = saves.length
    ? `<div class="save-list">${saves
        .map(
          (save) =>
            `<button class="command-button save-list-row" type="button" data-load-name="${escapeAttr(save.name)}">
              <span>
                <span class="meta"><strong>${escapeHtml(save.name)}</strong> · ${escapeHtml(save.char_name || "?")} · ${escapeHtml(save.realm || "?")}</span>
                <span class="meta">回合 ${save.turn_count || 0}</span>
              </span>
              <span class="turn">${save.turn_count || 0}</span>
            </button>`
        )
        .join("")}</div>`
    : `<p class="muted-line">暂无存档。先开始一局并保存。</p>`;
  openModal("读档", body);
  document.querySelectorAll("[data-load-name]").forEach((button) => {
    button.addEventListener("click", async () => {
      const session = await api(`/api/sessions/${state.session.session_id}/load`, {
        method: "POST",
        body: { name: button.dataset.loadName },
      });
      state.session = session;
      state.prevCharacter = null;
      renderSession(session);
      modal.close();
      showView("game");
    });
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
