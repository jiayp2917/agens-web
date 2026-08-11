"""Rule RNG and authoritative outcome contracts."""

from __future__ import annotations

from agens_novel.engine.start_flow import apply_profile_session
from agens_novel.engine.turn_rules import settle_turn_outcome
from agens_novel.game.realm import golden_breakthrough_flags
from agens_novel.rule_rng import new_run_seed
from agens_novel.session.game_session import GameSession


def _profile() -> dict[str, object]:
    return {
        "char_name": "验真者",
        "talent": "天命道胎",
        "spirit_root": "火灵根",
        "spirit_root_grade": "地",
        "family_background": "散修遗孤",
        "difficulty": "普通",
        "attributes": {
            "root_bone": 5,
            "comprehension": 5,
            "luck": 5,
            "willpower": 5,
            "physique": 5,
            "soul": 5,
        },
    }


def test_same_seed_counter_and_slot_produce_same_rule_outcome() -> None:
    first = GameSession(run_seed="fixed-seed", rule_rng_counter=7, turn_count=8)
    second = GameSession(run_seed="fixed-seed", rule_rng_counter=7, turn_count=8)

    first_outcome = settle_turn_outcome("D【气运】随缘而行", first)
    second_outcome = settle_turn_outcome("D【气运】不同显示文案", second)

    assert first_outcome.intent.slot == "D"
    assert first_outcome.intent.category == "气运"
    assert first_outcome.state_delta == second_outcome.state_delta


def test_profile_start_persists_rng_state_through_save_round_trip() -> None:
    session = GameSession()
    apply_profile_session(session, _profile())
    session.rule_rng_counter = 3

    restored = GameSession.from_save_dict(session.to_save_dict())

    assert restored.run_seed == session.run_seed
    assert restored.rule_rng_counter == 3
    assert settle_turn_outcome("A【稳妥】稳住根基", restored).state_delta == settle_turn_outcome(
        "A【稳妥】另一段显示文案", session
    ).state_delta


def test_validation_seed_becomes_the_persisted_run_seed(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_VALIDATION_SEED", "local-v2-fixed-seed")

    assert new_run_seed() == "local-v2-fixed-seed"


def test_v3_long_form_progress_grants_rule_owned_breakthrough_preparation() -> None:
    session = GameSession(story_version=3, realm="练气", realm_stage=8, realm_turn_count=16)

    assert golden_breakthrough_flags(session) == ("foundation_aid",)


def test_v3_calendar_advances_on_story_beats_instead_of_every_choice() -> None:
    session = GameSession(run_seed="v3-calendar", story_version=3, turn_count=1)

    scene_outcome = settle_turn_outcome("A【稳妥】稳住根基", session)
    session.turn_count = 4
    beat_outcome = settle_turn_outcome("A【稳妥】稳住根基", session)

    assert scene_outcome.state_delta["character"]["age"] == "+0"
    assert "时间流逝：数月" in scene_outcome.turn_summary
    assert beat_outcome.state_delta["character"]["age"] == "+1"


def test_seeded_risk_route_can_resolve_a_rule_owned_death(monkeypatch) -> None:
    class AlwaysRiskRuleRng:
        def randint(self, lower: int, _upper: int, _stream: str) -> int:
            return lower

        def random(self, _stream: str) -> float:
            return 0.0

    session = GameSession(run_seed="risk", difficulty="困难", story_version=3)
    session.attributes = {
        "root_bone": 2,
        "comprehension": 2,
        "luck": 2,
        "willpower": 8,
        "physique": 8,
        "soul": 8,
    }
    monkeypatch.setattr(
        "agens_novel.engine.turn_rules.rule_rng_for_session",
        lambda _session: AlwaysRiskRuleRng(),
    )

    outcome = settle_turn_outcome("C【风险】踏入险地", session)

    assert outcome.state_delta["meta"]["risk_death"] is True
    assert outcome.state_delta["meta"]["game_over"] is True
    assert "身死" in outcome.state_delta["meta"]["game_over_reason"]
