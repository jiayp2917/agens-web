"""Deterministic rules-and-flow validation for a versioned golden route."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from typing import Any

from agens_novel.engine.choices import fallback_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.game.constants import format_realm_name
from agens_novel.verification.authority import (
    canonical_authority_trajectory,
    canonical_replay_session,
)
from agens_novel.verification.scenarios import canonical_v3_scenarios


def run_golden_route(*, seed: str, story_version: int = 2, max_turns: int = 90) -> dict[str, Any]:
    if story_version not in {1, 2, 3}:
        raise ValueError("story_version must be 1, 2, or 3")
    previous_version = os.environ.get("AGENS_STORY_CONTENT_VERSION")
    previous_seed = os.environ.get("AGENS_VALIDATION_SEED")
    os.environ["AGENS_STORY_CONTENT_VERSION"] = str(story_version)
    os.environ["AGENS_VALIDATION_SEED"] = seed
    try:
        engine = GameEngine()
        engine.start_from_profile(
            {
                "char_name": "验真者",
                "talent": "天命道胎",
                "spirit_root": "雷灵根",
                "spirit_root_grade": "天",
                "family_background": "隐世仙族",
                "difficulty": "普通",
                "attributes": {
                    "root_bone": 7,
                    "comprehension": 7,
                    "luck": 7,
                    "willpower": 3,
                    "physique": 3,
                    "soul": 3,
                },
            }
        )
        engine.run_agent = _deterministic_agent  # type: ignore[method-assign]
        checkpoints: list[dict[str, Any]] = []
        breakthrough_attempts: list[dict[str, Any]] = []
        previous_realm = engine.game_session.realm

        while engine.game_session.turn_count < max_turns and not engine.game_session.game_over:
            can_breakthrough, _reason = engine.realm_system.can_attempt_breakthrough(
                engine.game_session
            )
            if can_breakthrough:
                before_realm = engine.game_session.realm
                before_turn = engine.game_session.turn_count
                before_realm_turn = engine.game_session.realm_turn_count
                engine.attempt_breakthrough()
                breakthrough_attempts.append(
                    {
                        "realm": before_realm,
                        "turn_before": before_turn,
                        "realm_turn_before": before_realm_turn,
                        "succeeded": engine.game_session.realm != before_realm,
                    }
                )
            else:
                engine.handle_action("A")
            session = engine.game_session
            if session.realm != previous_realm or session.game_over:
                checkpoints.append(
                    {
                        "turn": session.turn_count,
                        "realm": session.realm,
                        "realm_stage": session.realm_stage,
                        "finale": session.finale,
                    }
                )
                previous_realm = session.realm

        session = engine.game_session
        story_resolution = str(session.story_state.get("arc_resolution") or "")
        story_status = str(session.story_state.get("status") or "")
        ascended = bool(session.finale and session.realm == "飞升" and session.turn_count <= max_turns)
        mainline_resolved = bool(
            story_version == 3
            and session.turn_count == max_turns
            and story_resolution in {"resolved", "failed"}
            and story_status in {"post_arc", "resolved", "failed"}
        )
        return {
            "seed": seed,
            "max_turns": max_turns,
            "turn_count": session.turn_count,
            "realm": session.realm,
            "realm_stage": session.realm_stage,
            "realm_label": format_realm_name(session.realm, session.realm_stage),
            "story_version": session.story_version,
            "game_over": session.game_over,
            "finale": session.finale,
            "story_resolution": story_resolution,
            "story_status": story_status,
            "ascended_within_limit": ascended,
            "accepted_within_limit": mainline_resolved if story_version == 3 else ascended,
            "checkpoints": checkpoints,
            "breakthrough_attempts": breakthrough_attempts,
        }
    finally:
        _restore_env("AGENS_STORY_CONTENT_VERSION", previous_version)
        _restore_env("AGENS_VALIDATION_SEED", previous_seed)


def _deterministic_agent(
    agent_name: str,
    user_input: str,
    session: Any,
    **_kwargs: Any,
) -> dict[str, Any]:
    if agent_name == "narrator":
        success = "突破成功" in user_input
        failure = "突破失败" in user_input
        if success:
            narrative = "破境已成，旧境积累由此化为更高道基。"
        elif failure:
            narrative = "破境未成，灵机反噬，此后先以稳妥调息修复根基。"
        else:
            narrative = "编年又过一载，主线因果、修行进境与外界局势一并向前推进。"
        return {
            "narrative": narrative,
            "state_delta": {},
            "choices": fallback_choices(session),
            "llm_error": "",
        }
    if agent_name == "judge":
        return {
            "approved": True,
            "corrected_delta": {},
            "judgment_note": "规则结果一致",
            "review_score": 10,
            "llm_error": "",
        }
    raise ValueError(f"unexpected validation agent: {agent_name}")


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def run_v3_scenario(
    *,
    scenario_key: str,
    seed: str | None = None,
    max_turns: int = 90,
) -> dict[str, Any]:
    """Replay one pre-registered v3 route without an LLM or breakthrough shortcuts."""
    scenario = next((item for item in canonical_v3_scenarios() if item.key == scenario_key), None)
    if scenario is None:
        raise ValueError("scenario must be one of the registered v3 scenarios")
    if seed:
        scenario = replace(scenario, run_seed=seed)
    trajectory = canonical_authority_trajectory(scenario, story_version=3, max_turns=max_turns)
    session = canonical_replay_session(
        scenario,
        story_version=3,
        target_turn=len(trajectory),
    )
    resolution = str(session.story_state.get("arc_resolution") or "")
    status = str(session.story_state.get("status") or "")
    return {
        "scenario": scenario.key,
        "seed": scenario.run_seed,
        "max_turns": max_turns,
        "turn_count": session.turn_count,
        "story_version": session.story_version,
        "game_over": session.game_over,
        "finale": session.finale,
        "story_resolution": resolution,
        "story_status": status,
        "trajectory_count": len(trajectory),
        "accepted_within_limit": bool(
            session.game_over
            or (
                session.turn_count == max_turns
                and resolution in {"resolved", "failed"}
                and status == "post_arc"
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed")
    parser.add_argument("--story-version", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--scenario", choices=("high_steady", "low_risk", "middle_mixed"))
    parser.add_argument("--max-turns", type=int, default=90)
    args = parser.parse_args()
    result = (
        run_v3_scenario(
            scenario_key=args.scenario or "high_steady",
            seed=args.seed,
            max_turns=args.max_turns,
        )
        if args.story_version == 3
        else run_golden_route(
            seed=args.seed or "agens-golden-169",
            story_version=args.story_version,
            max_turns=args.max_turns,
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["accepted_within_limit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
