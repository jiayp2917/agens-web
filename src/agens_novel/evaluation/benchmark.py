"""Frozen, provider-neutral narrator benchmark and anonymous review packets."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..artifacts import sink, store
from ..engine.choices import has_visible_english, normalize_choices
from ..engine.game_engine import GameEngine
from ..engine.model_result import classify_narrator_result
from ..session.game_session import GameSession
from .ledger import EvaluationCallObserver, EvaluationLedger
from .playthrough import authority_state_hash, canonical_replay_session
from .scenarios import CanonicalScenarioV1, canonical_scenario_hash, canonical_v3_scenarios

if TYPE_CHECKING:
    from .model_config import EvaluationModelConfig

_REVIEW_CRITERIA = (
    "\u8bed\u8a00\u81ea\u7136\u5ea6",
    "\u56e0\u679c\u8fde\u7eed",
    "\u547d\u6570\u627f\u8bfa\u5151\u73b0",
    "\u9009\u9879\u5177\u4f53\u6027",
    "\u6587\u98ce\u91cd\u590d",
)


@dataclass(frozen=True)
class FrozenNarratorSnapshotV2:
    """A rule-replayed authority snapshot used once by each provider."""

    snapshot_id: str
    scenario_key: str
    phase: str
    turn_count: int
    choice_slot: str
    rule_outcome: str
    authority_hash: str
    session: GameSession


def frozen_narrator_snapshots() -> tuple[FrozenNarratorSnapshotV2, ...]:
    """Return nine fixed snapshots generated from real catalog rule replay."""
    snapshots: list[FrozenNarratorSnapshotV2] = []
    for scenario in canonical_v3_scenarios():
        for phase, turn_count in _snapshot_turns(scenario):
            snapshots.append(_snapshot(scenario, phase, turn_count))
    return tuple(snapshots)


def run_frozen_benchmark(
    config: EvaluationModelConfig,
    *,
    ledger: EvaluationLedger,
    snapshots: tuple[FrozenNarratorSnapshotV2, ...] | None = None,
) -> tuple[dict[str, Any], Any]:
    """Run one provider against immutable snapshots without turn-to-turn carryover."""
    sample_set = snapshots or frozen_narrator_snapshots()
    results = [_run_snapshot(config, snapshot, ledger) for snapshot in sample_set]
    report = {
        "benchmark_version": "frozen-narrator-v2",
        "provider": config.provider,
        "model": config.model,
        "snapshot_hash": _snapshot_hash(sample_set),
        "results": results,
        "ledger": ledger.summary(),
    }
    report["acceptance"] = frozen_benchmark_acceptance(report)
    run_id = store.new_run_id()
    path = sink.write_json("benchmark", run_id, "results.json", report)
    return report, path


def frozen_benchmark_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    """Return the strict, content-safe acceptance decision for nine snapshots."""
    results_value = report.get("results")
    results = results_value if isinstance(results_value, list) else []
    expected_ids = {item.snapshot_id for item in frozen_narrator_snapshots()}
    received_ids = {
        str(item.get("snapshot_id") or "")
        for item in results
        if isinstance(item, dict) and str(item.get("snapshot_id") or "")
    }
    issues: list[dict[str, str]] = []
    if len(results) != 9 or received_ids != expected_ids:
        issues.append({"level": "P0", "sample": "set", "code": "snapshot_set_incomplete"})
    for item in results:
        if not isinstance(item, dict):
            issues.append({"level": "P0", "sample": "unknown", "code": "invalid_result"})
            continue
        sample = str(item.get("snapshot_id") or "unknown")
        if not bool(item.get("strict")):
            issues.append({"level": "P0", "sample": sample, "code": "strict_failed"})
            continue
        narrative = str(item.get("narrative") or "").strip()
        choices = normalize_choices(item.get("choices"))
        if not narrative or len(choices) != 4:
            issues.append({"level": "P0", "sample": sample, "code": "accepted_output_incomplete"})
            continue
        if has_visible_english("\n".join([narrative, *choices])):
            issues.append({"level": "P1", "sample": sample, "code": "visible_english"})
    p0 = sum(item["level"] == "P0" for item in issues)
    p1 = sum(item["level"] == "P1" for item in issues)
    return {
        "snapshot_count": len(results),
        "strict_count": sum(bool(item.get("strict")) for item in results if isinstance(item, dict)),
        "p0_issues": p0,
        "p1_issues": p1,
        "accepted": len(results) == 9 and p0 == 0 and p1 == 0,
        "issues": issues,
    }


def build_blind_review_packet(
    first_report: dict[str, Any],
    second_report: dict[str, Any],
    *,
    review_seed: str = "frozen-narrator-v2",
) -> tuple[dict[str, Any], Any]:
    """Write anonymous left/right samples and a private model mapping separately."""
    _validate_pairable_reports(first_report, second_report)
    first_by_id = _results_by_snapshot(first_report)
    second_by_id = _results_by_snapshot(second_report)
    review_pairs: list[dict[str, Any]] = []
    mapping: list[dict[str, str]] = []
    for snapshot_id in sorted(first_by_id):
        first = _review_sample(first_by_id[snapshot_id])
        second = _review_sample(second_by_id[snapshot_id])
        first_on_left = _left_side(snapshot_id, review_seed)
        review_pairs.append(
            {
                "snapshot_id": snapshot_id,
                "left": first if first_on_left else second,
                "right": second if first_on_left else first,
            }
        )
        mapping.append(
            {
                "snapshot_id": snapshot_id,
                "left_provider": str(
                    first_report["provider"] if first_on_left else second_report["provider"]
                ),
                "left_model": str(
                    first_report["model"] if first_on_left else second_report["model"]
                ),
                "right_provider": str(
                    second_report["provider"] if first_on_left else first_report["provider"]
                ),
                "right_model": str(
                    second_report["model"] if first_on_left else first_report["model"]
                ),
            }
        )
    packet = {
        "benchmark_version": "frozen-narrator-v2",
        "pair_count": len(review_pairs),
        "criteria": list(_REVIEW_CRITERIA),
        "pairs": review_pairs,
    }
    run_id = store.new_run_id()
    path = sink.write_json("blind_review", run_id, "review-pairs.json", packet)
    sink.write_json("blind_review_mapping", run_id, "provider-mapping.json", {"mapping": mapping})
    return packet, path


def _snapshot(
    scenario: CanonicalScenarioV1,
    phase: str,
    target_turn: int,
) -> FrozenNarratorSnapshotV2:
    session = canonical_replay_session(
        scenario,
        story_version=3,
        target_turn=target_turn,
    )
    entry = session.turn_history[-1] if session.turn_history else {}
    delta = entry.get("delta") if isinstance(entry, dict) else {}
    meta = delta.get("meta") if isinstance(delta, dict) else {}
    rule_outcome = str(meta.get("turn_summary") or "") if isinstance(meta, dict) else ""
    choice_index = max(0, min(max(1, session.turn_count) - 1, len(scenario.slots) - 1))
    return FrozenNarratorSnapshotV2(
        snapshot_id=f"{scenario.key}-{phase}",
        scenario_key=scenario.key,
        phase=phase,
        turn_count=session.turn_count,
        choice_slot=scenario.slots[choice_index],
        rule_outcome=rule_outcome,
        authority_hash=authority_state_hash(session),
        session=session,
    )


def _snapshot_turns(scenario: CanonicalScenarioV1) -> tuple[tuple[str, int], ...]:
    return (("opening", 1), ("middle", 45), ("resolution", 90))


def _run_snapshot(
    config: EvaluationModelConfig,
    snapshot: FrozenNarratorSnapshotV2,
    ledger: EvaluationLedger,
) -> dict[str, Any]:
    engine = GameEngine()
    engine.model_config = config.public_metadata()
    engine.model_runtime_resolver = config.runtime_config
    engine.model_call_observer = EvaluationCallObserver(ledger)
    result = engine.run_agent(
        "narrator",
        _narrator_input(snapshot.choice_slot, snapshot.rule_outcome),
        snapshot.session,
        repair_incomplete_output=False,
    )
    status = classify_narrator_result(result)
    scenario = next(item for item in canonical_v3_scenarios() if item.key == snapshot.scenario_key)
    accepted = status.ok
    return {
        "snapshot_id": snapshot.snapshot_id,
        "scenario_key": snapshot.scenario_key,
        "phase": snapshot.phase,
        "turn_count": snapshot.turn_count,
        "scenario_hash": canonical_scenario_hash(scenario, story_version=3),
        "authority_hash": snapshot.authority_hash,
        "strict": accepted,
        "status": status.label,
        "narrative": str(result.get("narrative") or "") if accepted else "",
        "choices": [str(item) for item in result.get("choices") or []] if accepted else [],
    }


def _narrator_input(slot: str, rule_outcome: str) -> str:
    choices = {
        "A": "\u9009\u62e9\u7a33\u59a5\u8def\u7ebf\uff0c\u5148\u6838\u9a8c\u7ebf\u7d22\u3002",
        "B": "\u9009\u62e9\u673a\u9047\u8def\u7ebf\uff0c\u5411\u821f\u5ba2\u63a2\u95ee\u3002",
        "C": "\u9009\u62e9\u98ce\u9669\u8def\u7ebf\uff0c\u8e0f\u5165\u6697\u7901\u3002",
        "D": "\u9009\u62e9\u6c14\u8fd0\u8def\u7ebf\uff0c\u501f\u6f6e\u8bd5\u8def\u3002",
    }[slot]
    return f"{choices}\n\n[\u672c\u56de\u5408\u89c4\u5219\u7ed3\u7b97\u7ed3\u679c\uff08\u4ee5\u6b64\u4e3a\u6743\u5a01\u6570\u503c\uff09\uff1a{rule_outcome}]"


def _snapshot_hash(snapshots: tuple[FrozenNarratorSnapshotV2, ...]) -> str:
    payload = [
        {
            "id": item.snapshot_id,
            "scenario": item.scenario_key,
            "phase": item.phase,
            "turn": item.turn_count,
            "slot": item.choice_slot,
            "rule_outcome": item.rule_outcome,
            "authority_hash": item.authority_hash,
            "state": item.session.as_game_state(),
            "history": item.session.chat_history,
        }
        for item in snapshots
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_pairable_reports(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("benchmark_version") != "frozen-narrator-v2":
        raise ValueError("first report has an unknown benchmark version")
    if second.get("benchmark_version") != "frozen-narrator-v2":
        raise ValueError("second report has an unknown benchmark version")
    if first.get("snapshot_hash") != second.get("snapshot_hash"):
        raise ValueError("reports do not use the same frozen snapshots")
    if set(_results_by_snapshot(first)) != set(_results_by_snapshot(second)):
        raise ValueError("reports do not contain the same snapshot ids")


def _results_by_snapshot(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = report.get("results")
    if not isinstance(results, list):
        raise ValueError("benchmark report has no result list")
    mapped = {
        str(item.get("snapshot_id")): item
        for item in results
        if isinstance(item, dict) and str(item.get("snapshot_id") or "")
    }
    if len(mapped) != len(results):
        raise ValueError("benchmark report has invalid or duplicate snapshot ids")
    return mapped


def _review_sample(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "narrative": str(result.get("narrative") or ""),
        "choices": [str(item) for item in result.get("choices") or []],
    }


def _left_side(snapshot_id: str, review_seed: str) -> bool:
    seeded = random.Random(f"{review_seed}:{snapshot_id}")
    return bool(seeded.getrandbits(1))
