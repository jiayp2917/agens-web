"use strict";

const {
  cleanText,
  normalizeForCompare,
  parseAge,
  textSimilarity,
  unique,
} = require("./playtest_utils.cjs");

const GENERIC_CHOICE_PATTERNS = [
  /(?:稳妥|机遇|风险|气运)路径的具体行动/u,
  /^具体行动$/u,
];

const FORBIDDEN_VISIBLE_PATTERNS = [
  ["history_suppression_notice", /此事未入正史/u],
  ["choice_completion_notice", /补齐下一步选择/u],
  ["internal_delta_notice", /模型状态变更未采用/u],
  ["model_contract_returned", /模型已返回/u],
  ["model_output_notice", /模型输出/u],
  ["state_update_format_notice", /状态更新格式不完整/u],
  ["missing_narrative_notice", /缺少叙事正文/u],
  ["missing_abcd_notice", /未返回可用\s*A\/B\/C\/D|未返回恰好\s*4\s*项\s*A\/B\/C\/D/u],
  ["model_unavailable_notice", /模型(?:暂)?不可用/u],
  ["local_story_notice", /(?:本地故事继续|转入本地故事|本局已转入本地故事)/u],
  ["heaven_disorder_notice", /天道紊乱/u],
  ["upstream_model_notice", /上游模型/u],
  ["basic_rule_settlement_notice", /基础规则结算/u],
  ["breakthrough_probability_notice", /突破概率\s*[:：]|开始突破/u],
  ["internal_realm_status", /境界\s*[:：].*破境准备/u],
  ["fallback_word", /\bfallback\b/iu],
  ["mismatch_word", /\bmismatch\b/iu],
  ["state_update_tag", /<\/?state_update\b|<state_update>/iu],
  ["choices_tag", /<\/?choices\b|<choices>/iu],
  ["json_fence", /```(?:json)?/iu],
  ["json_like_object", /(?:^|[\s，：])\{[^{}]*(?:state_delta|state_update|character|world|meta|choices)[^{}]*\}/iu],
  ["json_like_array", /(?:^|[\s，：])\[(?=[^\]]*(?:"|'))[^\]]+\]/u],
  ["quoted_choice_fragment", /(?:\\?["“][^"“”\n]{4,160}\\?["”]\s*[,，、]\s*){2,}\\?["“][^"“”\n]{4,160}\\?["”]/u],
  ["english_status_word", /\b(?:prowess|inventory|lifespan|realm|delta|narrative|turn_count|game_turns)\b/iu],
  ["english_word", /\b(?!jiayp\b)[A-Za-z]{2,}(?:_[A-Za-z0-9]+)?\b/iu],
];

function forbiddenHits(text) {
  const body = String(text || "");
  if (!body.trim()) return [];
  const hits = [];
  for (const [name, pattern] of FORBIDDEN_VISIBLE_PATTERNS) {
    if (pattern.test(body)) hits.push(name);
  }
  return hits;
}

function canBreakthroughFromRealmText(realmText) {
  const text = String(realmText || "");
  if (/[练炼]气\s*(?:第)?(?:9|九)\s*层/u.test(text)) return true;
  return /圆满/u.test(text);
}

function normalizedRealmLabel(value) {
  const digits = { 一: "1", 二: "2", 三: "3", 四: "4", 五: "5", 六: "6", 七: "7", 八: "8", 九: "9" };
  return String(value || "")
    .replace(/\s+/g, "")
    .replace(/第(?=[1-9一二三四五六七八九]层)/g, "")
    .replace(/[一二三四五六七八九]/g, (char) => digits[char] || char)
    .replace(/^(筑基|金丹|元婴|化神|合体|大乘|渡劫)期$/u, "$1");
}

function realmClaimMatchesCurrent(claim, currentRealm) {
  if (claim === currentRealm) return true;
  const currentBase = String(currentRealm || "").match(/^(筑基|金丹|元婴|化神|合体|大乘|渡劫)/u)?.[1] || "";
  return Boolean(currentBase && claim === currentBase);
}

function narrativeRealmClaims(text) {
  const source = String(text || "");
  const claims = [];
  for (const segment of source.split(/[。！？；\n]/u)) {
    const matches = segment.match(/[练炼]气\s*(?:第)?\s*[1-9一二三四五六七八九]\s*层|(?:筑基|金丹|元婴|化神|合体|大乘|渡劫)\s*(?:初期|中期|后期|圆满|期)/gu) || [];
    if (!matches.length) continue;
    const playerProgress = /突破至|突破到|踏入|晋入|晋升|修至|升至|跌落至|跌至|降至|迈入|进入/u.test(segment);
    const playerSubject = /(?:^|[，,\s])(?:其人|其|他|她|玩家|验真者)(?:已|仍|尚|的|修为|境界|根基|(?=[练炼]气|筑基|金丹|元婴|化神|合体|大乘|渡劫))/u.test(segment);
    if (!playerProgress && !playerSubject) continue;
    claims.push(...matches.map((match) => normalizedRealmLabel(match).replace(/^炼气/u, "练气")));
  }
  return unique(claims);
}

function hasBreakthroughIntent(text) {
  const body = String(text || "");
  if (/[练炼]气\s*(?:第)?(?:[1-9]|[一二三四五六七八九])\s*层/u.test(body)
      && !/突破|破境|筑基|金丹|元婴|化神|合体|大乘|渡劫|飞升/u.test(body)) {
    return false;
  }
  if (/所需|准备|底蕴|线索|打听|寻找|静候|机缘/u.test(body) && !/尝试|正式|强行|开始/u.test(body)) {
    return false;
  }
  return /突破|破境|冲关/u.test(body)
    || /冲击\s*(?:筑基|金丹|元婴|化神|合体|大乘|渡劫|飞升)/u.test(body)
    || /(?:尝试|正式|强行|开始|立即|直接)\s*(?:渡劫|飞升)/u.test(body);
}

function genericChoiceTexts(choices) {
  return (Array.isArray(choices) ? choices : [])
    .map((choice) => cleanText(typeof choice === "string" ? choice : choice?.text))
    .filter((text) => text && GENERIC_CHOICE_PATTERNS.some((pattern) => pattern.test(text)));
}

function chronicleSignature(item) {
  return [
    cleanText(item?.age || ""),
    cleanText(item?.text || ""),
  ].join("|");
}

function newChronicleEntries(beforeSnapshot, afterSnapshot) {
  const before = Array.isArray(beforeSnapshot?.chronicle) ? beforeSnapshot.chronicle : [];
  const after = Array.isArray(afterSnapshot?.chronicle) ? afterSnapshot.chronicle : [];
  if (after.length > before.length) return after.slice(before.length);
  const beforeSignatures = new Set(before.map((item) => chronicleSignature(item)));
  const added = after.filter((item) => !beforeSignatures.has(chronicleSignature(item)));
  if (added.length) return added;
  return after.filter((item) => item.latest && !beforeSignatures.has(chronicleSignature(item)));
}

function createVisibleAuditState() {
  return {
    seenChronicle: new Map(),
    lastChronicleText: "",
    lastWorldIntelKey: "",
    lastWorldIntelChangeTurn: 0,
    worldIntelChangeCount: 0,
  };
}

function annotateVisibleSnapshot(snapshot) {
  snapshot.forbidden_hits = unique(forbiddenHits(snapshot.body_issue_text));
  snapshot.latest_age_value = parseAge(snapshot.latest_chronicle?.at(-1)?.age || "");
  snapshot.status_age_value = parseAge(snapshot.status?.age || "");
  return snapshot;
}

function auditVisibleContent({
  enabled = true,
  allowModelUnavailableNotice = false,
  turnRecord,
  beforeSnapshot,
  afterSnapshot,
  auditState,
  issue,
}) {
  if (!enabled || !afterSnapshot) return;
  const forbidden = unique([
    ...(beforeSnapshot?.forbidden_hits || []),
    ...(afterSnapshot?.forbidden_hits || []),
  ]).filter((hit) => !(allowModelUnavailableNotice && hit === "model_unavailable_notice"));
  turnRecord.forbidden_hits = forbidden;
  turnRecord.forbidden_count = forbidden.length;
  turnRecord.horizontal_overflow = Boolean(afterSnapshot.viewport?.horizontal_overflow);
  const terminalTurn = Boolean(turnRecord.game_over || turnRecord.finale);
  if (turnRecord.horizontal_overflow) {
    issue("P1", "page has horizontal overflow at the configured viewport", {
      turn_index: turnRecord.turn_index,
      phase: turnRecord.phase || "main",
      viewport: afterSnapshot.viewport,
    });
  }
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

  const currentRealm = normalizedRealmLabel(turnRecord.status_realm);
  for (const entry of newEntries) {
    const realmClaims = narrativeRealmClaims(entry.text);
    if (realmClaims.length && currentRealm && !realmClaims.some((claim) => realmClaimMatchesCurrent(claim, currentRealm))) {
      issue("P1", "chronicle realm claim contradicts authoritative status", {
        turn_index: turnRecord.turn_index,
        phase: turnRecord.phase || "main",
        realm: turnRecord.status_realm,
        claims: realmClaims,
        text: entry.text,
      });
    }
  }

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
  const realmChanged = normalizedRealmLabel(beforeSnapshot?.status?.realm || "") !== normalizedRealmLabel(afterSnapshot.status?.realm || "");
  const majorStageFeedback = realmChanged || hasBreakthroughIntent(turnRecord.choice) || terminalTurn;
  if (intelKey && intelKey !== auditState.lastWorldIntelKey) {
    auditState.lastWorldIntelKey = intelKey;
    auditState.lastWorldIntelChangeTurn = turnRecord.turn_index;
    auditState.worldIntelChangeCount += 1;
    turnRecord.world_intel_changed = true;
  } else {
    turnRecord.world_intel_changed = false;
  }
  if (majorStageFeedback) {
    auditState.lastWorldIntelChangeTurn = turnRecord.turn_index;
    turnRecord.stage_feedback_reason = realmChanged ? "realm_changed" : (terminalTurn ? "terminal" : "breakthrough");
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

module.exports = {
  FORBIDDEN_VISIBLE_PATTERNS,
  annotateVisibleSnapshot,
  auditVisibleContent,
  canBreakthroughFromRealmText,
  createVisibleAuditState,
  forbiddenHits,
  genericChoiceTexts,
  hasBreakthroughIntent,
  narrativeRealmClaims,
  newChronicleEntries,
  normalizedRealmLabel,
  realmClaimMatchesCurrent,
};
