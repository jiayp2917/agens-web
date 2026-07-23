"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { cleanText } = require("./playtest_utils.cjs");
const {
  annotateVisibleSnapshot,
  canBreakthroughFromRealmText,
  hasBreakthroughIntent,
} = require("./visible_content_audit.cjs");

function parseViewport(raw) {
  const match = /^(\d{3,4})x(\d{3,4})$/u.exec(String(raw || "").trim());
  if (!match) throw new Error(`Invalid AGENS_PLAYTEST_VIEWPORT: ${raw}`);
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (width < 320 || width > 3840 || height < 480 || height > 2160) {
    throw new Error(`Unsupported AGENS_PLAYTEST_VIEWPORT: ${raw}`);
  }
  return { width, height };
}

function parseSlotSequence(raw) {
  const normalized = String(raw || "").replace(/[\s,]/gu, "").toUpperCase();
  if (!normalized) return "";
  if (!/^[ABCD]+$/u.test(normalized)) {
    throw new Error("AGENS_PLAYTEST_SLOT_SEQUENCE must contain only A/B/C/D");
  }
  return normalized;
}

function loadPlaywright(environment = process.env) {
  try {
    return require("playwright");
  } catch {
    // Continue with explicit path lookup.
  }
  const candidates = [];
  if (environment.AGENS_PLAYWRIGHT_NODE_MODULES) {
    candidates.push(environment.AGENS_PLAYWRIGHT_NODE_MODULES);
  }
  for (const entry of String(environment.PATH || "").split(path.delimiter)) {
    if (entry.endsWith(`${path.sep}node_modules${path.sep}.bin`)) {
      candidates.push(path.dirname(entry));
    }
  }
  for (const root of [
    path.join(environment.LOCALAPPDATA || "", "npm-cache", "_npx"),
    path.join(environment.APPDATA || "", "npm-cache", "_npx"),
    path.join(environment.USERPROFILE || "", "AppData", "Local", "npm-cache", "_npx"),
    path.join("D:", "UserData", "dev-cache", "npm", "_npx"),
  ]) {
    if (!root || !fs.existsSync(root)) continue;
    for (const item of fs.readdirSync(root)) candidates.push(path.join(root, item, "node_modules"));
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

function chromeExecutablePath(environment = process.env) {
  const explicit = environment.AGENS_CHROME_PATH;
  const candidates = [
    explicit,
    path.join(environment.PROGRAMFILES || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(environment["PROGRAMFILES(X86)"] || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(environment.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe"),
    path.join(environment.PROGRAMFILES || "", "Microsoft", "Edge", "Application", "msedge.exe"),
    path.join(environment["PROGRAMFILES(X86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe"),
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function routeIndexForTurn(turn, choices, snapshot, { choiceStrategy = "cycle", slotSequence = "" } = {}) {
  const enabled = choices.filter((choice) => !choice.disabled);
  const fallback = enabled[(turn - 1) % Math.max(1, enabled.length)];
  const canonicalSlot = slotSequence[turn - 1];
  if (canonicalSlot) {
    return enabled.find((choice) => String(choice.letter || "").toUpperCase() === canonicalSlot) || fallback;
  }
  const normalized = String(choiceStrategy || "cycle").toLowerCase().replace(/[^a-z0-9_-]/g, "");
  const fixedMatch = normalized.match(/^fixed-?([abcd])$/);
  if (fixedMatch) {
    const wanted = fixedMatch[1].toUpperCase();
    return enabled.find((choice) => String(choice.letter || "").toUpperCase() === wanted) || fallback;
  }
  if (["a", "b", "c", "d"].includes(normalized)) {
    const wanted = normalized.toUpperCase();
    return enabled.find((choice) => String(choice.letter || "").toUpperCase() === wanted) || fallback;
  }
  if (normalized === "golden") {
    const breakthrough = canBreakthroughFromRealmText(snapshot?.status?.realm || "")
      ? enabled.find((choice) => hasBreakthroughIntent(choice.text))
      : null;
    return breakthrough
      || enabled.find((choice) => String(choice.letter || "").toUpperCase() === "A")
      || fallback;
  }
  if (normalized === "mixed" || normalized === "player") {
    return chooseMixedChoice(turn, enabled, snapshot) || fallback;
  }
  return fallback;
}

async function configureGoldenProfile(page) {
  const attributes = {
    willpower: 3,
    physique: 3,
    soul: 3,
    root_bone: 7,
    comprehension: 7,
    luck: 7,
  };
  for (const [name, value] of Object.entries(attributes)) {
    const input = page.locator(`input[name="${name}"]`);
    await input.focus();
    await input.press("Home");
    for (let current = 2; current < value; current += 1) await input.press("ArrowRight");
  }
  const actual = await page.locator('.attribute-panel input[type="range"]').evaluateAll((inputs) =>
    Object.fromEntries(inputs.map((input) => [input.name, Number(input.value)])),
  );
  if (Object.entries(attributes).some(([name, value]) => actual[name] !== value)) {
    throw new Error(`Golden profile attributes were not applied: ${JSON.stringify(actual)}`);
  }
}

function chooseMixedChoice(turn, enabled, snapshot) {
  const realm = snapshot?.status?.realm || "";
  const lifespan = snapshot?.status?.lifespan || "";
  const lowLifespan = /(?:^|[^\d])(?:[0-9]|1[0-5])\/\d+/.test(lifespan);
  const breakthrough = canBreakthroughFromRealmText(realm)
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
      if (aria && (!text || aria.length > text.length)) text = aria;
      const letter = String(mark || String.fromCharCode(65 + index)).trim().slice(0, 1);
      text = text
        .replace(new RegExp(`^${letter}\\s*[.:：、)）-]?\\s*`), "")
        .replace(/^[A-Da-d1-4]\s*[.:：、)）-]?\s*/, "")
        .trim();
      return { index, letter, text, aria, disabled: Boolean(button.disabled) };
    }),
  );
}

async function uiSnapshot(page, label) {
  const snapshot = await page.evaluate((snapshotLabel) => {
    const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const textOf = (selector) => clean(document.querySelector(selector)?.textContent || "");
    const boundsOf = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return {
        left: Math.round(rect.left), top: Math.round(rect.top), right: Math.round(rect.right), bottom: Math.round(rect.bottom),
        width: Math.round(rect.width), height: Math.round(rect.height),
        within_viewport: rect.left >= -1 && rect.top >= -1 && rect.right <= window.innerWidth + 1 && rect.bottom <= window.innerHeight + 1,
      };
    };
    const fullPageText = clean(document.body?.innerText || "");
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
    const documentWidth = document.documentElement?.scrollWidth || 0;
    const bodyWidth = document.body?.scrollWidth || 0;
    return {
      label: snapshotLabel,
      captured_at: new Date().toISOString(),
      status: {
        name: textOf(".status-panel h2"), age: statValue("年龄"), realm: statValue("境界"), lifespan: textOf(".lifespan-bar strong"),
        talent: textOf(".character-meta dd:nth-of-type(1)"), spirit_root: textOf(".character-meta dd:nth-of-type(2)"),
        family_background: textOf(".character-meta dd:nth-of-type(3)"), luck: textOf(".character-meta dd:nth-of-type(4)"),
      },
      heading: textOf(".chronicle-heading > span"),
      world_intel: Array.from(document.querySelectorAll(".world-intel li")).map((item) => clean(item.textContent || "")),
      chronicle,
      latest_chronicle: chronicle.filter((item) => item.latest),
      choices,
      fallback_banner: textOf(".fallback"),
      viewport: {
        inner_width: window.innerWidth, inner_height: window.innerHeight, document_scroll_width: documentWidth, body_scroll_width: bodyWidth,
        horizontal_overflow: Math.max(documentWidth, bodyWidth) > window.innerWidth + 1,
      },
      element_bounds: { game_shell: boundsOf(".game-shell"), dialog: boundsOf(".settings-dialog"), toast: boundsOf(".toast") },
      full_page_text: fullPageText,
      body_issue_text: [
        fullPageText,
        ...chronicle.map((item) => item.text),
        ...Array.from(document.querySelectorAll(".world-intel li")).map((item) => clean(item.textContent || "")),
        ...choices.map((item) => item.text),
        textOf(".fallback"),
      ].filter(Boolean).join("\n"),
    };
  }, label);
  return annotateVisibleSnapshot(snapshot);
}

async function firstVisible(page, selectors, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    for (const selector of selectors) {
      const locator = page.locator(selector).first();
      try {
        if ((await locator.count()) > 0 && (await locator.isVisible())) return locator;
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

async function runSaveLoadProbe(page, { summary, issue, screenshotBase, label, contentAudit, refreshProbe }) {
  if (summary.save_load_passed) return;
  await page.locator('button.icon-btn[aria-label="存档"]').click();
  await page.waitForSelector(".settings-dialog", { timeout: 30000 });
  await page.waitForTimeout(300);
  if (contentAudit) {
    summary.save_dialog_ui_snapshot = await uiSnapshot(page, `${label}-save-dialog-open`);
    const dialogSnapshot = summary.save_dialog_ui_snapshot;
    if (dialogSnapshot.viewport?.horizontal_overflow || dialogSnapshot.element_bounds?.dialog?.within_viewport === false) {
      issue("P1", "save dialog does not fit the configured viewport", {
        viewport: dialogSnapshot.viewport,
        dialog_bounds: dialogSnapshot.element_bounds?.dialog,
      });
    }
    await page.screenshot({ path: `${screenshotBase}-${label}-save-dialog.png`, fullPage: true });
  }
  await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:last-child"], 30000);
  await page.waitForTimeout(1000);
  await clickFirstVisible(page, [".save-row:nth-child(1) .save-row-actions button:first-child"], 30000);
  await page.waitForSelector(".choice-button", { timeout: 30000 });
  await page.screenshot({ path: `${screenshotBase}-${label}-save-load.png`, fullPage: true });
  summary.save_load_passed = true;
  summary.save_load_probe_label = label;
  if (contentAudit) {
    summary.save_load_ui_snapshot = await uiSnapshot(page, `${label}-save-load-after`);
    if (summary.save_load_ui_snapshot.viewport?.horizontal_overflow) {
      issue("P1", "page has horizontal overflow after save/load", { viewport: summary.save_load_ui_snapshot.viewport });
    }
  }
  if (refreshProbe) {
    try {
      await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForSelector(".choice-button", { timeout: 10000 });
      summary.refresh_probe_passed = true;
      if (contentAudit) summary.refresh_probe_ui_snapshot = await uiSnapshot(page, `${label}-refresh-after`);
    } catch (error) {
      summary.refresh_probe_passed = false;
      issue("P1", "refresh probe did not restore visible game choices", { error: String(error).slice(0, 500) });
    }
    await page.screenshot({ path: `${screenshotBase}-${label}-refresh.png`, fullPage: true });
  }
}

function redactedUrl(url) {
  return String(url || "").replace(/sessions\/[^/]+/g, "sessions/<id>");
}

async function routeApiBase(page, { apiBaseUrl = "", conflictState = null } = {}) {
  if (!apiBaseUrl && !conflictState) return;
  const apiBase = apiBaseUrl.replace(/\/+$/, "");
  await page.route("**/*", (route) => {
    const request = route.request();
    const requestUrl = new URL(request.url());
    const options = {};
    if (conflictState?.armed && request.method() === "POST" && /\/api\/sessions\/[^/]+\/choice$/u.test(requestUrl.pathname)) {
      try {
        const payload = JSON.parse(request.postData() || "{}");
        payload.expected_version = Math.max(0, Number(payload.expected_version || 0) - 1);
        options.postData = JSON.stringify(payload);
        conflictState.armed = false;
        conflictState.triggered = true;
      } catch (error) {
        conflictState.armed = false;
        conflictState.error = String(error);
      }
    }
    if (!requestUrl.pathname.startsWith("/api/")) {
      route.continue(options);
      return;
    }
    if (apiBaseUrl) options.url = `${apiBase}${requestUrl.pathname}${requestUrl.search}`;
    route.continue(options);
  });
}

function ensureInvite({ root, pythonExe, inviteCode, environment = process.env }) {
  const py = `
import os
from web.backend.auth import hash_invite_code
from web.backend.database import create_database

code = os.environ["AGENS_PLAYTEST_INVITE_CODE"]
db = create_database()
try:
    db.create_invite_code(hash_invite_code(code), max_uses=1)
except Exception:
    pass
print("ok")
`;
  const result = spawnSync(pythonExe, ["-c", py], {
    cwd: root,
    env: { ...environment, AGENS_PLAYTEST_INVITE_CODE: inviteCode },
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`Failed to seed local invite: ${(result.stderr || result.stdout || "").trim()}`);
  }
}

function writeStrictEvidence({ root, pythonExe, rawPath, outputDir, name }) {
  const result = spawnSync(
    pythonExe,
    ["scripts/playwright_evidence.py", "--input", rawPath, "--output-dir", outputDir, "--name", name],
    { cwd: root, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(`Failed to write strict evidence: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return JSON.parse(result.stdout);
}

module.exports = {
  chromeExecutablePath,
  choiceSnapshots,
  cleanText,
  clickFirstVisible,
  configureGoldenProfile,
  ensureInvite,
  firstVisible,
  loadPlaywright,
  parseSlotSequence,
  parseViewport,
  redactedUrl,
  routeApiBase,
  routeIndexForTurn,
  runSaveLoadProbe,
  uiSnapshot,
  writeStrictEvidence,
};
