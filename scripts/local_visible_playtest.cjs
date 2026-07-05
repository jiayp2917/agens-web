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
  return {
    narrator_elapsed_ms: numberMetric(narratorDiag.elapsed_ms),
    judge_elapsed_ms: numberMetric(judgeDiag.elapsed_ms),
    repair_elapsed_ms: numberMetric(narratorDiag.repair_elapsed_ms),
    repaired_output: Boolean(narratorDiag.repaired_output),
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

function numberMetric(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const inviteCode = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const username = `chrome_${Date.now()}`;
  const password = `pw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const rawPath = path.join(OUT_DIR, `${STAMP}-source.json`);
  const screenshotBase = path.join(OUT_DIR, STAMP);
  const summary = {
    scenario: "local visible Chrome 20-turn playtest",
    target_turns: TARGET_TURNS,
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

  function issue(level, text, data = {}) {
    issues.push({ level, text, ...data });
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

    for (let turn = 1; summary.result === "running" && turn <= TARGET_TURNS; turn += 1) {
      const beforeChoices = await choiceSnapshots(page);
      const enabled = beforeChoices.filter((choice) => !choice.disabled);
      const selected = enabled[(turn - 1) % Math.max(1, enabled.length)];
      if (!selected || !cleanText(selected.text)) {
        issue("P0", "empty choice label before click; stopped without sending choice", {
          turn_index: turn,
          choices: beforeChoices,
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
      const diagnostics = latestModelDiagnostics(body, started);
      turns.push({
        turn_index: turn,
        selected_index: selected.index,
        choice: cleanText(selected.text),
        choice_letter: selected.letter,
        http_status: response.status(),
        fallback,
        turn_count: turnCount,
        elapsed_ms: elapsed,
        choices_count: afterChoices.length,
        ...diagnostics,
        note: response.ok() ? (fallback ? "fallback" : "non-fallback") : "http_failure",
      });

      const turnAdvanced = turnCount === turn;
      const hasFourChoices = afterChoices.length === 4;
      if (!response.ok() || fallback || !turnAdvanced || !hasFourChoices) {
        issue("P0", "choice did not satisfy live-model acceptance", {
          turn_index: turn,
          http_status: response.status(),
          fallback,
          turn_count: turnCount,
          expected_turn_count: turn,
          turn_advanced: turnAdvanced,
          choices_count: afterChoices.length,
        });
        summary.result = "failed_or_partial";
        await page.screenshot({ path: `${screenshotBase}-stopped-turn${turn}.png`, fullPage: true });
        break;
      }
      await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
    }

    summary.turns_completed = turns.length;
    summary.accepted_live_turns = turns.filter((turn) => turn.http_status >= 200 && turn.http_status < 300 && !turn.fallback).length;
    summary.fallback_count = turns.filter((turn) => turn.fallback).length;
    summary.max_elapsed_ms = Math.max(0, ...turns.map((turn) => turn.elapsed_ms || 0));
    summary.avg_elapsed_ms = turns.length
      ? Math.round(turns.reduce((total, turn) => total + (turn.elapsed_ms || 0), 0) / turns.length)
      : 0;
    summary.repair_attempt_count = turns.filter((turn) => (turn.repair_elapsed_ms || 0) > 0).length;
    summary.repaired_output_count = turns.filter((turn) => turn.repaired_output).length;
    summary.judge_count = turns.filter((turn) => (turn.judge_elapsed_ms || 0) > 0).length;
    summary.avg_narrator_elapsed_ms = avgMetric(turns, "narrator_elapsed_ms");
    summary.avg_judge_elapsed_ms = avgMetric(turns, "judge_elapsed_ms");
    summary.avg_repair_elapsed_ms = avgMetric(turns, "repair_elapsed_ms");
    summary.avg_prompt_chars = avgMetric(turns, "prompt_chars");
    summary.max_prompt_chars = Math.max(0, ...turns.map((turn) => turn.prompt_chars || 0));
    summary.max_history_count = Math.max(0, ...turns.map((turn) => turn.history_count || 0));
    summary.last_turn_count = turns.length ? turns[turns.length - 1].turn_count : 0;

    if (summary.accepted_live_turns >= TARGET_TURNS && summary.fallback_count === 0 && !issues.some((item) => item.level === "P0")) {
      await page.locator('button[aria-label*="存"]').click();
      await page.waitForSelector(".settings-dialog", { timeout: 30000 });
      await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:last-child"], 30000);
      await page.waitForTimeout(1000);
      await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:first-child"], 30000);
      await page.waitForSelector(".choice-button", { timeout: 30000 });
      await page.screenshot({ path: `${screenshotBase}-save-load.png`, fullPage: true });
      summary.save_load_passed = true;
      summary.result = "passed";
    } else if (summary.result === "running") {
      summary.result = "failed_or_partial";
    }

    await page.screenshot({ path: `${screenshotBase}-final.png`, fullPage: true });
  } catch (error) {
    summary.result = "failed_script";
    issue("P0", "validation script failed", { error: String(error).slice(0, 1000) });
  } finally {
    summary.completed_at = new Date().toISOString();
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
    if (summary.result !== "passed" || issues.some((item) => item.level === "P0")) {
      process.exitCode = 1;
    }
  }
})();

function avgMetric(rows, key) {
  const values = rows.map((row) => Number(row[key] || 0)).filter((value) => value > 0);
  if (!values.length) return 0;
  return Math.round(values.reduce((total, value) => total + value, 0) / values.length);
}
