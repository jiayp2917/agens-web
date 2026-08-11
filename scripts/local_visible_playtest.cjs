#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const { browserOutputDir } = require("./playtest_output.cjs");
const browserDriver = require("./playtest/browser_driver.cjs");
const acceptanceDecision = require("./playtest/acceptance_decision.cjs");
const acceptanceReport = require("./playtest/acceptance_report.cjs");
const persistedTurnAudit = require("./playtest/persisted_turn_audit.cjs");
const visibleContentAudit = require("./playtest/visible_content_audit.cjs");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = browserOutputDir(ROOT);
const BASE_URL = process.env.AGENS_PLAYTEST_URL || "http://127.0.0.1:5173/static/";
const API_BASE_URL = process.env.AGENS_PLAYTEST_API_BASE || "";
const TARGET_TURNS = Number(process.env.AGENS_PLAYTEST_TURNS || "20");
const OPENING_ONLY = process.env.AGENS_PLAYTEST_OPENING_ONLY === "1";
const REQUEST_TIMEOUT_MS = Number(process.env.AGENS_PLAYTEST_TIMEOUT_MS || "300000");
const STAMP = process.env.AGENS_PLAYTEST_NAME || `local-visible-20turn-${stamp()}`;
const CONTENT_AUDIT = process.env.AGENS_PLAYTEST_CONTENT_AUDIT === "1";
const CONTENT_AUDIT_FAIL_ON_P1 = CONTENT_AUDIT && process.env.AGENS_PLAYTEST_FAIL_ON_P1 !== "0";
const CHOICE_STRATEGY = (process.env.AGENS_PLAYTEST_CHOICE_STRATEGY || "cycle").toLowerCase();
const POST_LOAD_TURNS = Number(process.env.AGENS_PLAYTEST_POST_LOAD_TURNS || (CONTENT_AUDIT ? "3" : "0"));
const SAVE_LOAD_TURN = Number(process.env.AGENS_PLAYTEST_SAVE_LOAD_TURN || "0");
const REFRESH_PROBE = process.env.AGENS_PLAYTEST_REFRESH_PROBE === "1";
const DOUBLE_CLICK_PROBE = process.env.AGENS_PLAYTEST_DOUBLE_CLICK_PROBE === "1";
const CONFLICT_PROBE = process.env.AGENS_PLAYTEST_CONFLICT_PROBE === "1";
const REQUIRE_FINALE = process.env.AGENS_PLAYTEST_REQUIRE_FINALE === "1";
const REQUIRE_PERSISTED_AUDIT = process.env.AGENS_PLAYTEST_REQUIRE_PERSISTED_AUDIT === "1";
const REQUIRE_LIVE_OPENING = process.env.AGENS_PLAYTEST_REQUIRE_LIVE_OPENING === "1";
const LOCAL_STORY_MODE = process.env.AGENS_PLAYTEST_LOCAL_STORY === "1";
const VIEWPORT = browserDriver.parseViewport(process.env.AGENS_PLAYTEST_VIEWPORT || "1440x1000");
const SLOT_SEQUENCE = browserDriver.parseSlotSequence(process.env.AGENS_PLAYTEST_SLOT_SEQUENCE || "");

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function evidenceContext() {
  const command = (args) => spawnSync("git", args, {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  }).stdout || "";
  const head = command(["rev-parse", "HEAD"]).trim();
  const status = command(["status", "--porcelain=v1"]);
  const diff = command(["diff", "--binary", "--no-ext-diff"]);
  const databaseLabel = String(process.env.AGENS_PLAYTEST_DATABASE_LABEL || "").trim();
  return {
    head,
    dirty: Boolean(status.trim()),
    worktree_fingerprint: sha256(`${head}\n${status}\n${diff}`),
    playtest_script_sha256: sha256(fs.readFileSync(__filename)),
    database_label: /^[A-Za-z0-9_.-]{1,80}$/u.test(databaseLabel) ? databaseLabel : "",
  };
}

const SENSITIVE_EVIDENCE_KEYS = new Set([
  "api_key",
  "apikey",
  "authorization",
  "cookie",
  "password",
  "secret",
  "token",
  "base_url",
  "prompt",
  "messages",
  "user_input",
  "game_state_json",
]);

function redactEvidence(value) {
  if (Array.isArray(value)) return value.map(redactEvidence);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key,
      isSensitiveEvidenceKey(key) ? "[redacted]" : redactEvidence(item),
    ]));
  }
  if (typeof value !== "string") return value;
  return value
    .replace(/(?:[A-Za-z][A-Za-z0-9_-]*?(?:key|secret|token|cookie|authorization|password))\s*[:=]\s*[^\s,;]+/giu, "[redacted_secret]")
    .replace(/\bbearer\s+[A-Za-z0-9._~+/=-]{8,}/giu, "[redacted_secret]")
    .replace(/\b(?:sk|ag|ds|rk)-[A-Za-z0-9_-]{8,}\b/giu, "[redacted_secret]")
    .replace(/https?:\/\/[^\s\]\["'<>{}]+/giu, "[redacted_url]");
}

function isSensitiveEvidenceKey(key) {
  const normalized = String(key || "").trim().toLowerCase().replace(/-/gu, "_");
  return SENSITIVE_EVIDENCE_KEYS.has(normalized)
    || normalized.includes("secret")
    || normalized.includes("password")
    || (normalized.includes("token") && !normalized.endsWith("_tokens"));
}

function pythonExe() {
  const local = path.join(ROOT, ".venv", "Scripts", "python.exe");
  return fs.existsSync(local) ? local : "python";
}

function cleanText(value) {
  return browserDriver.cleanText(value);
}

function displayedChoiceText(value) {
  let text = cleanText(value).replace(/^【(?:稳妥|机遇|风险|气运)】\s*/, "");
  for (let index = 0; index < 3; index += 1) {
    const next = text
      .replace(/^(?:[（(]?\s*[A-Da-d1-4]\s*[）)]?|选项\s*[A-Da-d])(?:\s*[.:：、)）．。-]|\s+(?=(?:稳妥|机遇|风险|气运)\s*[：:]))\s*/, "")
      .replace(/^(?:稳妥|机遇|风险|气运)\s*[：:]\s*/, "")
      .replace(/^[A-Da-d1-4](?=[\u3400-\u9fff])/, "")
      .trim();
    if (next === text) break;
    text = next;
  }
  return text;
}

async function waitForRenderedChoices(page, choices) {
  const expected = Array.isArray(choices)
    ? choices.map((choice) => displayedChoiceText(choice)).filter(Boolean)
    : [];
  if (expected.length !== 4) return;
  await page.waitForFunction((expectedChoices) => {
    const actual = [...document.querySelectorAll(".choice-button")].map((button, index) => {
      const letter = String(
        button.querySelector(".choice-mark")?.textContent || String.fromCharCode(65 + index),
      ).trim().slice(0, 1);
      const source = button.querySelector(".choice-copy")?.textContent || button.textContent || "";
      return String(source)
        .replace(/\s+/g, " ")
        .replace(new RegExp(`^${letter}\\s*[.:\uFF1A\u3001)\uFF09-]?\\s*`), "")
        .replace(/^[A-Da-d1-4]\s*[.:\uFF1A\u3001)\uFF09-]?\s*/, "")
        .replace(/^[A-Da-d1-4](?=[\u3400-\u9fff])/, "")
        .trim();
    });
    return actual.length === expectedChoices.length
      && actual.every((choice, index) => choice === expectedChoices[index]);
  }, expected, { timeout: REQUEST_TIMEOUT_MS });
}

function acceptedTurnEvidence(turns) {
  const accepted = new Map();
  for (const turn of turns) {
    const turnIndex = Number(turn?.turn_index || 0);
    const status = Number(turn?.http_status || 0);
    const strict = turn?.narrator_status === "ok"
      && !turn?.fallback
      && !turn?.repaired_output
      && !turn?.contract_recovery;
    if (!turnIndex || !strict || status < 200 || status >= 300 || Number(turn?.turn_count || 0) !== turnIndex) {
      continue;
    }
    accepted.set(turnIndex, {
      turn: turnIndex,
      slot: cleanText(turn.choice_letter),
      narrative: cleanText(turn.latest_chronicle_text),
      choices: (turn.choice_texts_after || []).map((choice) => cleanText(choice)).filter(Boolean),
      strict: {
        first_pass: !turn.retried_after_request_failed && !turn.retried_after_incomplete_output,
        final: true,
      },
      retry: Boolean(turn.retried_after_request_failed || turn.retried_after_incomplete_output),
      repair: Boolean(turn.repaired_output),
      fallback: Boolean(turn.fallback),
      recovery: Boolean(turn.contract_recovery),
      timing_ms: {
        end_to_end: Math.max(0, Number(turn.elapsed_ms || 0)),
        full_response: Math.max(0, Number(turn.narrator_elapsed_ms || 0)),
        ttft: null,
      },
    });
  }
  return [...accepted.values()].sort((left, right) => left.turn - right.turn);
}

module.exports = {
  canBreakthroughFromRealmText: visibleContentAudit.canBreakthroughFromRealmText,
  hasBreakthroughIntent: visibleContentAudit.hasBreakthroughIntent,
  narrativeRealmClaims: visibleContentAudit.narrativeRealmClaims,
  normalizedRealmLabel: visibleContentAudit.normalizedRealmLabel,
  redactEvidence,
  realmClaimMatchesCurrent: visibleContentAudit.realmClaimMatchesCurrent,
  displayedChoiceText,
};

if (require.main === module) {
(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const inviteCode = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const username = `chrome_${Date.now()}`;
  const password = `pw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const rawPath = path.join(OUT_DIR, `${STAMP}-source.json`);
  const screenshotBase = path.join(OUT_DIR, STAMP);
  const summary = acceptanceReport.createAcceptanceSummary({
    targetTurns: TARGET_TURNS,
    contentAudit: CONTENT_AUDIT,
    contentAuditFailOnP1: CONTENT_AUDIT_FAIL_ON_P1,
    choiceStrategy: CHOICE_STRATEGY,
    postLoadTurns: POST_LOAD_TURNS,
    saveLoadTurn: SAVE_LOAD_TURN,
    refreshProbe: REFRESH_PROBE,
    doubleClickProbe: DOUBLE_CLICK_PROBE,
    conflictProbe: CONFLICT_PROBE,
    requireFinale: REQUIRE_FINALE,
    requireLiveOpening: REQUIRE_LIVE_OPENING,
    viewport: VIEWPORT,
    evidenceContext: evidenceContext(),
    requestTimeoutMs: REQUEST_TIMEOUT_MS,
  });
  summary.opening_only = OPENING_ONLY;
    summary.local_story_mode = LOCAL_STORY_MODE;
  const turns = [];
  const issues = [];
  const requests = [];
  const consoleMessages = [];
  const auditState = visibleContentAudit.createVisibleAuditState();
  const issue = acceptanceReport.createIssueCollector(issues);
  const auditModelDiagnostics = (turnRecord, phase) =>
    acceptanceReport.auditModelDiagnostics(turnRecord, phase, issue);

  function persistSource() {
    fs.writeFileSync(
      rawPath,
      JSON.stringify(redactEvidence({ summary: { ...summary, issues, requests, console: consoleMessages }, turns }), null, 2) + "\n",
      "utf8",
    );
  }

  let browser;
  let playtestSessionId = "";
  let persistedOpeningState = null;
  try {
    browserDriver.ensureInvite({ root: ROOT, pythonExe: pythonExe(), inviteCode });
    summary.invite_seeded = true;

    const { chromium } = browserDriver.loadPlaywright();
    const executablePath = browserDriver.chromeExecutablePath();
    if (!executablePath) {
      throw new Error("No local Chrome/Edge executable found. Set AGENS_CHROME_PATH to a visible browser executable.");
    }
    summary.browser_executable = path.basename(executablePath);
    const conflictState = CONFLICT_PROBE ? { armed: false, triggered: false, error: "" } : null;
    browser = await chromium.launch({
      headless: false,
      executablePath,
      args: [`--window-size=${VIEWPORT.width},${VIEWPORT.height}`],
    });
    const page = await browser.newPage({ viewport: VIEWPORT });
    await browserDriver.routeApiBase(page, { apiBaseUrl: API_BASE_URL, conflictState });

    page.on("console", (msg) => {
      consoleMessages.push({ type: msg.type(), text: msg.text().slice(0, 500) });
    });
    page.on("response", async (response) => {
      if (!response.url().includes("/api/")) return;
      const rec = {
        url: browserDriver.redactedUrl(response.url()),
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

    await browserDriver.clickFirstVisible(page, [".home-actions button:nth-child(5)", "text=邀请码注册", "text=注册"], 30000);
    await page.locator('input[name="username"]').fill(username);
    await page.locator('input[name="password"]').fill(password);
    await page.locator('input[name="invite_code"]').fill(inviteCode);
    await Promise.all([
      page.waitForResponse((resp) => resp.url().includes("/api/auth/register") && resp.request().method() === "POST", {
        timeout: 30000,
      }),
      page.locator(".auth-panel button[type='submit']").click(),
    ]);
    await page.waitForSelector(".user-chip", { state: "attached", timeout: 30000 });
    summary.registration_passed = true;

    await browserDriver.clickFirstVisible(page, [".home-actions button:nth-child(1)", "text=新游戏"], 30000);
    await page.waitForSelector('input[name="char_name"]', { timeout: 30000 });
    await page.locator('input[name="char_name"]').fill("验真者");
    if (CHOICE_STRATEGY === "golden") {
      await browserDriver.configureGoldenProfile(page);
      summary.golden_profile_configured = true;
    }
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
    playtestSessionId = cleanText(startBody?.session_id);
    Object.assign(summary, acceptanceReport.startAcceptance(startBody, startResponse.status(), cleanText));
    if (LOCAL_STORY_MODE && startResponse.ok()) {
      const pending = startBody?.pending_model_failure;
      if (pending?.stage !== "opening") {
        issue("P0", "local-story mode did not receive a pending opening failure", {
          pending_stage: cleanText(pending?.stage),
        });
        summary.result = "failed_or_partial";
      } else {
        const actionResponse = page.waitForResponse(
          (resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/action"),
          { timeout: REQUEST_TIMEOUT_MS },
        );
        await page.getByRole("button", { name: "本地故事" }).click();
        const response = await actionResponse;
        let body = null;
        try {
          body = await response.json();
        } catch {
          // The status and visible choices below still determine acceptance.
        }
        const choices = Array.isArray(body?.choices) ? body.choices : [];
        await waitForRenderedChoices(page, choices);
        summary.local_story_opening_passed = Boolean(
          response.ok() && body?.local_story?.active && !body?.pending_model_failure && choices.length === 4,
        );
        if (!summary.local_story_opening_passed) {
          issue("P0", "player-selected local story did not complete the opening", {
            http_status: response.status(),
            choices_count: choices.length,
            local_story_active: Boolean(body?.local_story?.active),
            pending_model_failure: Boolean(body?.pending_model_failure),
          });
          summary.result = "failed_or_partial";
        }
      }
    }
    await page.waitForSelector(".choice-button", { timeout: REQUEST_TIMEOUT_MS });
    const startUiSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, "start") : null;
    const startForbiddenHits = (startUiSnapshot?.forbidden_hits || []).filter(
      (hit) => !(LOCAL_STORY_MODE && hit === "model_unavailable_notice"),
    );
    if (CONTENT_AUDIT && startForbiddenHits.length) {
      issue("P1", "player-visible forbidden/internal text appeared at start", {
        hits: startForbiddenHits,
        latest_text: startUiSnapshot.latest_chronicle?.at(-1)?.text || "",
        fallback_banner_set: Boolean(startUiSnapshot.fallback_banner),
      });
    }
    if (CONTENT_AUDIT && startUiSnapshot?.viewport?.horizontal_overflow) {
      issue("P1", "opening page has horizontal overflow at the configured viewport", {
        viewport: startUiSnapshot.viewport,
      });
    }
    summary.start_ui_snapshot = startUiSnapshot;
    const startGenericChoices = visibleContentAudit.genericChoiceTexts(startUiSnapshot?.choices);
    if (CONTENT_AUDIT && startGenericChoices.length) {
      issue("P1", "opening choices contain generic placeholder text", {
        choices: startGenericChoices,
      });
    }
    await page.screenshot({ path: `${screenshotBase}-start.png`, fullPage: true });
    summary.start_passed = true;

    if (REQUIRE_PERSISTED_AUDIT && playtestSessionId && startResponse.ok()) {
      try {
        persistedOpeningState = persistedTurnAudit.readPersistedOpeningState({
          root: ROOT,
          pythonExe: pythonExe(),
          sessionId: playtestSessionId,
        });
        summary.persisted_opening_state_captured = true;
      } catch (error) {
        issue("P0", "persisted turn audit could not capture the opening state", {
          error: String(error).slice(0, 1000),
        });
      }
    }

    if (
      !startResponse.ok()
      || (LOCAL_STORY_MODE
        ? !summary.local_story_opening_passed
        : (summary.start_fallback
          || (REQUIRE_LIVE_OPENING && !summary.start_model_ok)
          || summary.start_choices_count !== 4))
      || !summary.start_world_name_set
      || summary.start_chronicle_count < 1
      || !summary.start_initial_situation_set
    ) {
      issue("P0", "start did not satisfy opening acceptance", {
        http_status: summary.start_http_status,
        fallback: LOCAL_STORY_MODE ? !summary.local_story_opening_passed : summary.start_fallback,
        model_ok: summary.start_model_ok,
        choices_count: summary.start_choices_count,
        world_name_set: summary.start_world_name_set,
        chronicle_count: summary.start_chronicle_count,
        initial_situation_set: summary.start_initial_situation_set,
      });
      summary.result = "failed_or_partial";
      await page.screenshot({ path: `${screenshotBase}-start-rejected.png`, fullPage: true });
    }

    if (OPENING_ONLY && summary.result === "running") {
      summary.result = "passed";
    } else {
    let firstMainTurn = 1;
    if (summary.result === "running" && CONFLICT_PROBE) {
      const phase = "version_conflict";
      const beforeSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-before`) : null;
      const beforeChoices = await browserDriver.choiceSnapshots(page);
      const selected = browserDriver.routeIndexForTurn(1, beforeChoices, beforeSnapshot, {
        choiceStrategy: CHOICE_STRATEGY,
        slotSequence: SLOT_SEQUENCE,
      });
      if (!selected || !cleanText(selected.text)) {
        issue("P0", "empty choice label before conflict probe", {
          phase,
          choices: beforeChoices,
          ui_snapshot: beforeSnapshot,
        });
        summary.result = "failed_script_empty_choice";
      } else {
        const requestStartIndex = requests.length;
        conflictState.armed = true;
        const choice = page.locator(".choice-button").nth(selected.index);
        await choice.focus();
        const focusBefore = await choice.evaluate((element) => element === document.activeElement);
        const responsePromise = page.waitForResponse(
          (resp) => resp.url().includes("/api/sessions/") && resp.url().includes("/choice"),
          { timeout: REQUEST_TIMEOUT_MS },
        );
        await page.keyboard.press("Enter");
        let response = null;
        try {
          response = await responsePromise;
        } catch {
          // The summary below records the missing 409 as a failed probe.
        }
        const notice = page.locator('.toast.toast-notice[role="status"]');
        let noticeText = "";
        if (response?.status() === 409) {
          try {
            await notice.waitFor({ state: "visible", timeout: 30000 });
            noticeText = cleanText(await notice.textContent());
          } catch {
            // A missing visible conflict notice is part of the probe result.
          }
        }
        await page.waitForTimeout(250);
        const afterSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-after`) : null;
        const probeRequests = requests.slice(requestStartIndex);
        const choiceResponseCount = probeRequests.filter((request) => request.url.includes("/choice")).length;
        const refreshResponseCount = probeRequests.filter(
          (request) => request.method === "GET" && request.url.includes("/api/sessions/<id>"),
        ).length;
        const focusAfter = await page.evaluate(() => ({
          tag: document.activeElement?.tagName || "",
          class_name: document.activeElement?.className || "",
          text: String(document.activeElement?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160),
        }));
        summary.conflict_probe_passed = Boolean(
          response?.status() === 409
          && conflictState.triggered
          && !conflictState.error
          && focusBefore
          && noticeText.includes("已加载最新进度")
          && choiceResponseCount === 1
          && refreshResponseCount >= 1
        );
        summary.conflict_probe_evidence = {
          http_status: response?.status() || 0,
          keyboard_focus_before: focusBefore,
          focus_after: focusAfter,
          notice_text: noticeText,
          choice_response_count: choiceResponseCount,
          refresh_response_count: refreshResponseCount,
          route_triggered: conflictState.triggered,
          route_error: conflictState.error,
          ui_before: beforeSnapshot,
          ui_after: afterSnapshot,
        };
        await page.screenshot({ path: `${screenshotBase}-version-conflict.png`, fullPage: true });
        if (!summary.conflict_probe_passed) {
          issue("P1", "version-conflict probe did not prove keyboard, refresh, and visible feedback", {
            phase,
            ...summary.conflict_probe_evidence,
          });
          summary.result = "failed_or_partial";
        }
      }
    }
    if (summary.result === "running" && DOUBLE_CLICK_PROBE) {
      const phase = "double_click";
      const beforeSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-turn-1-before`) : null;
      const beforeChoices = await browserDriver.choiceSnapshots(page);
      const selected = browserDriver.routeIndexForTurn(1, beforeChoices, beforeSnapshot, {
        choiceStrategy: CHOICE_STRATEGY,
        slotSequence: SLOT_SEQUENCE,
      });
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
        const localStoryActive = Boolean(body?.local_story?.active || body?.session?.local_story?.active);
        const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
        const afterChoices = Array.isArray(body?.choices)
          ? body.choices
          : Array.isArray(body?.session?.choices)
            ? body.session.choices
            : [];
        await waitForRenderedChoices(page, afterChoices);
        const afterSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-turn-1-after`) : null;
        const turnRecord = {
          phase,
          turn_index: 1,
          selected_index: selected.index,
          choice: cleanText(selected.text),
          choice_letter: selected.letter,
          http_status: response ? response.status() : "",
          fallback,
          local_story_active: localStoryActive,
          turn_count: turnCount,
          elapsed_ms: elapsed,
          choices_count: afterChoices.length,
          choice_response_count: choiceResponseCount,
          ...acceptanceReport.latestModelDiagnostics(body, started),
          note: response ? (fallback ? "fallback" : "non-fallback") : "choice_response_timeout",
          ui_before: beforeSnapshot,
          ui_after: afterSnapshot,
        };
        visibleContentAudit.auditVisibleContent({
          enabled: CONTENT_AUDIT,
          allowModelUnavailableNotice: LOCAL_STORY_MODE,
          turnRecord,
          beforeSnapshot,
          afterSnapshot,
          auditState,
          issue,
        });
        if (!LOCAL_STORY_MODE) auditModelDiagnostics(turnRecord, phase);
        turns.push(turnRecord);
        summary.double_click_probe_passed = Boolean(
          response?.ok()
          && (LOCAL_STORY_MODE ? localStoryActive : !fallback)
          && turnCount === 1
          && choiceResponseCount === 1,
        );
        if (!summary.double_click_probe_passed) {
          issue(response ? "P1" : "P0", "double-click probe did not prove single-submit behavior", {
            turn_index: 1,
            phase,
            http_status: response ? response.status() : "",
            fallback,
            turn_count: turnCount,
            choice_response_count: choiceResponseCount,
          });
          if (!response || turnCount < 1 || (LOCAL_STORY_MODE ? !localStoryActive : fallback)) {
            summary.result = "failed_or_partial";
          }
        }
        firstMainTurn = Math.max(2, turnCount + 1);
      }
    }

    for (let turn = firstMainTurn; summary.result === "running" && turn <= TARGET_TURNS; turn += 1) {
      const beforeSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `turn-${turn}-before`) : null;
      const beforeChoices = await browserDriver.choiceSnapshots(page);
      const enabled = beforeChoices.filter((choice) => !choice.disabled);
      const selected = browserDriver.routeIndexForTurn(turn, beforeChoices, beforeSnapshot, {
        choiceStrategy: CHOICE_STRATEGY,
        slotSequence: SLOT_SEQUENCE,
      });
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
      const localStoryActive = Boolean(body?.local_story?.active || body?.session?.local_story?.active);
      const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
      const afterChoices = Array.isArray(body?.choices)
        ? body.choices
        : Array.isArray(body?.session?.choices)
          ? body.session.choices
          : [];
      const gameOver = Boolean(body?.game_over ?? body?.session?.game_over);
      const finale = Boolean(body?.finale ?? body?.session?.finale);
      const diagnostics = acceptanceReport.latestModelDiagnostics(body, started);
      if (!gameOver) {
        await waitForRenderedChoices(page, afterChoices);
      } else {
        await page.waitForTimeout(500);
      }
      const afterSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `turn-${turn}-after`) : null;
      const turnRecord = {
        phase: "main",
        turn_index: turn,
        selected_index: selected.index,
        choice: cleanText(selected.text),
        choice_letter: selected.letter,
        http_status: response.status(),
        fallback,
        local_story_active: localStoryActive,
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
      visibleContentAudit.auditVisibleContent({
        enabled: CONTENT_AUDIT,
        allowModelUnavailableNotice: LOCAL_STORY_MODE,
        turnRecord,
        beforeSnapshot,
        afterSnapshot,
        auditState,
        issue,
      });
      if (!LOCAL_STORY_MODE) auditModelDiagnostics(turnRecord, "main");
      turns.push(turnRecord);

      const turnAdvanced = turnCount === turn;
      const hasFourChoices = afterChoices.length === 4;
      const strictModelOk = diagnostics.narrator_status === "ok"
        && !diagnostics.contract_recovery
        && (!diagnostics.provider_json_schema || diagnostics.provider_json_envelope_ok);
      const localStoryAccepted = LOCAL_STORY_MODE
        && response.ok()
        && localStoryActive
        && !body?.pending_model_failure
        && turnAdvanced
        && (gameOver || hasFourChoices);
      const terminalAccepted = localStoryAccepted
        ? gameOver
        : response.ok() && !fallback && strictModelOk && turnAdvanced && gameOver;
      if (terminalAccepted) {
        summary.ended_early_game_over = true;
        summary.ended_at_turn = turn;
        summary.ended_finale = finale;
        summary.result = "passed_terminal";
        await page.screenshot({ path: `${screenshotBase}-terminal-turn${turn}.png`, fullPage: true });
        break;
      }
      if (!(LOCAL_STORY_MODE ? localStoryAccepted : (response.ok() && !fallback && strictModelOk && turnAdvanced && hasFourChoices))) {
        issue("P0", LOCAL_STORY_MODE
          ? "local-story choice did not preserve the expected session state"
          : "choice did not satisfy live-model acceptance", {
          turn_index: turn,
          http_status: response.status(),
          fallback,
          narrator_status: diagnostics.narrator_status,
          contract_recovery: diagnostics.contract_recovery,
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
      if (SAVE_LOAD_TURN > 0 && turn === SAVE_LOAD_TURN) {
        await browserDriver.runSaveLoadProbe(page, {
          summary,
          issue,
          screenshotBase,
          label: `turn${turn}`,
          contentAudit: CONTENT_AUDIT,
          refreshProbe: REFRESH_PROBE,
        });
      }
    }

    acceptanceReport.updateSummaryFromTurns(summary, turns, auditState);

    if (summary.ended_early_game_over) {
      if (!summary.save_load_passed) summary.save_load_skipped_terminal = true;
    } else if ((LOCAL_STORY_MODE
      ? turns.filter((turn) => turn.local_story_active).length >= TARGET_TURNS
      : summary.accepted_live_turns >= TARGET_TURNS && summary.fallback_count === 0)
      && !issues.some((item) => item.level === "P0")) {
      summary.local_story_turns = turns.filter((turn) => turn.local_story_active).length;
      await browserDriver.runSaveLoadProbe(page, {
        summary,
        issue,
        screenshotBase,
        label: "final",
        contentAudit: CONTENT_AUDIT,
        refreshProbe: REFRESH_PROBE,
      });
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
        const beforeSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-turn-${turn}-before`) : null;
        const beforeChoices = await browserDriver.choiceSnapshots(page);
        const selected = browserDriver.routeIndexForTurn(turn, beforeChoices, beforeSnapshot, {
          choiceStrategy: CHOICE_STRATEGY,
          slotSequence: SLOT_SEQUENCE,
        });
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
        const localStoryActive = Boolean(body?.local_story?.active || body?.session?.local_story?.active);
        const turnCount = Number(body?.turn_count ?? body?.session?.turn_count ?? 0);
        const afterChoices = Array.isArray(body?.choices)
          ? body.choices
          : Array.isArray(body?.session?.choices)
            ? body.session.choices
            : [];
        const gameOver = Boolean(body?.game_over ?? body?.session?.game_over);
        const finale = Boolean(body?.finale ?? body?.session?.finale);
        const diagnostics = acceptanceReport.latestModelDiagnostics(body, started);
        if (!gameOver) {
          await waitForRenderedChoices(page, afterChoices);
        } else {
          await page.waitForTimeout(500);
        }
        const afterSnapshot = CONTENT_AUDIT ? await browserDriver.uiSnapshot(page, `${phase}-turn-${turn}-after`) : null;
        const turnRecord = {
          phase,
          turn_index: turn,
          selected_index: selected.index,
          choice: cleanText(selected.text),
          choice_letter: selected.letter,
          http_status: response.status(),
          fallback,
          local_story_active: localStoryActive,
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
        visibleContentAudit.auditVisibleContent({
          enabled: CONTENT_AUDIT,
          allowModelUnavailableNotice: LOCAL_STORY_MODE,
          turnRecord,
          beforeSnapshot,
          afterSnapshot,
          auditState,
          issue,
        });
        if (!LOCAL_STORY_MODE) auditModelDiagnostics(turnRecord, phase);
        turns.push(turnRecord);
        const turnAdvanced = turnCount === turn;
        const hasFourChoices = afterChoices.length === 4;
        const strictModelOk = diagnostics.narrator_status === "ok"
          && !diagnostics.contract_recovery
          && (!diagnostics.provider_json_schema || diagnostics.provider_json_envelope_ok);
        const localStoryAccepted = LOCAL_STORY_MODE
          && Boolean(body?.local_story?.active)
          && !body?.pending_model_failure
          && response.ok()
          && turnAdvanced
          && (gameOver || hasFourChoices);
        const terminalAccepted = localStoryAccepted
          ? gameOver
          : response.ok() && !fallback && strictModelOk && turnAdvanced && gameOver;
        if (terminalAccepted) {
          summary.ended_early_game_over = true;
          summary.ended_at_turn = turn;
          summary.ended_finale = finale;
          summary.result = "passed_terminal";
          await page.screenshot({ path: `${screenshotBase}-terminal-${phase}-turn${turn}.png`, fullPage: true });
          break;
        }
        if (!(LOCAL_STORY_MODE
          ? localStoryAccepted
          : (response.ok() && !fallback && strictModelOk && turnAdvanced && hasFourChoices))) {
          issue("P0", LOCAL_STORY_MODE
            ? "local-story choice did not preserve the expected session state"
            : "post-load choice did not satisfy live-model acceptance", {
            turn_index: turn,
            phase,
            http_status: response.status(),
            fallback,
            narrator_status: diagnostics.narrator_status,
            contract_recovery: diagnostics.contract_recovery,
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
      acceptanceReport.updateSummaryFromTurns(summary, turns, auditState);
      if (summary.result === "running") {
        summary.result = "passed";
      }
    } else if (summary.result === "running") {
      summary.result = "failed_or_partial";
    }

    }
    await page.screenshot({ path: `${screenshotBase}-final.png`, fullPage: true });
  } catch (error) {
    summary.result = "failed_script";
    issue("P0", "validation script failed", { error: String(error).slice(0, 1000) });
  } finally {
    summary.completed_at = new Date().toISOString();
    if (REQUIRE_FINALE && !summary.ended_finale) {
      issue("P1", "validation required a finale but the run did not reach ascension", {
        ended_at_turn: summary.ended_at_turn || 0,
        turns_completed: summary.turns_completed || 0,
      });
      summary.result = "failed_terminal";
    }
    if (REQUIRE_PERSISTED_AUDIT && !OPENING_ONLY) {
      if (!playtestSessionId) {
        issue("P0", "persisted turn audit could not identify the playtest session");
      } else {
        try {
          const persisted = persistedTurnAudit.readPersistedTurnAudit({
            root: ROOT,
            pythonExe: pythonExe(),
            sessionId: playtestSessionId,
            openingState: persistedOpeningState,
          });
          acceptanceReport.applyPersistedTurnAudit(summary, persisted, issue);
        } catch (error) {
          issue("P0", "persisted turn audit failed", { error: String(error).slice(0, 1000) });
        }
      }
    }
    summary.accepted_turns = acceptedTurnEvidence(turns);
    acceptanceReport.updateIssueCounts(summary, issues);
    summary.result = acceptanceDecision.evaluateAcceptance({
      result: summary.result,
      issues,
      contentAuditFailOnP1: CONTENT_AUDIT_FAIL_ON_P1,
    });
    persistSource();
    let paths = {};
    try {
      paths = browserDriver.writeStrictEvidence({
        root: ROOT,
        pythonExe: pythonExe(),
        rawPath,
        outputDir: OUT_DIR,
        name: STAMP,
      });
    } catch (error) {
      issue("P0", "strict evidence writer failed", { error: String(error).slice(0, 1000) });
      acceptanceReport.updateIssueCounts(summary, issues);
      summary.result = "failed_or_partial";
      persistSource();
    }
    console.log(JSON.stringify({ summary, issues, paths, source: rawPath }, null, 2));
    if (browser) {
      await browser.close();
    }
    if (acceptanceDecision.acceptanceFailed({
      result: summary.result,
      issues,
      contentAuditFailOnP1: CONTENT_AUDIT_FAIL_ON_P1,
    })) {
      process.exitCode = 1;
    }
  }
})();
}
