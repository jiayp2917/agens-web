"""Deterministic rules-and-flow validation for the v2 golden route."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from agens_novel.engine.choices import fallback_choices
from agens_novel.engine.game_engine import GameEngine
from agens_novel.game.constants import format_realm_name


def run_golden_route(*, seed: str, max_turns: int = 90) -> dict[str, Any]:
    previous_version = os.environ.get("AGENS_STORY_CONTENT_VERSION")
    previous_seed = os.environ.get("AGENS_VALIDATION_SEED")
    os.environ["AGENS_STORY_CONTENT_VERSION"] = "2"
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
            "ascended_within_limit": bool(
                session.finale and session.realm == "飞升" and session.turn_count <= max_turns
            ),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="agens-golden-169")
    parser.add_argument("--max-turns", type=int, default=90)
    args = parser.parse_args()
    result = run_golden_route(seed=args.seed, max_turns=args.max_turns)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ascended_within_limit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
