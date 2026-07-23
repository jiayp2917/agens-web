#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { acceptanceFailed, evaluateAcceptance } = require("./acceptance_decision.cjs");
const {
  applyPersistedTurnAudit,
  createIssueCollector,
  updateIssueCounts,
  updateSummaryFromTurns,
} = require("./acceptance_report.cjs");
const { auditVisibleContent, createVisibleAuditState } = require("./visible_content_audit.cjs");

function replayCase(replay) {
  const summary = { ...(replay.summary || {}) };
  const issues = [...(replay.issues || [])];
  const issue = createIssueCollector(issues);
  const auditState = createVisibleAuditState();
  const turns = [];
  for (const turn of replay.visible_turns || []) {
    const turnRecord = { ...(turn.turn_record || {}) };
    auditVisibleContent({
      enabled: true,
      turnRecord,
      beforeSnapshot: turn.before_snapshot || {},
      afterSnapshot: turn.after_snapshot || {},
      auditState,
      issue,
    });
    turns.push(turnRecord);
  }
  if (turns.length) updateSummaryFromTurns(summary, turns, auditState);
  if (replay.persisted_turn_audit) {
    applyPersistedTurnAudit(summary, replay.persisted_turn_audit, issue);
  }
  updateIssueCounts(summary, issues);
  summary.result = evaluateAcceptance({
    result: summary.result,
    issues,
    contentAuditFailOnP1: Boolean(replay.content_audit_fail_on_p1),
  });
  return {
    name: replay.name,
    result: summary.result,
    p0_issues: summary.p0_issues,
    p1_issues: summary.p1_issues,
    fallback_count: summary.fallback_count || 0,
    failed: acceptanceFailed({
      result: summary.result,
      issues,
      contentAuditFailOnP1: Boolean(replay.content_audit_fail_on_p1),
    }),
  };
}

function replayFile(filePath) {
  const payload = JSON.parse(fs.readFileSync(filePath, "utf8"));
  const cases = Array.isArray(payload) ? payload : payload.cases || [];
  return cases.map(replayCase);
}

function main(argv = process.argv) {
  const input = argv[2];
  if (!input) throw new Error("usage: replay_acceptance.cjs <fixture.json>");
  console.log(JSON.stringify(replayFile(path.resolve(input)), null, 2));
  return 0;
}

module.exports = { replayCase, replayFile };

if (require.main === module) {
  process.exitCode = main();
}
