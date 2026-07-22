"""Frozen, provider-neutral narrator benchmark and anonymous review packets."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..artifacts import sink, store
from ..engine.game_engine import GameEngine
from ..engine.model_result import classify_narrator_result
from ..session.game_session import GameSession
from .ledger import EvaluationCallObserver, EvaluationLedger
from .scenarios import CanonicalScenarioV1, canonical_v3_scenarios

if TYPE_CHECKING:
    from .model_config import EvaluationModelConfig

_REVIEW_CRITERIA = (
    "语言自然度",
    "因果连续",
    "命数承诺兑现",
    "选项具体性",
    "文风重复",
)


@dataclass(frozen=True)
class FrozenNarratorSnapshotV1:
    """A non-model authority snapshot used once by each provider."""

    snapshot_id: str
    scenario_key: str
    phase: str
    turn_count: int
    choice_slot: str
    session: GameSession


def frozen_narrator_snapshots() -> tuple[FrozenNarratorSnapshotV1, ...]:
    """Return nine fixed snapshots that do not depend on model history."""
    snapshots: list[FrozenNarratorSnapshotV1] = []
    for scenario in canonical_v3_scenarios():
        for phase, turn_count, slot in (("opening", 1, "A"), ("middle", 45, "B"), ("resolution", 90, "C")):
            snapshots.append(_snapshot(scenario, phase, turn_count, slot))
    return tuple(snapshots)


def run_frozen_benchmark(
    config: EvaluationModelConfig,
    *,
    ledger: EvaluationLedger,
    snapshots: tuple[FrozenNarratorSnapshotV1, ...] | None = None,
) -> tuple[dict[str, Any], Any]:
    """Run one provider against immutable snapshots without turn-to-turn carryover."""
    sample_set = snapshots or frozen_narrator_snapshots()
    results = [_run_snapshot(config, snapshot, ledger) for snapshot in sample_set]
    report = {
        "benchmark_version": "frozen-narrator-v1",
        "provider": config.provider,
        "model": config.model,
        "snapshot_hash": _snapshot_hash(sample_set),
        "results": results,
        "ledger": ledger.summary(),
    }
    run_id = store.new_run_id()
    path = sink.write_json("benchmark", run_id, "results.json", report)
    return report, path


def build_blind_review_packet(
    first_report: dict[str, Any],
    second_report: dict[str, Any],
    *,
    review_seed: str = "frozen-narrator-v1",
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
                "left_provider": str(first_report["provider"] if first_on_left else second_report["provider"]),
                "left_model": str(first_report["model"] if first_on_left else second_report["model"]),
                "right_provider": str(second_report["provider"] if first_on_left else first_report["provider"]),
                "right_model": str(second_report["model"] if first_on_left else first_report["model"]),
            }
        )
    packet = {
        "benchmark_version": "frozen-narrator-v1",
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
    turn_count: int,
    choice_slot: str,
) -> FrozenNarratorSnapshotV1:
    profile = scenario.profile
    session = GameSession(
        game_started=True,
        turn_count=turn_count,
        run_seed=scenario.run_seed,
        char_name=str(profile["char_name"]),
        talent=str(profile["talent"]),
        spirit_root=str(profile["spirit_root"]),
        spirit_root_grade=str(profile["spirit_root_grade"]),
        family_background=str(profile["family_background"]),
        difficulty=str(profile["difficulty"]),
        attributes=dict(profile["attributes"]),
        age=16 + turn_count // 3,
        location="潮音渡口",
        region="沧澜群岛",
        current_scene="渡口潮雾",
        world_profile={"world_key": scenario.world_key},
        story_key=f"{scenario.world_key}:v3",
        story_version=3,
        story_state={
            "phase": phase,
            "arc_resolution": "pending",
            "recent_motifs": ["潮声", "旧灯", "渡口"],
            "commitments": ["查明潮音渡口旧灯的来历", "在试炼前决定去留"],
        },
        last_choices=["稳妥探查", "结交舟客", "越过暗礁", "借潮试路"],
        chat_history=[
            {
                "role": "assistant",
                "content": "潮音渡口的旧灯照着雾岸，试炼前的承诺尚未兑现。",
            }
        ],
    )
    return FrozenNarratorSnapshotV1(
        snapshot_id=f"{scenario.key}-{phase}",
        scenario_key=scenario.key,
        phase=phase,
        turn_count=turn_count,
        choice_slot=choice_slot,
        session=session,
    )


def _run_snapshot(
    config: EvaluationModelConfig,
    snapshot: FrozenNarratorSnapshotV1,
    ledger: EvaluationLedger,
) -> dict[str, Any]:
    engine = GameEngine()
    runtime = config.runtime_config()
    engine.model_config = runtime.public_metadata()
    engine.model_runtime_resolver = config.runtime_config
    engine.model_call_observer = EvaluationCallObserver(ledger)
    result = engine.run_agent(
        "narrator",
        _choice_input(snapshot.choice_slot),
        snapshot.session,
        repair_incomplete_output=False,
    )
    status = classify_narrator_result(result)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "scenario_key": snapshot.scenario_key,
        "phase": snapshot.phase,
        "turn_count": snapshot.turn_count,
        "strict": status.ok,
        "status": status.label,
        "narrative": str(result.get("narrative") or ""),
        "choices": [str(item) for item in result.get("choices") or []],
    }


def _choice_input(slot: str) -> str:
    return {
        "A": "选择稳妥路线，先核验线索。",
        "B": "选择机遇路线，向舟客探问。",
        "C": "选择风险路线，踏入暗礁。",
        "D": "选择气运路线，借潮试路。",
    }[slot]


def _snapshot_hash(snapshots: tuple[FrozenNarratorSnapshotV1, ...]) -> str:
    payload = [
        {
            "id": item.snapshot_id,
            "scenario": item.scenario_key,
            "phase": item.phase,
            "turn": item.turn_count,
            "slot": item.choice_slot,
            "state": item.session.as_game_state(),
            "history": item.session.chat_history,
        }
        for item in snapshots
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_pairable_reports(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("benchmark_version") != "frozen-narrator-v1":
        raise ValueError("first report has an unknown benchmark version")
    if second.get("benchmark_version") != "frozen-narrator-v1":
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
