"""Run one strict, one-request World Builder evaluation canary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agens_novel.artifacts import sink, store
from agens_novel.engine.game_engine import GameEngine
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationCallObserver,
    EvaluationLedger,
    configured_evaluation_limits,
    evaluation_budget_root,
    evaluation_record_only,
)
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.scenarios import canonical_v3_scenarios


def main() -> int:
    args = _arguments()
    run_id, root = _prepare_artifact_root()
    config = EvaluationModelConfig.from_environment()
    record_only = evaluation_record_only()
    budget = None
    if not record_only:
        max_total_calls, max_narrator_calls = configured_evaluation_limits()
        budget = EvaluationBudget(
            evaluation_budget_root(root),
            max_total_calls=max_total_calls,
            max_narrator_calls=max_narrator_calls,
        )
    ledger = EvaluationLedger(
        provider=config.provider,
        model=config.model,
        shared_budget=budget,
        record_only=record_only,
    )
    result = run_opening_canary(config, args.scenario, ledger)
    result["run_id"] = run_id
    label = f"{config.provider.lower()}-{args.scenario}-opening-canary"
    store.write_audit("opening_canary", label, result)
    sink.write_json("opening_canary", label, "summary.json", result)
    print(json.dumps(_public_summary(result), ensure_ascii=True, sort_keys=True))
    return 0 if result["accepted"] else 2


def run_opening_canary(
    config: EvaluationModelConfig,
    scenario_key: str,
    ledger: EvaluationLedger,
) -> dict[str, Any]:
    scenario = next((item for item in canonical_v3_scenarios() if item.key == scenario_key), None)
    if scenario is None:
        raise ValueError("evaluation scenario is not registered")
    engine = GameEngine()
    engine.model_config = config.public_metadata()
    engine.model_runtime_resolver = config.runtime_config
    engine.model_call_observer = EvaluationCallObserver(ledger)
    events: list[dict[str, Any]] = []
    engine.on_model_result = _model_result_callback(events)
    previous = {
        name: os.environ.get(name)
        for name in (
            "AGENS_START_MODEL_WORLD",
            "AGENS_START_MODEL_OPENING",
            "AGENS_EVALUATION_OPENING_MAX_ATTEMPTS",
            "AGNES_MAX_RETRIES",
        )
    }
    try:
        os.environ["AGENS_START_MODEL_WORLD"] = "1"
        os.environ["AGENS_START_MODEL_OPENING"] = "1"
        os.environ["AGENS_EVALUATION_OPENING_MAX_ATTEMPTS"] = "1"
        os.environ["AGNES_MAX_RETRIES"] = "0"
        engine.start_from_profile(scenario.profile)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    opening_events = [event for event in events if event["agent"] == "world_builder"]
    strict = len(opening_events) == 1 and opening_events[0]["status"] == "ok"
    calls = ledger.summary()
    accepted = bool(
        strict
        and calls["call_count"] == 1
        and calls["narrator_call_count"] == 0
        and not engine.game_session.local_story_active
        and len(engine.game_session.last_choices) == 4
    )
    return {
        "accepted": accepted,
        "scenario": scenario.key,
        "opening_event_count": len(opening_events),
        "opening_strict": strict,
        "fallback": bool(engine.game_session.local_story_active),
        "choice_count": len(engine.game_session.last_choices),
        "ledger": calls,
        "events": opening_events,
    }


def _model_result_callback(events: list[dict[str, Any]]):
    def callback(
        agent: str,
        source: str,
        status: str,
        _model_set: bool,
        _base_url_set: bool,
        _key_set: bool,
        _config_source: str,
        diagnostics: dict[str, Any],
    ) -> None:
        events.append(
            {
                "agent": str(agent),
                "source": str(source),
                "status": str(status),
                "diagnostics": dict(diagnostics) if isinstance(diagnostics, dict) else {},
            }
        )

    return callback


def _public_summary(result: dict[str, Any]) -> dict[str, Any]:
    ledger_value = result.get("ledger")
    ledger: dict[str, Any] = ledger_value if isinstance(ledger_value, dict) else {}
    return {
        "accepted": bool(result.get("accepted")),
        "opening_event_count": int(result.get("opening_event_count") or 0),
        "opening_strict": bool(result.get("opening_strict")),
        "fallback": bool(result.get("fallback")),
        "call_count": int(ledger.get("call_count") or 0),
        "narrator_call_count": int(ledger.get("narrator_call_count") or 0),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="high_steady")
    return parser.parse_args()


def _prepare_artifact_root() -> tuple[str, Path]:
    raw_parent = os.environ.get("AGENS_EVALUATION_ARTIFACT_PARENT", "").strip()
    if not raw_parent:
        raise RuntimeError("AGENS_EVALUATION_ARTIFACT_PARENT is required")
    run_id, root = sink.create_evaluation_run_root(Path(raw_parent), label="agens-canary")
    os.environ["AGENS_ARTIFACT_ROOT"] = str(root)
    return run_id, root


if __name__ == "__main__":
    raise SystemExit(main())
