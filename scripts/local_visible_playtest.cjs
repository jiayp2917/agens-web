#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "output", "playwright");
const BASE_URL = process.env.AGENS_PLAYTEST_URL || "http://127.0.0.1:5173/static/";
const API_BASE_URL = process.env.AGENS_PLAYTEST_API_BASE || "";
const TARGET_TURNS = Number(process.env.AGENS_PLAYTEST_TURNS || "20");
const REQUEST_TIMEOUT_MS = Number(process.env.AGENS_PLAYTEST_TIMEOUT_MS || "300000");
const STAMP = process.env.AGENS_PLAYTEST_NAME || `local-visible-20turn-${stamp()}`;
const CONTENT_AUDIT = process.env.AGENS_PLAYTEST_CONTENT_AUDIT === "1";
const CONTENT_AUDIT_FAIL_ON_P1 = CONTENT_AUDIT && process.env.AGENS_PLAYTEST_FAIL_ON_P1 !== "0";
const CHOICE_STRATEGY = (process.env.AGENS_PLAYTEST_CHOICE_STRATEGY || "cycle").toLowerCase();
const POST_LOAD_TURNS = Number(process.env.AGENS_PLAYTEST_POST_LOAD_TURNS || (CONTENT_AUDIT ? "3" : "0"));
const REFRESH_PROBE = process.env.AGENS_PLAYTEST_REFRESH_PROBE === "1";
const DOUBLE_CLICK_PROBE = process.env.AGENS_PLAYTEST_DOUBLE_CLICK_PROBE === "1";

const FORBIDDEN_VISIBLE_PATTERNS = [
  ["history_suppression_notice", /此事未入正史/u],
  ["choice_completion_notice", /补齐下一步选择/u],
  ["internal_delta_notice", /模型状态变更未采用/u],
  ["fallback_word", /\bfallback\b/iu],
  ["mismatch_word", /\bmismatch\b/iu],
  ["state_update_tag", /<\/?state_update\b|<state_update>/iu],
  ["choices_tag", /<\/?choices\b|<choices>/iu],
  ["json_fence", /```(?:json)?/iu],
  ["json_like_object", /(?:^|[\s：:])\{[^{}]*(?:state_delta|state_update|character|world|meta|choices)[^{}]*\}/iu],
  ["json_like_array", /(?:^|[\s：:])\[(?=[^\]]*(?:"|'))[^\]]+\]/u],
  ["english_status_word", /\b(?:prowess|inventory|lifespan|realm|delta|narrative|turn_count|game_turns)\b/iu],
];

const ROUTE_HINTS = {
  a: "稳妥",
  b: "机遇",
  c: "风险",
  d: "气运",
};

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    // Continue with explicit path lookup.
  }

  const candidates = [];
  if (process.env.AGENS_PLAYWRIGHT_NODE_MODULES) {
    candidates.push(process.env.AGENS_PLAYWRIGHT_NODE_MODULES);
  }
  for (const entry of String(process.env.PATH || "").split(path.delimiter)) {
    if (entry.endsWith(`${path.sep}node_modules${path.sep}.bin`)) {
      candidates.push(path.dirname(entry));
    }
  }
  for (const root of [
    path.join(process.env.LOCALAPPDATA || "", "npm-cache", "_npx"),
    path.join(process.env.APPDATA || "", "npm-cache", "_npx"),
    path.join(process.env.USERPROFILE || "", "AppData", "Local", "npm-cache", "_npx"),
    path.join("D:", "UserData", "dev-cache", "npm", "_npx"),
  ]) {
    if (!root || !fs.existsSync(root)) continue;
    for (const item of fs.readdirSync(root)) {
      candidates.push(path.join(root, item, "node_modules"));
    }
  }

  for (const nodeModules of candidates) {
    try {
      const resolved = require.resolve("playwright", { paths: [nodeModules] });
      return require(resolved);
    } catch {
      // Try next candidate.
    }
  }
  throw new Error(
    "Cannot resolve Playwright. Run `npx playwright --version` once, or set AGENS_PLAYWRIGHT_NODE_MODULES to a node_modules directory containing playwright.",
  );
}

function pythonExe() {
  const local = path.join(ROOT, ".venv", "Scripts", "python.exe");
  return fs.existsSync(local) ? local : "python";
}

function ensureInvite(inviteCode) {
  const py = `
import os
from web.backend.auth import hash_invite_code
from web.backend.database import create_database

code = os.environ["AGENS_PLAYTEST_INVITE_CODE"]
db = create_database()
try:
    db.create_invite_code(hash_invite_code(code), max_uses=1)
except Exception:
    # The validation account uses a fresh invite code. If a collision somehow
    # occurs, registration will fail visibly and the browser evidence will show it.
    pass
print("ok")
`;
  const result = spawnSync(pythonExe(), ["-c", py], {
    cwd: ROOT,
    env: {
      ...process.env,
      AGENS_PLAYTEST_INVITE_CODE: inviteCode,
    },
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`Failed to seed local invite: ${(result.stderr || result.stdout || "").trim()}`);
  }
}

function writeStrictEvidence(rawPath, name) {
  const result = spawnSync(
    pythonExe(),
    ["scripts/playwright_evidence.py", "--input", rawPath, "--output-dir", "output/playwright", "--name", name],
    { cwd: ROOT, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(`Failed to write strict evidence: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return JSON.parse(result.stdout);
}

function chromeExecutablePath() {
  const explicit = process.env.AGENS_CHROME_PATH;
  const candidates = [
    explicit,
    path.join(process.env.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(process.env.PROGRAMFILES || "", "Microsoft", "Edge", "Application", "msedge.exe"),
    path.join(process.env["PROGRAMFILES(X86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe"),
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeForCompare(value) {
  return cleanText(value)
    .replace(/[，。、“”‘’；：:,.!?！？\s]/gu, "")
    .replace(/[一二三四五六七八九十百千万零〇\d]+岁/gu, "X岁")
    .replace(/\d+/g, "N");
}

function textSimilarity(left, right) {
  const a = normalizeForCompare(left);
  const b = normalizeForCompare(right);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const grams = (text) => {
    const set = new Set();
    for (let index = 0; index < text.length - 1; index += 1) {
      set.add(text.slice(index, index + 2));
    }
    return set.size ? set : new Set([text]);
  };
  const leftSet = grams(a);
  const rightSet = grams(b);
  let overlap = 0;
  for (const gram of leftSet) {
    if (rightSet.has(gram)) overlap += 1;
  }
  return overlap / Math.max(1, Math.min(leftSet.size, rightSet.size));
}

function forbiddenHits(text) {
  const body = String(text || "");
  if (!body.trim()) return [];
  const hits = [];
  for (const [name, pattern] of FORBIDDEN_VISIBLE_PATTERNS) {
    if (pattern.test(body)) hits.push(name);
  }
  return hits;
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

function parseAge(value) {
  const text = String(value || "");
  const match = text.match(/(\d+)\s*岁/u);
  if (match) return Number(match[1]);
  const chineseMatch = text.match(/([零〇一二三四五六七八九十百]+)\s*岁/u);
  return chineseMatch ? chineseNumber(chineseMatch[1]) : 0;
}

function chineseNumber(value) {
  const digits = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
  };
  const text = String(value || "");
  if (!text) return 0;
  if (text === "十") return 10;
  const hundred = text.split("百");
  if (hundred.length === 2) {
    const left = hundred[0] ? digits[hundred[0]] || 0 : 1;
    return left * 100 + chineseNumber(hundred[1]);
  }
  const ten = text.split("十");
  if (ten.length === 2) {
    const left = ten[0] ? digits[ten[0]] || 0 : 1;
    const right = ten[1] ? digits[ten[1]] || 0 : 0;
    return left * 10 + right;
  }
  return Array.from(text).reduce((total, char) => total * 10 + (digits[char] || 0), 0);
}

function canBreakthroughFromRealmText(realmText) {
  const text = String(realmText || "");
  if (/[练炼]气\s*(?:第)?(?:9|九)\s*层/u.test(text)) return true;
  return /圆满/u.test(text);
}

function hasBreakthroughIntent(text) {
  const body = String(text || "");
  if (/所需|准备|底蕴|线索|打听|寻找|静候|机缘/u.test(body) && !/尝试|正式|强行|开始/u.test(body)) {
    return false;
  }
  return /突破|破境|冲关|冲击|渡劫|飞升/u.test(body);
}

function routeIndexForTurn(turn, choices, snapshot) {
  const enabled = choices.filter((choice) => !choice.disabled);
  const fallback = enabled[(turn - 1) % Math.max(1, enabled.length)];
  const normalized = CHOICE_STRATEGY.replace(/[^a-z0-9_-]/g, "");
  const fixedMatch = normalized.match(/^fixed-?([abcd])$/);
  if (fixedMatch) {
    const wanted = fixedMatch[1].toUpperCase();
    return enabled.find((choice) => String(choice.letter || "").toUpperCase() === wanted) || fallback;
  }
  if (["a", "b", "c", "d"].includes(normalized)) {
    const wanted = normalized.toUpperCase();
    return enabled.find((choice) => String(choice.letter || "").toUpperCase() === wanted) || fallback;
  }
  if (normalized === "mixed" || normalized === "player") {
    return chooseMixedChoice(turn, enabled, snapshot) || fallback;
  }
  return fallback;
}

function chooseMixedChoice(turn, enabled, snapshot) {
  const realm = snapshot?.status?.realm || "";
  const lifespan = snapshot?.status?.lifespan || "";
  const lowLifespan = /(?:^|[^\d])(?:[0-9]|1[0-5])\/\d+/.test(lifespan);
  const canBreakthrough = canBreakthroughFromRealmText(realm);
  const breakthrough = canBreakthrough
    ? enabled.find((choice) => hasBreakthroughIntent(choice.text))
    : null;
  if (breakthrough && turn % 4 === 0) return breakthrough;
  if (lowLifespan) {
    return enabled.find((choice) => ["A", "B"].includes(String(choice.letter || "").toUpperCase())) || enabled[0];
  }
  const order = ["B", "A", "D", "C", "B", "A", "C", "D"];
  const wanted = order[(turn - 1) % order.length];
  return enabled.find((choice) => String(choice.letter || "").toUpperCase() === wanted) || enabled[0];
}

async function choiceSnapshots(page) {
  return page.locator(".choice-button").evaluateAll((buttons) =>
    buttons.map((button, index) => {
      const aria = button.getAttribute("aria-label") || "";
      const mark = button.querySelector(".choice-mark")?.textContent || String.fromCharCode(65 + index);
      const em = button.querySelector("em")?.textContent || "";
      const copy = button.querySelector(".choice-copy")?.textContent || "";
      const inner = button.textContent || "";
      const sources = [em, copy, aria, inner]
        .map((text) => String(text || "").replace(/\s+/g, " ").trim())
        .filter(Boolean);
      let text = sources[0] || "";
      if (aria && (!text || aria.length > text.length)) {
        text = aria;
      }
      const letter = String(mark || String.fromCharCode(65 + index)).trim().slice(0, 1);
      text = text
        .replace(new RegExp(`^${letter}\\s*[.:：、)）-]?\\s*`), "")
        .replace(/^[A-Da-d1-4]\s*[.:：、)）-]?\s*/, "")
        .trim();
      return {
        index,
        letter,
        text,
        aria,
        disabled: Boolean(button.disabled),
      };
    }),
  );
}

async function uiSnapshot(page, label) {
  const snapshot = await page.evaluate((snapshotLabel) => {
    const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const textOf = (selector) => clean(document.querySelector(selector)?.textContent || "");
    const railStats = Array.from(document.querySelectorAll(".rail-stats span")).map((item) => clean(item.textContent || ""));
    const statValue = (labelText) => {
      const row = railStats.find((item) => item.startsWith(labelText));
      return row ? clean(row.replace(labelText, "")) : "";
    };
    const chronicle = Array.from(document.querySelectorAll(".chronicle-item")).map((item, index) => ({
      index,
      age: clean(item.querySelector(".chronicle-age")?.textContent || ""),
      text: clean(item.querySelector("p")?.textContent || item.textContent || ""),
      latest: item.classList.contains("latest"),
    }));
    const choices = Array.from(document.querySelectorAll(".choice-button")).map((button, index) => ({
      index,
      letter: clean(button.querySelector(".choice-mark")?.textContent || String.fromCharCode(65 + index)).slice(0, 1),
      text: clean(button.querySelector(".choice-copy")?.textContent || button.textContent || ""),
      aria: clean(button.getAttribute("aria-label") || ""),
      disabled: Boolean(button.disabled),
    }));
    return {
      label: snapshotLabel,
      captured_at: new Date().toISOString(),
      status: {
        name: textOf(".status-panel h2"),
        age: statValue("年龄"),
        realm: statValue("境界"),
        lifespan: textOf(".lifespan-bar strong"),
        talent: textOf(".character-meta dd:nth-of-type(1)"),
        spirit_root: textOf(".character-meta dd:nth-of-type(2)"),
        family_background: textOf(".character-meta dd:nth-of-type(3)"),
        luck: textOf(".character-meta dd:nth-of-type(4)"),
      },
      heading: textOf(".chronicle-heading > span"),
      world_intel: Array.from(document.querySelectorAll(".world-intel li")).map((item) => clean(item.textContent || "")),
      chronicle,
      latest_chronicle: chronicle.filter((item) => item.latest),
      choices,
      fallback_banner: textOf(".fallback"),
      body_issue_text: [
        ...chronicle.map((item) => item.text),
        ...Array.from(document.querySelectorAll(".world-intel li")).map((item) => clean(item.textContent || "")),
        ...choices.map((item) => item.text),
        textOf(".fallback"),
      ].filter(Boolean).join("\n"),
    };
  }, label);
  snapshot.forbidden_hits = unique(forbiddenHits(snapshot.body_issue_text));
  snapshot.latest_age_value = parseAge(snapshot.latest_chronicle.at(-1)?.age || "");
  snapshot.status_age_value = parseAge(snapshot.status?.age || "");
  return snapshot;
}

async function firstVisible(page, selectors, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    for (const selector of selectors) {
      const locator = page.locator(selector).first();
      try {
        if ((await locator.count()) > 0 && (await locator.isVisible())) {
          return locator;
        }
      } catch (error) {
        lastError = error;
      }
    }
    await page.waitForTimeout(250);
  }
  throw lastError || new Error(`No visible selector matched: ${selectors.join(", ")}`);
}

async function clickFirstVisible(page, selectors, timeout) {
  const locator = await firstVisible(page, selectors, timeout);
  await locator.click();
}

function redactedUrl(url) {
  return String(url || "").replace(/sessions\/[^/]+/g, "sessions/<id>");
}

async function routeApiBase(page) {
  if (!API_BASE_URL) return;
  const apiBase = API_BASE_URL.replace(/\/+$/, "");
  await page.route("**/*", (route) => {
    const requestUrl = new URL(route.request().url());
    if (!requestUrl.pathname.startsWith("/api/")) {
      route.continue();
      return;
    }
    const redirected = `${apiBase}${requestUrl.pathname}${requestUrl.search}`;
    route.continue({ url: redirected });
  });
}

function latestModelDiagnostics(body, sinceMs = 0) {
  const events = Array.isArray(body?.events)
    ? body.events
    : Array.isArray(body?.session?.events)
      ? body.session.events
      : [];
  const modelEvents = events.filter((event) => {
    if (event?.type !== "model_result") return false;
    if (!sinceMs) return true;
    const eventMs = Number(event.at || 0) * 1000;
    return Number.isFinite(eventMs) && eventMs >= sinceMs;
  });
  const latestByAgent = {};
  for (const event of modelEvents) {
    const agent = event.agent || "";
    if (!agent) continue;
    latestByAgent[agent] = event;
  }
  const narrator = latestByAgent.narrator || {};
  const judge = latestByAgent.judge || {};
  const narratorDiag = narrator.diagnostics || {};
  const judgeDiag = judge.diagnostics || {};
  const narratorStatus = String(narrator.status || "");
  const judgeStatus = String(judge.status || "");
  return {
    narrator_status: narratorStatus,
    judge_status: judgeStatus,
    judge_request_failed: judgeStatus === "judge_failed",
    narrator_elapsed_ms: numberMetric(narratorDiag.elapsed_ms),
    judge_elapsed_ms: numberMetric(judgeDiag.elapsed_ms),
    repair_elapsed_ms: numberMetric(narratorDiag.repair_elapsed_ms),
    repaired_output: Boolean(narratorDiag.repaired_output),
    retried_after_incomplete_output: Boolean(narratorDiag.retried_after_incomplete_output),
    narrator_incomplete_output: narratorStatus === "incomplete_output",
    contract_missing_narrative: Boolean(narratorDiag.contract_missing_narrative),
    contract_missing_state_update: Boolean(narratorDiag.contract_missing_state_update),
    contract_choices_count_ok: Boolean(narratorDiag.contract_choices_count_ok),
    prompt_chars: numberMetric(narratorDiag.prompt_chars),
    game_state_chars: numberMetric(narratorDiag.game_state_chars),
    history_count: numberMetric(narratorDiag.history_count),
    prompt_tokens: numberMetric(narratorDiag.prompt_tokens),
    completion_tokens: numberMetric(narratorDiag.completion_tokens),
    total_tokens: numberMetric(narratorDiag.total_tokens),
  };
}

function startAcceptance(body, httpStatus) {
  const world = body?.world || body?.session?.world || {};
  const worldProfile = world?.world_profile || body?.world_profile || body?.session?.world_profile || {};
  const choices = Array.isArray(body?.choices)
    ? body.choices
    : Array.isArray(body?.session?.choices)
      ? body.session.choices
      : [];
  const chronicle = Array.isArray(worldProfile?.chronicle_0_16) ? worldProfile.chronicle_0_16 : [];
  const currentConflicts = Array.isArray(worldProfile?.current_conflicts) ? worldProfile.current_conflicts : [];
  const fateHooks = Array.isArray(worldProfile?.fate_hooks) ? worldProfile.fate_hooks : [];
  const initialSituation = worldProfile?.initial_situation_16 || worldProfile?.initial_situation || "";
  const fallback = Boolean(body?.fallback_prompt?.active || body?.session?.fallback_prompt?.active);
  const events = Array.isArray(body?.events)
    ? body.events
    : Array.isArray(body?.session?.events)
      ? body.session.events
      : [];
  const startModelOk = events.some((event) =>
    event?.type === "model_result"
    && event?.agent === "world_builder"
    && event?.source === "profile_opening"
    && event?.status === "ok",
  );
  const modelDiagnostics = latestModelDiagnostics(body);
  return {
    start_http_status: httpStatus,
    start_fallback: fallback,
    start_model_ok: startModelOk,
    start_choices_count: choices.length,
    start_world_name_set: Boolean(cleanText(worldProfile?.world_name)),
    start_world_name: cleanText(worldProfile?.world_name),
    start_chronicle_count: chronicle.length,
    start_initial_situation_set: Boolean(cleanText(initialSituation)),
    start_current_conflicts_count: currentConflicts.length,
    start_fate_hooks_count: fateHooks.length,
    start_narrator_elapsed_ms: modelDiagnostics.narrator_elapsed_ms,
    start_prompt_chars: modelDiagnostics.prompt_chars,
  };
}

function newChronicleEntries(beforeSnapshot, afterSnapshot) {
  const before = Array.isArray(beforeSnapshot?.chronicle) ? beforeSnapshot.chronicle : [];
  const after = Array.isArray(afterSnapshot?.chronicle) ? afterSnapshot.chronicle : [];
  if (after.length > before.length) {
    return after.slice(before.length);
  }
  const beforeSignatures = new Set(before.map((item) => chronicleSignature(item)));
  const added = after.filter((item) => !beforeSignatures.has(chronicleSignature(item)));
  if (added.length) return added;
  const latest = after.filter((item) => item.latest && !beforeSignatures.has(chronicleSignature(item)));
  return latest;
}

function chronicleSignature(item) {
  return [
    cleanText(item?.age || ""),
    cleanText(item?.text || ""),
  ].join("|");
}

function auditVisibleContent({
  turnRecord,
  beforeSnapshot,
  afterSnapshot,
  auditState,
  issue,
}) {
  if (!CONTENT_AUDIT || !afterSnapshot) return;
  const forbidden = unique([
    ...(beforeSnapshot?.forbidden_hits || []),
    ...(afterSnapshot?.forbidden_hits || []),
  ]);
  turnRecord.forbidden_hits = forbidden;
  turnRecord.forbidden_count = forbidden.length;
  const terminalTurn = Boolean(turnRecord.game_over || turnRecord.finale);
  if (forbidden.length) {
    issue("P1", "player-visible forbidden/internal text appeared", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      hits: forbidden,
      latest_text: afterSnapshot.latest_chronicle?.at(-1)?.text || "",
      fallback_banner_set: Boolean(afterSnapshot.fallback_banner),
    });
  }

  const newEntries = newChronicleEntries(beforeSnapshot, afterSnapshot)
    .map((entry) => ({ ...entry, text: cleanText(entry.text) }))
    .filter((entry) => entry.text);
  turnRecord.new_chronicle_count = newEntries.length;
  turnRecord.latest_chronicle_text = newEntries.at(-1)?.text || afterSnapshot.latest_chronicle?.at(-1)?.text || "";
  if (!newEntries.length && !turnRecord.fallback && !terminalTurn) {
    issue("P1", "non-fallback turn produced no new visible chronicle entry", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      status_age: afterSnapshot.status?.age || "",
      latest_age: afterSnapshot.latest_chronicle?.at(-1)?.age || "",
    });
  }
  turnRecord.status_age = afterSnapshot.status?.age || "";
  turnRecord.status_realm = afterSnapshot.status?.realm || "";
  turnRecord.status_lifespan = afterSnapshot.status?.lifespan || "";
  turnRecord.world_intel = afterSnapshot.world_intel || [];
  turnRecord.choice_texts_after = (afterSnapshot.choices || []).map((choice) => cleanText(choice.text));

  for (const entry of newEntries) {
    const normalized = normalizeForCompare(entry.text);
    if (normalized.length >= 16) {
      const seen = auditState.seenChronicle.get(normalized) || 0;
      if (seen >= 1) {
        turnRecord.repeated_exact = true;
        issue("P1", "chronicle text repeated exactly", {
          turn_index: turnRecord.turn_index,
          phase: turnRecord.phase || "main",
          text: entry.text,
          previous_count: seen,
        });
      }
      auditState.seenChronicle.set(normalized, seen + 1);
    }
    if (auditState.lastChronicleText) {
      const similarity = textSimilarity(entry.text, auditState.lastChronicleText);
      turnRecord.max_previous_similarity = Math.max(turnRecord.max_previous_similarity || 0, Number(similarity.toFixed(3)));
      if (similarity >= 0.86 && normalizeForCompare(entry.text).length >= 20) {
        issue("P1", "chronicle text is highly similar to previous turn", {
          turn_index: turnRecord.turn_index,
          phase: turnRecord.phase || "main",
          similarity: Number(similarity.toFixed(3)),
          text: entry.text,
          previous_text: auditState.lastChronicleText,
        });
      }
    }
    auditState.lastChronicleText = entry.text;
  }

  const intelKey = JSON.stringify(afterSnapshot.world_intel || []);
  if (intelKey && intelKey !== auditState.lastWorldIntelKey) {
    auditState.lastWorldIntelKey = intelKey;
    auditState.lastWorldIntelChangeTurn = turnRecord.turn_index;
    auditState.worldIntelChangeCount += 1;
    turnRecord.world_intel_changed = true;
  } else {
    turnRecord.world_intel_changed = false;
  }
  if (!terminalTurn && turnRecord.turn_index - auditState.lastWorldIntelChangeTurn > 5) {
    issue("P1", "world intel did not change within 5 turns", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      last_change_turn: auditState.lastWorldIntelChangeTurn,
    });
    auditState.lastWorldIntelChangeTurn = turnRecord.turn_index;
  }

  const latestAge = Number(afterSnapshot.latest_age_value || 0);
  const statusAge = Number(afterSnapshot.status_age_value || 0);
  turnRecord.latest_chronicle_age = latestAge || "";
  if (!terminalTurn && latestAge && statusAge && latestAge < statusAge - 3) {
    issue("P1", "visible timeline latest age lags behind status age", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      status_age: statusAge,
      latest_chronicle_age: latestAge,
    });
  }

  const canBreakthrough = canBreakthroughFromRealmText(afterSnapshot.status?.realm || "");
  const invalidBreakthroughChoices = (afterSnapshot.choices || [])
    .filter((choice) => !choice.disabled && hasBreakthroughIntent(choice.text) && !canBreakthrough)
    .map((choice) => `${choice.letter}:${choice.text}`);
  turnRecord.invalid_breakthrough_choices = invalidBreakthroughChoices;
  if (!terminalTurn && invalidBreakthroughChoices.length) {
    issue("P1", "breakthrough-looking choices shown while realm is not eligible", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      realm: afterSnapshot.status?.realm || "",
      choices: invalidBreakthroughChoices,
    });
  }

  const emptyChoices = (afterSnapshot.choices || []).filter((choice) => !choice.disabled && !cleanText(choice.text));
  if (!terminalTurn && ((afterSnapshot.choices || []).length !== 4 || emptyChoices.length)) {
    issue("P0", "visible choices are not exactly four non-empty buttons", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      choices_count: (afterSnapshot.choices || []).length,
      empty_choices: emptyChoices,
    });
  }
}

function numberMetric(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

function updateSummaryFromTurns(summary, turns, auditState) {
  summary.turns_completed = turns.length;
  summary.accepted_live_turns = turns.filter((turn) => turn.http_status >= 200 && turn.http_status < 300 && !turn.fallback).length;
  summary.fallback_count = turns.filter((turn) => turn.fallback).length;
  summary.max_elapsed_ms = Math.max(0, ...turns.map((turn) => turn.elapsed_ms || 0));
  summary.avg_elapsed_ms = turns.length
    ? Math.round(turns.reduce((total, turn) => total + (turn.elapsed_ms || 0), 0) / turns.length)
    : 0;
  summary.repair_attempt_count = turns.filter((turn) => (turn.repair_elapsed_ms || 0) > 0).length;
  summary.repaired_output_count = turns.filter((turn) => turn.repaired_output).length;
  summary.incomplete_retry_count = turns.filter((turn) => turn.retried_after_incomplete_output).length;
  summary.narrator_incomplete_output_count = turns.filter((turn) => turn.narrator_incomplete_output).length;
  summary.contract_missing_narrative_count = turns.filter((turn) => turn.contract_missing_narrative).length;
  summary.contract_missing_state_update_count = turns.filter((turn) => turn.contract_missing_state_update).length;
  summary.contract_bad_choices_count = turns.filter((turn) => turn.contract_choices_count_ok === false).length;
  summary.judge_count = turns.filter((turn) => (turn.judge_elapsed_ms || 0) > 0).length;
  summary.avg_narrator_elapsed_ms = avgMetric(turns, "narrator_elapsed_ms");
  summary.avg_judge_elapsed_ms = avgMetric(turns, "judge_elapsed_ms");
  summary.avg_repair_elapsed_ms = avgMetric(turns, "repair_elapsed_ms");
  summary.avg_prompt_chars = avgMetric(turns, "prompt_chars");
  summary.max_prompt_chars = Math.max(0, ...turns.map((turn) => turn.prompt_chars || 0));
  summary.max_history_count = Math.max(0, ...turns.map((turn) => turn.history_count || 0));
  summary.last_turn_count = turns.length ? turns[turns.length - 1].turn_count : 0;
  summary.visible_forbidden_turns = turns.filter((turn) => Number(turn.forbidden_count || 0) > 0).length;
  summary.repeated_exact_turns = turns.filter((turn) => turn.repeated_exact).length;
  summary.max_previous_similarity = Math.max(0, ...turns.map((turn) => Number(turn.max_previous_similarity || 0)));
  summary.judge_failed_count = turns.filter((turn) => turn.judge_request_failed).length;
  summary.world_intel_change_count = auditState?.worldIntelChangeCount || 0;
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const inviteCode = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const username = `chrome_${Date.now()}`;
  const password = `pw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const rawPath = path.join(OUT_DIR, `${STAMP}-source.json`);
  const screenshotBase = path.join(OUT_DIR, STAMP);
  const summary = {
    scenario: CONTENT_AUDIT ? "local visible Chrome content-audit playtest" : "local visible Chrome 20-turn playtest",
    target_turns: TARGET_TURNS,
    content_audit: CONTENT_AUDIT,
    content_audit_fail_on_p1: CONTENT_AUDIT_FAIL_ON_P1,
    choice_strategy: CHOICE_STRATEGY,
    post_load_turns: POST_LOAD_TURNS,
    refresh_probe: REFRESH_PROBE,
    double_click_probe: DOUBLE_CLICK_PROBE,
    base_url: BASE_URL,
    started_at: new Date().toISOString(),
    username_set: true,
    invite_seeded: false,
    registration_passed: false,
    start_passed: false,
    save_load_passed: false,
    request_timeout_ms: REQUEST_TIMEOUT_MS,
    result: "running",
  };
  const turns = [];
  const issues = [];
  const requests = [];
  const consoleMessages = [];
  const auditState = {
    seenChronicle: new Map(),
    lastChronicleText: "",
    lastWorldIntelKey: "",
    lastWorldIntelChangeTurn: 0,
    worldIntelChangeCount: 0,
  };

  function issue(level, text, data = {}) {
    const record = { ...(data || {}) };
    if (Object.prototype.hasOwnProperty.call(record, "text")) {
      record.visible_text = record.text;
      delete record.text;
    }
    delete record.level;
    issues.push({ ...record, level, text });
  }

  function auditModelDiagnostics(turnRecord, phase) {
    if (turnRecord.judge_request_failed) {
      issue("P1", "judge model request failed; rule-only settlement used", {
        turn_index: turnRecord.turn_index,
        phase,
        judge_status: turnRecord.judge_status,
      });
    }
  }

  function persistSource() {
    fs.writeFileSync(
      rawPath,
      JSON.stringify({ summary: { ...summary, issues, requests, console: consoleMessages }, turns }, null, 2) + "\n",
      "utf8",
    );
  }

  let browser;
  try {
    ensureInvite(inviteCode);
    summary.invite_seeded = true;

    const { chromium } = loadPlaywright();
    const executablePath = chromeExecutablePath();
    if (!executablePath) {
      throw new Error("No local Chrome/Edge executable found. Set AGENS_CHROME_PATH to a visible browser executable.");
    }
    summary.browser_executable = path.basename(executablePath);
    browser = await chromium.launch({
      headless: false,
      executablePath,
      args: ["--window-size=1440,1000"],
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await routeApiBase(page);

    page.on("console", (msg) => {
      consoleMessages.push({ type: msg.type(), text: msg.text().slice(0, 500) });
    });
    page.on("response", async (response) => {
      if (!response.url().includes("/api/")) return;
      const rec = {
        url: redactedUrl(response.url()),
        status: response.status(),
        method: response.request().method(),
        ts: new Date().toISOString(),
      };
      requests.push(rec);
    });

    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.screenshot({ path: `${screenshotBase}-home.png`, fullPage: true });

    await clickFirstVisible(page, [".home-actions button:nth-child(5)", "text=邀请码注册", "text=注册"], 30000);
    await page.locator('input[name="username"]').fill(username);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('input[name="invite_code"]').fill(inviteCode);
    await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/api/auth/register") && resp.request().method() === "POST", {
        timeout: 30000,
      }),
      page.locator(".auth-panel button[type='submit']").click(),
    ]);
    await page.waitForSelector(".user-chip", { timeout: 30000 });
    summary.registration_passed = true;

    await clickFirstVisible(page, [".home-actions button:nth-child(1)", "text=新游戏"], 30000);
    await page.waitForSelector('input[name="char_name"]', { timeout: 30000 });
    await page.locator('input[name="char_name"]').fill("验真者");
    const [startResponse] = await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/start"), {
        timeout: REQUEST_TIMEOUT_MS,
      }),
      page.locator(".start-btn").click(),
    ]);
    let startBody = null;
    try {
      startBody = await startResponse.json();
    } catch {
      // Keep null; status will still be recorded.
    }
    Object.assign(summary, startAcceptance(startBody, startResponse.status()));
    await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
    const startUiSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, "start") : null;
    if (CONTENT_AUDIT && startUiSnapshot?.forbidden_hits?.length) {
      issue("P1", "player-visible forbidden/internal text appeared at start", {
        hits: startUiSnapshot.forbidden_hits,
        latest_text: startUiSnapshot.latest_chronicle?.at(-1)?.text || "",
        fallback_banner_set: Boolean(startUiSnapshot.fallback_banner),
      });
    }
    summary.start_ui_snapshot = startUiSnapshot;
    await page.screenshot({ path: `${screenshotBase}-start.png`, fullPage: true });
    summary.start_passed = true;

    if (
      !startResponse.ok()
      || summary.start_fallback
      || !summary.start_model_ok
      || summary.start_choices_count !== 4
      || !summary.start_world_name_set
      || summary.start_chronicle_count < 1
      || !summary.start_initial_situation_set
    ) {
      issue("P0", "start did not satisfy dynamic live-model opening acceptance", {
        http_status: summary.start_http_status,
        fallback: summary.start_fallback,
        model_ok: summary.start_model_ok,
        choices_count: summary.start_choices_count,
        world_name_set: summary.start_world_name_set,
        chronicle_count: summary.start_chronicle_count,
        initial_situation_set: summary.start_initial_situation_set,
      });
      summary.result = "failed_or_partial";
      await page.screenshot({ path: `${screenshotBase}-start-rejected.png`, fullPage: true });
    }

    let firstMainTurn = 1;
    if (summary.result === "running" && DOUBLE_CLICK_PROBE) {
      const phase = "double_click";
      const beforeSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `${phase}-turn-1-before`) : null;
      const beforeChoices = await choiceSnapshots(page);
      const selected = routeIndexForTurn(1, beforeChoices, beforeSnapshot);
      if (!selected || !cleanText(selected.text)) {
        issue("P0", "empty choice label before double-click probe", {
          turn_index: 1,
          phase,
          choices: beforeChoices,
          ui_snapshot: beforeSnapshot,
        });
        summary.result = "failed_script_empty_choice";
      } else {
        const requestStartIndex = requests.length;
        const started = Date.now();
        const responsePromise = page.waitForResponse(
          (resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/choice"),
          { timeout: REQUEST_TIMEOUT_MS },
        );
        await page.locator(".choice-button").nth(selected.index).dblclick({ delay: 20 });
        let response;
        try {
          response = await responsePromise;
        } catch (error) {
          response = null;
        }
        await page.waitForTimeout(1500);
        const choiceResponseCount = requests
          .slice(requestStartIndex)
          .filter((request) => request.url.includes("/choice")).length;
        let body = null;
        if (response) {
          try {
            body = await response.json();
          } catch {
            // Keep null; status will still be recorded.
          }
        }
        const elapsed = Date.now() - started;
        const fallback = Boolean(body?.fallback_prompt?.active || body?.session?.fallback_prompt?.active);
        const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
        const afterChoices = Array.isArray(body?.choices)
          ? body.choices
          : Array.isArray(body?.session?.choices)
            ? body.session.choices
            : [];
        await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
        const afterSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `${phase}-turn-1-after`) : null;
        const turnRecord = {
          phase,
          turn_index: 1,
          selected_index: selected.index,
          choice: cleanText(selected.text),
          choice_letter: selected.letter,
          http_status: response ? response.status() : "",
          fallback,
          turn_count: turnCount,
          elapsed_ms: elapsed,
          choices_count: afterChoices.length,
          choice_response_count: choiceResponseCount,
          ...latestModelDiagnostics(body, started),
          note: response ? (fallback ? "fallback" : "non-fallback") : "choice_response_timeout",
          ui_before: beforeSnapshot,
          ui_after: afterSnapshot,
        };
        auditVisibleContent({ turnRecord, beforeSnapshot, afterSnapshot, auditState, issue });
        auditModelDiagnostics(turnRecord, phase);
        turns.push(turnRecord);
        summary.double_click_probe_passed = Boolean(response?.ok() && !fallback && turnCount === 1 && choiceResponseCount === 1);
        if (!summary.double_click_probe_passed) {
          issue(response ? "P1" : "P0", "double-click probe did not prove single-submit behavior", {
            turn_index: 1,
            phase,
            http_status: response ? response.status() : "",
            fallback,
            turn_count: turnCount,
            choice_response_count: choiceResponseCount,
          });
          if (!response || fallback || turnCount < 1) {
            summary.result = "failed_or_partial";
          }
        }
        firstMainTurn = Math.max(2, turnCount + 1);
      }
    }

    for (let turn = firstMainTurn; summary.result === "running" && turn <= TARGET_TURNS; turn += 1) {
      const beforeSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `turn-${turn}-before`) : null;
      const beforeChoices = await choiceSnapshots(page);
      const enabled = beforeChoices.filter((choice) => !choice.disabled);
      const selected = routeIndexForTurn(turn, beforeChoices, beforeSnapshot);
      if (!selected || !cleanText(selected.text)) {
        issue("P0", "empty choice label before click; stopped without sending choice", {
          turn_index: turn,
          choices: beforeChoices,
          ui_snapshot: beforeSnapshot,
        });
        summary.result = "failed_script_empty_choice";
        await page.screenshot({ path: `${screenshotBase}-empty-choice-turn${turn}.png`, fullPage: true });
        break;
      }

      const started = Date.now();
      const responsePromise = page.waitForResponse(
        (resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/choice"),
        { timeout: REQUEST_TIMEOUT_MS },
      );
      await page.locator(".choice-button").nth(selected.index).click();
      let response;
      try {
        response = await responsePromise;
      } catch (error) {
        const elapsed = Date.now() - started;
        turns.push({
          phase: "main",
          turn_index: turn,
          selected_index: selected.index,
          choice: cleanText(selected.text),
          choice_letter: selected.letter,
          http_status: "",
          fallback: "",
          turn_count: "",
          elapsed_ms: elapsed,
          choices_count: beforeChoices.length,
          note: "choice_response_timeout",
          ui_before: beforeSnapshot,
        });
        issue("P0", "choice response timed out before acceptance could be evaluated", {
          turn_index: turn,
          timeout_ms: REQUEST_TIMEOUT_MS,
          elapsed_ms: elapsed,
          selected_index: selected.index,
        });
        summary.result = "failed_timeout";
        await page.screenshot({ path: `${screenshotBase}-timeout-turn${turn}.png`, fullPage: true });
        break;
      }
      let body = null;
      try {
        body = await response.json();
      } catch {
        // Keep null; status will still be recorded.
      }
      const elapsed = Date.now() - started;
      const fallback = Boolean(body?.fallback_prompt?.active || body?.session?.fallback_prompt?.active);
      const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
      const afterChoices = Array.isArray(body?.choices)
        ? body.choices
        : Array.isArray(body?.session?.choices)
          ? body.session.choices
          : [];
      const gameOver = Boolean(body?.game_over ?? body?.session?.game_over);
      const finale = Boolean(body?.finale ?? body?.session?.finale);
      const diagnostics = latestModelDiagnostics(body, started);
      if (!gameOver) {
        await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
      } else {
        await page.waitForTimeout(500);
      }
      const afterSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `turn-${turn}-after`) : null;
      const turnRecord = {
        phase: "main",
        turn_index: turn,
        selected_index: selected.index,
        choice: cleanText(selected.text),
        choice_letter: selected.letter,
        http_status: response.status(),
        fallback,
        game_over: gameOver,
        finale,
        turn_count: turnCount,
        elapsed_ms: elapsed,
        choices_count: afterChoices.length,
        ...diagnostics,
        note: response.ok() ? (fallback ? "fallback" : (gameOver ? "terminal" : "non-fallback")) : "http_failure",
        ui_before: beforeSnapshot,
        ui_after: afterSnapshot,
      };
      auditVisibleContent({
        turnRecord,
        beforeSnapshot,
        afterSnapshot,
        auditState,
        issue,
      });
      auditModelDiagnostics(turnRecord, "main");
      turns.push(turnRecord);

      const turnAdvanced = turnCount === turn;
      const hasFourChoices = afterChoices.length === 4;
      const terminalAccepted = response.ok() && !fallback && turnAdvanced && gameOver;
      if (terminalAccepted) {
        summary.ended_early_game_over = true;
        summary.ended_at_turn = turn;
        summary.ended_finale = finale;
        summary.result = "passed_terminal";
        await page.screenshot({ path: `${screenshotBase}-terminal-turn${turn}.png`, fullPage: true });
        break;
      }
      if (!response.ok() || fallback || !turnAdvanced || !hasFourChoices) {
        issue("P0", "choice did not satisfy live-model acceptance", {
          turn_index: turn,
          http_status: response.status(),
          fallback,
          game_over: gameOver,
          turn_count: turnCount,
          expected_turn_count: turn,
          turn_advanced: turnAdvanced,
          choices_count: afterChoices.length,
        });
        summary.result = "failed_or_partial";
        await page.screenshot({ path: `${screenshotBase}-stopped-turn${turn}.png`, fullPage: true });
        break;
      }
    }

    updateSummaryFromTurns(summary, turns, auditState);

    if (summary.accepted_live_turns >= TARGET_TURNS && summary.fallback_count === 0 && !issues.some((item) => item.level === "P0")) {
      await page.locator('button[aria-label*="存"]').click();
      await page.waitForSelector(".settings-dialog", { timeout: 30000 });
      await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:last-child"], 30000);
      await page.waitForTimeout(1000);
      await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:first-child"], 30000);
      await page.waitForSelector(".choice-button", { timeout: 30000 });
      await page.screenshot({ path: `${screenshotBase}-save-load.png`, fullPage: true });
      summary.save_load_passed = true;
      if (CONTENT_AUDIT) {
        summary.save_load_ui_snapshot = await uiSnapshot(page, "save-load-after");
      }
      if (REFRESH_PROBE) {
        try {
          await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
          await page.waitForSelector(".choice-button", { timeout: 10000 });
          summary.refresh_probe_passed = true;
          if (CONTENT_AUDIT) {
            summary.refresh_probe_ui_snapshot = await uiSnapshot(page, "refresh-after");
          }
        } catch (error) {
          summary.refresh_probe_passed = false;
          issue("P1", "refresh probe did not restore visible game choices", {
            error: String(error).slice(0, 500),
          });
        }
        await page.screenshot({ path: `${screenshotBase}-refresh.png`, fullPage: true });
      }
      const postLoadStartTurn = Number(summary.last_turn_count || TARGET_TURNS) + 1;
      const postLoadChoicesAvailable = (await page.locator(".choice-button").count()) > 0;
      if (POST_LOAD_TURNS > 0 && !postLoadChoicesAvailable) {
        issue("P1", "post-load continuation skipped because no visible choices were available", {
          post_load_turns: POST_LOAD_TURNS,
          refresh_probe_passed: summary.refresh_probe_passed,
        });
      }
      for (let turn = postLoadStartTurn; postLoadChoicesAvailable && summary.result === "running" && turn < postLoadStartTurn + POST_LOAD_TURNS; turn += 1) {
        const phase = "post_load";
        const beforeSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `${phase}-turn-${turn}-before`) : null;
        const beforeChoices = await choiceSnapshots(page);
        const selected = routeIndexForTurn(turn, beforeChoices, beforeSnapshot);
        if (!selected || !cleanText(selected.text)) {
          issue("P0", "empty choice label before click; stopped without sending post-load choice", {
            turn_index: turn,
            phase,
            choices: beforeChoices,
            ui_snapshot: beforeSnapshot,
          });
          summary.result = "failed_script_empty_choice";
          await page.screenshot({ path: `${screenshotBase}-empty-choice-${phase}-turn${turn}.png`, fullPage: true });
          break;
        }
        const started = Date.now();
        const responsePromise = page.waitForResponse(
          (resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/choice"),
          { timeout: REQUEST_TIMEOUT_MS },
        );
        await page.locator(".choice-button").nth(selected.index).click();
        let response;
        try {
          response = await responsePromise;
        } catch (error) {
          const elapsed = Date.now() - started;
          turns.push({
            phase,
            turn_index: turn,
            selected_index: selected.index,
            choice: cleanText(selected.text),
            choice_letter: selected.letter,
            http_status: "",
            fallback: "",
            turn_count: "",
            elapsed_ms: elapsed,
            choices_count: beforeChoices.length,
            note: "choice_response_timeout",
            ui_before: beforeSnapshot,
          });
          issue("P0", "post-load choice response timed out before acceptance could be evaluated", {
            turn_index: turn,
            phase,
            timeout_ms: REQUEST_TIMEOUT_MS,
            elapsed_ms: elapsed,
            selected_index: selected.index,
          });
          summary.result = "failed_timeout";
          await page.screenshot({ path: `${screenshotBase}-timeout-${phase}-turn${turn}.png`, fullPage: true });
          break;
        }
        let body = null;
        try {
          body = await response.json();
        } catch {
          // Keep null; status will still be recorded.
        }
        const elapsed = Date.now() - started;
        const fallback = Boolean(body?.fallback_prompt?.active || body?.session?.fallback_prompt?.active);
        const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
        const afterChoices = Array.isArray(body?.choices)
          ? body.choices
          : Array.isArray(body?.session?.choices)
            ? body.session.choices
            : [];
        const gameOver = Boolean(body?.game_over ?? body?.session?.game_over);
        const finale = Boolean(body?.finale ?? body?.session?.finale);
        const diagnostics = latestModelDiagnostics(body, started);
        if (!gameOver) {
          await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
        } else {
          await page.waitForTimeout(500);
        }
        const afterSnapshot = CONTENT_AUDIT ? await uiSnapshot(page, `${phase}-turn-${turn}-after`) : null;
        const turnRecord = {
          phase,
          turn_index: turn,
          selected_index: selected.index,
          choice: cleanText(selected.text),
          choice_letter: selected.letter,
          http_status: response.status(),
          fallback,
          game_over: gameOver,
          finale,
          turn_count: turnCount,
          elapsed_ms: elapsed,
          choices_count: afterChoices.length,
          ...diagnostics,
          note: response.ok() ? (fallback ? "fallback" : (gameOver ? "terminal" : "non-fallback")) : "http_failure",
          ui_before: beforeSnapshot,
          ui_after: afterSnapshot,
        };
        auditVisibleContent({ turnRecord, beforeSnapshot, afterSnapshot, auditState, issue });
        auditModelDiagnostics(turnRecord, phase);
        turns.push(turnRecord);
        const turnAdvanced = turnCount === turn;
        const hasFourChoices = afterChoices.length === 4;
        const terminalAccepted = response.ok() && !fallback && turnAdvanced && gameOver;
        if (terminalAccepted) {
          summary.ended_early_game_over = true;
          summary.ended_at_turn = turn;
          summary.ended_finale = finale;
          summary.result = "passed_terminal";
          await page.screenshot({ path: `${screenshotBase}-terminal-${phase}-turn${turn}.png`, fullPage: true });
          break;
        }
        if (!response.ok() || fallback || !turnAdvanced || !hasFourChoices) {
          issue("P0", "post-load choice did not satisfy live-model acceptance", {
            turn_index: turn,
            phase,
            http_status: response.status(),
            fallback,
            game_over: gameOver,
            turn_count: turnCount,
            expected_turn_count: turn,
            turn_advanced: turnAdvanced,
            choices_count: afterChoices.length,
          });
          summary.result = "failed_or_partial";
          await page.screenshot({ path: `${screenshotBase}-stopped-${phase}-turn${turn}.png`, fullPage: true });
          break;
        }
      }
      updateSummaryFromTurns(summary, turns, auditState);
      if (summary.result === "running") {
        summary.result = "passed";
      }
    } else if (summary.result === "running") {
      summary.result = "failed_or_partial";
    }

    await page.screenshot({ path: `${screenshotBase}-final.png`, fullPage: true });
  } catch (error) {
    summary.result = "failed_script";
    issue("P0", "validation script failed", { error: String(error).slice(0, 1000) });
  } finally {
    summary.completed_at = new Date().toISOString();
    summary.p0_issues = issues.filter((item) => item.level === "P0").length;
    summary.p1_issues = issues.filter((item) => item.level === "P1").length;
    if (CONTENT_AUDIT_FAIL_ON_P1 && ["passed", "passed_terminal"].includes(summary.result) && summary.p1_issues > 0) {
      summary.result = "failed_content";
    }
    persistSource();
    let paths = {};
    try {
      paths = writeStrictEvidence(rawPath, STAMP);
    } catch (error) {
      issue("P0", "strict evidence writer failed", { error: String(error).slice(0, 1000) });
      persistSource();
    }
    console.log(JSON.stringify({ summary, issues, paths, source: rawPath }, null, 2));
    if (browser) {
      await browser.close();
    }
    if (
      !["passed", "passed_terminal"].includes(summary.result)
      || summary.p0_issues > 0
      || (CONTENT_AUDIT_FAIL_ON_P1 && summary.p1_issues > 0)
    ) {
      process.exitCode = 1;
    }
  }
})();

function avgMetric(rows, key) {
  const values = rows.map((row) => Number(row[key] || 0)).filter((value) => value > 0);
  if (!values.length) return 0;
  return Math.round(values.reduce((total, value) => total + value, 0) / values.length);
}
