"use strict";

const { numberMetric } = require("./playtest_utils.cjs");

function createAcceptanceSummary({
  targetTurns,
  contentAudit,
  contentAuditFailOnP1,
  choiceStrategy,
  postLoadTurns,
  saveLoadTurn,
  refreshProbe,
  doubleClickProbe,
  conflictProbe,
  requireFinale,
  requireLiveOpening,
  viewport,
  evidenceContext,
  requestTimeoutMs,
}) {
  return {
    scenario: contentAudit ? "local visible Chrome content-audit playtest" : "local visible Chrome 20-turn playtest",
    target_turns: targetTurns,
    content_audit: contentAudit,
    content_audit_fail_on_p1: contentAuditFailOnP1,
    choice_strategy: choiceStrategy,
    post_load_turns: postLoadTurns,
    save_load_turn: saveLoadTurn,
    refresh_probe: refreshProbe,
    double_click_probe: doubleClickProbe,
    conflict_probe: conflictProbe,
    require_finale: requireFinale,
    require_live_opening: requireLiveOpening,
    viewport,
    evidence_context: evidenceContext,
    started_at: new Date().toISOString(),
    username_set: true,
    invite_seeded: false,
    registration_passed: false,
    start_passed: false,
    golden_profile_configured: false,
    save_load_passed: false,
    request_timeout_ms: requestTimeoutMs,
    result: "running",
  };
}

function createIssueCollector(issues) {
  return function issue(level, text, data = {}) {
    const record = { ...(data || {}) };
    if (Object.prototype.hasOwnProperty.call(record, "text")) {
      record.visible_text = record.text;
      delete record.text;
    }
    delete record.level;
    issues.push({ ...record, level, text });
  };
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
    if (agent) latestByAgent[agent] = event;
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
    retried_after_request_failed: Boolean(narratorDiag.retried_after_request_failed),
    retried_after_incomplete_output: Boolean(narratorDiag.retried_after_incomplete_output),
    narrator_incomplete_output: narratorStatus === "incomplete_output",
    contract_recovery: narratorStatus === "incomplete_output",
    contract_missing_narrative: Boolean(narratorDiag.contract_missing_narrative),
    contract_missing_state_update: Boolean(narratorDiag.contract_missing_state_update),
    contract_choices_count_ok: Boolean(narratorDiag.contract_choices_count_ok),
    contract_raw_has_state_update_tag: Boolean(narratorDiag.contract_raw_has_state_update_tag),
    contract_raw_has_choices_tag: Boolean(narratorDiag.contract_raw_has_choices_tag),
    provider_json_schema: Boolean(narratorDiag.provider_json_schema),
    provider_json_envelope_ok: Boolean(narratorDiag.provider_json_envelope_ok),
    prompt_chars: numberMetric(narratorDiag.prompt_chars),
    game_state_chars: numberMetric(narratorDiag.game_state_chars),
    history_count: numberMetric(narratorDiag.history_count),
    prompt_tokens: numberMetric(narratorDiag.prompt_tokens),
    completion_tokens: numberMetric(narratorDiag.completion_tokens),
    total_tokens: numberMetric(narratorDiag.total_tokens),
  };
}

function startAcceptance(body, httpStatus, cleanText) {
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

function auditModelDiagnostics(turnRecord, phase, issue) {
  if (turnRecord.narrator_incomplete_output) {
    issue("P1", "narrator output required local contract recovery", {
      turn_index: turnRecord.turn_index,
      phase,
      narrator_status: turnRecord.narrator_status,
      missing_narrative: turnRecord.contract_missing_narrative,
      missing_state_update: turnRecord.contract_missing_state_update,
      choices_count_ok: turnRecord.contract_choices_count_ok,
      raw_has_state_update_tag: turnRecord.contract_raw_has_state_update_tag,
      raw_has_choices_tag: turnRecord.contract_raw_has_choices_tag,
    });
  }
  if (turnRecord.provider_json_schema && !turnRecord.provider_json_envelope_ok) {
    issue("P1", "provider JSON schema envelope was not accepted", {
      turn_index: turnRecord.turn_index,
      phase,
    });
  }
  if (turnRecord.judge_request_failed) {
    issue("P1", "judge model request failed; rule-only settlement used", {
      turn_index: turnRecord.turn_index,
      phase,
      judge_status: turnRecord.judge_status,
    });
  }
}

function percentile(values, ratio) {
  const sorted = values
    .map((value) => Number(value || 0))
    .filter((value) => Number.isFinite(value) && value >= 0)
    .sort((left, right) => left - right);
  if (!sorted.length) return 0;
  const rank = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1));
  return Math.round(sorted[rank]);
}

function avgMetric(rows, key) {
  const values = rows.map((row) => Number(row[key] || 0)).filter((value) => value > 0);
  if (!values.length) return 0;
  return Math.round(values.reduce((total, value) => total + value, 0) / values.length);
}

function updateSummaryFromTurns(summary, turns, auditState) {
  summary.turns_completed = turns.length;
  summary.accepted_live_turns = turns.filter((turn) => (
    turn.http_status >= 200
    && turn.http_status < 300
    && !turn.fallback
    && !turn.contract_recovery
    && turn.narrator_status === "ok"
    && (!turn.provider_json_schema || turn.provider_json_envelope_ok)
  )).length;
  summary.fallback_count = turns.filter((turn) => turn.fallback).length;
  summary.max_elapsed_ms = Math.max(0, ...turns.map((turn) => turn.elapsed_ms || 0));
  summary.avg_elapsed_ms = turns.length
    ? Math.round(turns.reduce((total, turn) => total + (turn.elapsed_ms || 0), 0) / turns.length)
    : 0;
  summary.p50_elapsed_ms = percentile(turns.map((turn) => turn.elapsed_ms), 0.5);
  summary.p95_elapsed_ms = percentile(turns.map((turn) => turn.elapsed_ms), 0.95);
  summary.repair_attempt_count = turns.filter((turn) => (turn.repair_elapsed_ms || 0) > 0).length;
  summary.repaired_output_count = turns.filter((turn) => turn.repaired_output).length;
  summary.incomplete_retry_count = turns.filter((turn) => turn.retried_after_incomplete_output).length;
  summary.narrator_incomplete_output_count = turns.filter((turn) => turn.narrator_incomplete_output).length;
  summary.contract_recovery_count = turns.filter((turn) => turn.contract_recovery).length;
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

function updateIssueCounts(summary, issues) {
  summary.p0_issues = issues.filter((item) => item.level === "P0").length;
  summary.p1_issues = issues.filter((item) => item.level === "P1").length;
}

function applyPersistedTurnAudit(summary, persisted, issue) {
  summary.persisted_turn_audit = persisted;
  if (!persisted.continuous || persisted.turn_count !== Number(summary.last_turn_count || 0)) {
    issue("P0", "persisted game turns were not continuous", {
      turn_count: persisted.turn_count,
      last_turn: persisted.last_turn,
      continuous: persisted.continuous,
      browser_turn_count: Number(summary.last_turn_count || 0),
    });
  }
  if (persisted.authority_match !== true) {
    issue("P0", "persisted authority hashes were not verified against the rule trajectory", {
      mismatch_count: persisted.authority_mismatch_count,
      replay_source: persisted.authority_replay_source || "",
    });
  }
  if (persisted.duplicate_narrative_count > 0) {
    issue("P1", "persisted chronicle text repeated exactly", {
      duplicate_count: persisted.duplicate_narrative_count,
      duplicates: persisted.duplicates,
    });
  }
}

module.exports = {
  applyPersistedTurnAudit,
  auditModelDiagnostics,
  createAcceptanceSummary,
  createIssueCollector,
  latestModelDiagnostics,
  startAcceptance,
  updateIssueCounts,
  updateSummaryFromTurns,
};
