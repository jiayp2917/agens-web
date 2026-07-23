"""Regression coverage for the evaluator's private canonical Web path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agens_novel.evaluation.playthrough import (
    authority_state_hash,
    canonical_authority_trajectory,
    canonical_replay_session,
)
from agens_novel.evaluation.scenarios import canonical_v3_scenarios
from web.backend.evaluation_app import CanonicalEvaluationHooks
from web.backend.service import WebGameService, WebRunner


class _NoopResolver:
    def apply_runner(self, _runner: WebRunner) -> None:
        return None


def _service(*, canonical: bool = False) -> WebGameService:
    database = SimpleNamespace(
        get_session_mutation=lambda *_args: None,
        list_legacy_bonuses=lambda _user_id: [],
        list_catalog=lambda _table: [],
    )
    return WebGameService(
        database,
        model_config_resolver=_NoopResolver(),
        evaluation_hooks=CanonicalEvaluationHooks() if canonical else None,
    )


def _started_runner() -> WebRunner:
    runner = WebRunner(session_id="evaluation-session", user_id="evaluation-user")
    session = runner.engine.game_session
    session.game_started = True
    session.char_name = "验真青"
    session.age = 16
    session.lifespan = 80
    session.turn_count = 1
    session.last_choices = ["甲", "乙", "丙", "丁"]
    session.turn_history = [
        {
            "turn": 1,
            "choices": list(session.last_choices),
            "delta": {"meta": {"elapsed_years": 1, "choice_category": "steady"}},
            "narrative": "潮声渐远，旧灯仍在。",
        }
    ]
    return runner


def test_product_service_ignores_evaluation_environment_without_hooks(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", "high_steady")

    assert _service()._evaluation_hooks.active_scenario() is None


def test_canonical_scenario_rejects_unregistered_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", "not-registered")

    with pytest.raises(ValueError, match="not registered"):
        CanonicalEvaluationHooks().active_scenario()


def test_start_uses_canonical_profile_seed_and_v3_only_when_selected(monkeypatch) -> None:
    scenario = canonical_v3_scenarios()[0]
    monkeypatch.setenv("AGENS_EVALUATION_MODE", "1")
    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", scenario.key)
    service = _service(canonical=True)
    runner = WebRunner(session_id="evaluation-start", user_id="evaluation-user")
    service._register_runner(runner.session_id, runner)

    def start_from_profile(profile: dict[str, object]) -> None:
        session = runner.engine.game_session
        session.game_started = True
        session.char_name = str(profile["char_name"])
        session.talent = str(profile["talent"])
        session.spirit_root = str(profile["spirit_root"])
        session.world_profile = {"world_key": "ui-selected-world"}

    runner.engine.start_from_profile = start_from_profile  # type: ignore[method-assign]
    monkeypatch.setattr(
        service,
        "_commit_runner",
        lambda _runner, **kwargs: kwargs["response"],
    )

    service.start_session(
        runner.session_id,
        {"char_name": "UI 输入角色", "request_id": "evaluation-start", "expected_version": 0},
        user_id=runner.user_id,
    )

    session = runner.engine.game_session
    assert session.char_name == scenario.profile["char_name"]
    assert session.run_seed == scenario.run_seed
    assert session.story_version == 3
    assert session.world_profile["world_key"] == scenario.world_key


def test_persisted_turn_hash_is_evaluation_only(monkeypatch) -> None:
    service = _service()
    runner = _started_runner()
    before = {"turn_no": 0, "age": 15}

    monkeypatch.delenv("AGENS_EVALUATION_MODE", raising=False)
    normal = service._settled_turn_payload(runner, before, "A")
    assert normal is not None
    assert "_evaluation_authority_hash" not in normal["state_after"]

    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", "high_steady")
    evaluated = _service(canonical=True)._settled_turn_payload(runner, before, "A")
    assert evaluated is not None
    assert evaluated["state_after"]["_evaluation_authority_hash"] == authority_state_hash(
        runner.engine.game_session
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"choice_index": 0}, "选择稳妥路线，先核验线索。"),
        ({"choice": "A"}, "选择稳妥路线，先核验线索。"),
        ({"choice": "1"}, "选择稳妥路线，先核验线索。"),
    ],
)
def test_evaluation_choice_uses_canonical_action_not_model_display_text(
    monkeypatch, payload: dict[str, object], expected: str
) -> None:
    scenario = canonical_v3_scenarios()[0]
    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", scenario.key)
    runner = WebRunner(session_id="evaluation-choice", user_id="evaluation-user")
    runner.engine.game_session = canonical_replay_session(scenario, story_version=3, target_turn=0)
    runner.engine.game_session.last_choices = [
        "模型生成的显示选项一",
        "模型生成的显示选项二",
        "模型生成的显示选项三",
        "模型生成的显示选项四",
    ]

    assert _service(canonical=True)._choice_text(runner, payload) == expected


def test_evaluation_choice_produces_canonical_first_turn_hash(monkeypatch) -> None:
    scenario = canonical_v3_scenarios()[0]
    monkeypatch.setenv("AGENS_EVALUATION_SCENARIO", scenario.key)
    runner = WebRunner(session_id="evaluation-hash", user_id="evaluation-user")
    runner.engine.game_session = canonical_replay_session(scenario, story_version=3, target_turn=0)
    runner.engine.game_session.last_choices = ["显示 A", "显示 B", "显示 C", "显示 D"]
    runner.engine.run_agent = lambda *_args, **_kwargs: {
        "narrative": "规则动作已按槽位结算。",
        "choices": ["甲", "乙", "丙", "丁"],
        "state_delta": {},
        "llm_error": "",
    }

    runner.engine.handle_action(_service(canonical=True)._choice_text(runner, {"choice_index": 0}))

    expected = canonical_authority_trajectory(scenario, story_version=3, max_turns=1)[0]
    assert authority_state_hash(runner.engine.game_session) == expected["authority_hash"]


def test_authority_hash_excludes_live_opening_display_fields() -> None:
    runner = _started_runner()
    session = runner.engine.game_session
    original = authority_state_hash(session)

    session.world_profile = {"world_name": "display-only"}
    session.location = "display-only"
    session.current_scene = "display-only"
    session.lore_facts = ["display-only"]

    assert authority_state_hash(session) == original
    session.age += 1
    assert authority_state_hash(session) != original
