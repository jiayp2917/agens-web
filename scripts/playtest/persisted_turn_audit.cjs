"use strict";

const { spawnSync } = require("child_process");

function readPersistedTurnAudit({ root, pythonExe, sessionId, environment = process.env }) {
  const py = `
import hashlib
import json
import os
import re

from sqlalchemy import text

from agens_novel.evaluation.playthrough import canonical_authority_trajectory
from agens_novel.evaluation.scenarios import canonical_v3_scenarios

from web.backend.database import create_database

session_id = os.environ["AGENS_PLAYTEST_SESSION_ID"]
db = create_database()
with db.engine.connect() as conn:
    rows = conn.execute(
        text("""
            SELECT game_turns.turn_no, game_turns.narrative, game_turns.state_after
            FROM game_turns
            JOIN game_runs ON game_runs.id = game_turns.run_id
            WHERE game_runs.session_id = :session_id
            ORDER BY game_turns.turn_no
        """),
        {"session_id": session_id},
    ).mappings().all()

turns = [int(row["turn_no"]) for row in rows]
scenario_key = os.environ.get("AGENS_PLAYTEST_CANONICAL_SCENARIO", "").strip()
expected_hashes = []
if scenario_key:
    scenario = next((item for item in canonical_v3_scenarios() if item.key == scenario_key), None)
    if scenario is None:
        raise ValueError("playtest canonical scenario is not registered")
    expected_hashes = [
        str(item["authority_hash"])
        for item in canonical_authority_trajectory(
            scenario,
            story_version=3,
            max_turns=len(rows),
        )
    ]
authority_mismatch_count = 0
if scenario_key:
    if len(expected_hashes) != len(rows):
        authority_mismatch_count = abs(len(expected_hashes) - len(rows))
    for index, row in enumerate(rows[: len(expected_hashes)]):
        state_after = row["state_after"] if isinstance(row["state_after"], dict) else {}
        if str(state_after.get("_evaluation_authority_hash") or "") != expected_hashes[index]:
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

print(json.dumps({
    "status": "ok",
    "turn_count": len(turns),
    "last_turn": turns[-1] if turns else 0,
    "continuous": turns == list(range(1, len(turns) + 1)),
    "authority_match": authority_mismatch_count == 0 if scenario_key and rows else None,
    "authority_mismatch_count": authority_mismatch_count,
    "duplicate_narrative_count": len(duplicates),
    "duplicates": duplicates,
}, ensure_ascii=True))
`;
  const result = spawnSync(pythonExe, ["-c", py], {
    cwd: root,
    env: { ...environment, AGENS_PLAYTEST_SESSION_ID: sessionId },
    encoding: "utf8",
    maxBuffer: 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error(`Failed to audit persisted turns: ${(result.stderr || result.stdout || "").trim()}`);
  }
  return JSON.parse(result.stdout);
}

module.exports = { readPersistedTurnAudit };
