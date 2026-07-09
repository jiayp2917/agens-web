#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "output", "playwright");
const STAMP = process.env.AGENS_CONTENT_AUDIT_NAME || `local-content-audit-${stamp()}`;

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function selectedRuns() {
  const raw = process.env.AGENS_CONTENT_AUDIT_RUNS || "base,routes,mixed,anomaly";
  return new Set(raw.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean));
}

function buildRuns() {
  const selected = selectedRuns();
  const runs = [];
  if (selected.has("base")) {
    runs.push({
      key: "base-cycle-20",
      turns: 20,
      strategy: "cycle",
      postLoadTurns: 3,
      refreshProbe: true,
    });
  }
  if (selected.has("routes")) {
    for (const [key, strategy] of [
      ["route-a-20", "fixed-a"],
      ["route-b-20", "fixed-b"],
      ["route-c-20", "fixed-c"],
      ["route-d-20", "fixed-d"],
    ]) {
      runs.push({ key, turns: 20, strategy, postLoadTurns: 0, refreshProbe: false });
    }
  }
  if (selected.has("mixed")) {
    runs.push({
      key: "mixed-player-60",
      turns: Number(process.env.AGENS_CONTENT_AUDIT_MIXED_TURNS || "60"),
      strategy: "mixed",
      postLoadTurns: 3,
      refreshProbe: true,
    });
  }
  if (selected.has("anomaly")) {
    runs.push({
      key: "double-click-1",
      turns: 1,
      strategy: "cycle",
      postLoadTurns: 0,
      refreshProbe: false,
      doubleClickProbe: true,
    });
  }
  return runs;
}

function parseChildOutput(stdout) {
  const text = String(stdout || "").trim();
  if (!text) return {};
  try {
    return JSON.parse(text.slice(text.indexOf("{")));
  } catch {
    return { raw_stdout_tail: text.slice(-2000) };
  }
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const batch = {
  name: STAMP,
  started_at: new Date().toISOString(),
  result: "running",
  stop_reason: "",
  p0_issues: 0,
  p1_issues: 0,
  runs: [],
};

for (const run of buildRuns()) {
  const runName = `${STAMP}-${run.key}`;
  console.log(`\n=== ${runName} ===`);
  const child = spawnSync(process.execPath, ["scripts/local_visible_playtest.cjs"], {
    cwd: ROOT,
    env: {
      ...process.env,
      AGENS_PLAYTEST_NAME: runName,
      AGENS_PLAYTEST_CONTENT_AUDIT: "1",
      AGENS_PLAYTEST_TURNS: String(run.turns),
      AGENS_PLAYTEST_CHOICE_STRATEGY: run.strategy,
      AGENS_PLAYTEST_POST_LOAD_TURNS: String(run.postLoadTurns || 0),
      AGENS_PLAYTEST_REFRESH_PROBE: run.refreshProbe ? "1" : "0",
      AGENS_PLAYTEST_DOUBLE_CLICK_PROBE: run.doubleClickProbe ? "1" : "0",
    },
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 64,
  });
  if (child.stderr) console.error(child.stderr.trim());
  const parsed = parseChildOutput(child.stdout);
  const issues = parsed.issues || [];
  const p0Issues = issues.filter((item) => item.level === "P0").length;
  const p1Issues = issues.filter((item) => item.level === "P1").length;
  console.log(JSON.stringify({
    key: run.key,
    status: child.status,
    result: parsed.summary?.result || "",
    turns_completed: parsed.summary?.turns_completed || 0,
    accepted_live_turns: parsed.summary?.accepted_live_turns || 0,
    fallback_count: parsed.summary?.fallback_count || 0,
    visible_forbidden_turns: parsed.summary?.visible_forbidden_turns || 0,
    repeated_exact_turns: parsed.summary?.repeated_exact_turns || 0,
    max_previous_similarity: parsed.summary?.max_previous_similarity || 0,
    p0_issues: p0Issues,
    p1_issues: p1Issues,
    paths: parsed.paths || {},
  }, null, 2));
  batch.p0_issues += p0Issues;
  batch.p1_issues += p1Issues;
  batch.runs.push({
    key: run.key,
    name: runName,
    status: child.status,
    signal: child.signal,
    summary: parsed.summary || {},
    issues,
    paths: parsed.paths || {},
    source: parsed.source || "",
  });
  const p1OnlyFailure = child.status !== 0 && p0Issues === 0 && p1Issues > 0;
  if ((child.status !== 0 && !p1OnlyFailure) || p0Issues > 0) {
    batch.result = "stopped";
    batch.stop_reason = `P0 or non-zero exit in ${run.key}`;
    break;
  }
}

if (batch.result === "running") {
  batch.result = batch.p1_issues > 0 ? "completed_with_p1" : "completed";
}
batch.completed_at = new Date().toISOString();
const summaryPath = path.join(OUT_DIR, `${STAMP}-batch-summary.json`);
fs.writeFileSync(summaryPath, JSON.stringify(batch, null, 2) + "\n", "utf8");
console.log(`\nBatch summary: ${summaryPath}`);
if (batch.result !== "completed") {
  process.exitCode = 1;
}
