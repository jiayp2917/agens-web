"use strict";

const { spawnSync } = require("child_process");

function readPersistedOpeningState({ root, pythonExe, sessionId, environment = process.env }) {
  const py = `
import json
import os

from sqlalchemy import text

from web.backend.database import create_database

db = create_database()
with db.engine.connect() as conn:
    row = conn.execute(
        text("SELECT snapshot FROM sessions WHERE id = :session_id"),
        {"session_id": os.environ["AGENS_PLAYTEST_SESSION_ID"]},
    ).mappings().first()

if row is None or not isinstance(row["snapshot"], dict):
    raise ValueError("playtest session has no persisted opening snapshot")

print(json.dumps(row["snapshot"], ensure_ascii=True))
`;
  const result = spawnSync(pythonExe, ["-c", py], {
    cwd: root,
    env: { ...environment, AGENS_PLAYTEST_SESSION_ID: sessionId },
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error(`Failed to read persisted opening state: ${(result.stderr || result.stdout || "").trim()}`);
  }
  const state = JSON.parse(result.stdout);
  if (!state || typeof state !== "object" || Array.isArray(state)) {
    throw new Error("Persisted opening state is not an object");
  }
  return state;
}

function readPersistedTurnAudit({
  root,
  pythonExe,
  sessionId,
  openingState = null,
  environment = process.env,
}) {
  const py = `
import hashlib
import json
import os
import re
import sys

from sqlalchemy import text

from agens_novel.verification.authority import (
    authority_state_hash,
    authority_state_hash_from_persisted_state,
    canonical_authority_trajectory,
)
from agens_novel.verification.scenarios import canonical_v3_scenarios
from agens_novel.engine.choices import fallback_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.session.game_session import GameSession

from web.backend.database import create_database

session_id = os.environ["AGENS_PLAYTEST_SESSION_ID"]
try:
    audit_input = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
except json.JSONDecodeError:
    audit_input = {}
opening_state_input = audit_input.get("opening_state")
if not isinstance(opening_state_input, dict):
    opening_state_input = None
db = create_database()
with db.engine.connect() as conn:
    rows = conn.execute(
        text("""
            SELECT game_turns.turn_no, game_turns.choice_taken, game_turns.narrative
                 , game_turns.state_after, game_turns.choices, game_turns.state_delta
                 , sessions.events
            FROM game_turns
            JOIN game_runs ON game_runs.id = game_turns.run_id
            JOIN sessions ON sessions.id = game_runs.session_id
            WHERE game_runs.session_id = :session_id
            ORDER BY game_turns.turn_no
        """),
        {"session_id": session_id},
    ).mappings().all()

turns = [int(row["turn_no"]) for row in rows]
scenario_key = os.environ.get("AGENS_PLAYTEST_CANONICAL_SCENARIO", "").strip()
story_version = int(os.environ.get("AGENS_PLAYTEST_STORY_VERSION", "3") or 3)
expected_hashes = []
authority_replay_source = ""
if scenario_key:
    scenario = next((item for item in canonical_v3_scenarios() if item.key == scenario_key), None)
    if scenario is None:
        raise ValueError("playtest canonical scenario is not registered")
    expected_hashes = [
        str(item["authority_hash"])
        for item in canonical_authority_trajectory(
            scenario,
            story_version=story_version,
            max_turns=len(rows),
        )
    ]
    authority_replay_source = "canonical_scenario"
elif rows:
    opening_state = opening_state_input
    if opening_state is None:
        events = rows[0]["events"] if isinstance(rows[0]["events"], list) else []
        opening_state = next(
            (
                event.get("state")
                for event in events
                if isinstance(event, dict)
                and event.get("type") == "character_created"
                and isinstance(event.get("state"), dict)
            ),
            None,
        )
    if isinstance(opening_state, dict):
        replay = GameEngine()
        replay.game_session = GameSession.from_save_dict(opening_state)

        def replay_agent(agent_name, _user_input, session, **_kwargs):
            if agent_name == "narrator":
                return {
                    "narrative": "规则回放已结算本回合因果。",
                    "choices": fallback_choices(session),
                    "state_delta": {},
                    "llm_error": "",
                }
            return {"approved": True, "llm_error": ""}

        replay.run_agent = replay_agent
        for row in rows:
            state_delta = row["state_delta"] if isinstance(row["state_delta"], dict) else {}
            meta = state_delta.get("meta") if isinstance(state_delta.get("meta"), dict) else {}
            category = str(meta.get("choice_category") or "")
            if category == "breakthrough":
                replay.attempt_breakthrough()
            else:
                slot = str(meta.get("choice_slot") or row["choice_taken"] or "")[:1].upper()
                if slot not in {"A", "B", "C", "D"}:
                    raise ValueError("persisted turn has no valid choice slot for authority replay")
                replay.handle_action(slot)
            expected_hashes.append(authority_state_hash(replay.game_session))
        authority_replay_source = "recorded_opening"
authority_mismatch_count = 0
if expected_hashes:
    if len(expected_hashes) != len(rows):
        authority_mismatch_count = abs(len(expected_hashes) - len(rows))
    for index, row in enumerate(rows[: len(expected_hashes)]):
        state_after = row["state_after"] if isinstance(row["state_after"], dict) else {}
        if authority_state_hash_from_persisted_state(state_after) != expected_hashes[index]:
            authority_mismatch_count += 1
seen = {}
duplicates = []
for row in rows:
    turn_no = int(row["turn_no"])
    normalized = re.sub(r"\\s+", "", str(row["narrative"] or ""))
    if not normalized:
        continue
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    previous = seen.get(digest)
    if previous is not None:
        duplicates.append({
            "turn_no": turn_no,
            "previous_turn_no": previous,
            "narrative_sha256": digest,
        })
    else:
        seen[digest] = turn_no

accepted_turns = []
for row in rows:
    turn_no = int(row["turn_no"])
    state_delta = row["state_delta"] if isinstance(row["state_delta"], dict) else {}
    meta = state_delta.get("meta") if isinstance(state_delta.get("meta"), dict) else {}
    state_after = row["state_after"] if isinstance(row["state_after"], dict) else {}
    choices = row["choices"] if isinstance(row["choices"], list) else []
    world_after = state_after.get("world") if isinstance(state_after.get("world"), dict) else {}
    story_after = world_after.get("story_state") if isinstance(world_after.get("story_state"), dict) else {}
    turn_motifs = story_after.get("recent_motifs") if isinstance(story_after.get("recent_motifs"), list) else []
    slot = str(meta.get("choice_slot") or "")
    accepted_turns.append({
        "turn": turn_no,
        "slot": slot if slot in {"A", "B", "C", "D"} else "",
        "intent_category": str(meta.get("choice_category") or ""),
        "event_id": str(meta.get("event_id") or ""),
        "motif": str(turn_motifs[-1] or "") if turn_motifs else "",
        "rule_outcome": str(meta.get("turn_summary") or ""),
        "narrative": str(row["narrative"] or ""),
        "choices": [str(choice) for choice in choices[:4] if str(choice).strip()],
        "authority_hash": str(authority_state_hash_from_persisted_state(state_after) or ""),
    })

final_state = rows[-1]["state_after"] if rows and isinstance(rows[-1]["state_after"], dict) else {}
world = final_state.get("world") if isinstance(final_state.get("world"), dict) else {}
story_state = world.get("story_state") if isinstance(world.get("story_state"), dict) else {}
commitments = story_state.get("commitments") if isinstance(story_state.get("commitments"), list) else []
motifs = story_state.get("recent_motifs") if isinstance(story_state.get("recent_motifs"), list) else []
consequences = story_state.get("consequence_log") if isinstance(story_state.get("consequence_log"), list) else []
safe_statuses = {"pending", "hooked", "pressured", "due", "fulfilled", "failed"}
commitment_statuses = [
    status if status in safe_statuses else "unknown"
    for item in commitments
    if isinstance(item, dict)
    for status in [str(item.get("status") or "")]
]
route_consequences_have_dimensions = bool(consequences) and all(
    isinstance(item, dict) and isinstance(item.get("dimensions"), list) and len(item["dimensions"]) >= 2
    for item in consequences
)

print(json.dumps({
    "status": "ok",
    "turn_count": len(turns),
    "last_turn": turns[-1] if turns else 0,
    "continuous": turns == list(range(1, len(turns) + 1)),
    "authority_match": authority_mismatch_count == 0 if expected_hashes and rows else None,
    "authority_mismatch_count": authority_mismatch_count,
    "authority_replay_source": authority_replay_source,
    "duplicate_narrative_count": len(duplicates),
    "duplicates": duplicates,
    "story_status": str(story_state.get("status") or ""),
    "story_resolution": str(story_state.get("arc_resolution") or ""),
    "post_arc_turns": max(0, int(story_state.get("post_arc_turns") or 0)),
    "commitment_count": len(commitment_statuses),
    "commitment_statuses": commitment_statuses,
    "recent_motif_count": len(motifs),
    "recent_motifs_unique": len(motifs) == len(set(str(item) for item in motifs)),
    "consequence_count": len(consequences),
    "route_consequences_have_dimensions": route_consequences_have_dimensions,
    "accepted_turns": accepted_turns,
}, ensure_ascii=True))
`;
  const result = spawnSync(pythonExe, ["-c", py], {
    cwd: root,
    env: { ...environment, AGENS_PLAYTEST_SESSION_ID: sessionId },
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
    input: JSON.stringify({ opening_state: openingState }),
  });
  if (result.status !== 0) {
    throw new Error(`Failed to audit persisted turns: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return JSON.parse(result.stdout);
}

module.exports = { readPersistedOpeningState, readPersistedTurnAudit };
