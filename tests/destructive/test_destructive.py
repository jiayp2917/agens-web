"""Destructive tests for the core runtime.

These tests keep adversarial coverage on the shared session, parser, and
save/load layers that the web runtime depends on.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agens_novel.agents.narrator.nodes import _parse_narrator_output
from agens_novel.engine.model_result import ModelResultKind, classify_narrator_result
from agens_novel.session.game_session import GameSession


class TestApplyDeltaDestructive:
    """Attack GameSession.apply_delta with malformed LLM-style values."""

    @pytest.mark.parametrize(
        "bad_val",
        ["+abc", "+3.5", "+", "-abc", "-3.5", "-", "+0x10", "++5", "--5", "+ 10"],
    )
    def test_malformed_increment_string_is_ignored(self, bad_val: str) -> None:
        s = GameSession(lifespan=80)
        s.apply_delta({"character": {"lifespan": bad_val}})
        assert isinstance(s.lifespan, int)
        assert s.lifespan >= 1  # lifespan floors at 1 in game mode

    @pytest.mark.parametrize("bad_val", [3.14, None, True, False, [5], {"lifespan": 5}])
    def test_non_numeric_types_are_ignored(self, bad_val: Any) -> None:
        s = GameSession(lifespan=80)
        s.apply_delta({"character": {"lifespan": bad_val}})
        assert s.lifespan == 80

    def test_stat_clamps_survive_extreme_values(self) -> None:
        s = GameSession(lifespan=100)
        s.apply_delta({"character": {"lifespan": "+999999", "gold": "-999999"}})
        assert s.lifespan == 1000099
        assert not hasattr(s, "gold")

    def test_invalid_realm_is_rejected(self) -> None:
        s = GameSession(realm="练气")
        s.apply_delta({"character": {"realm": "超级赛亚人"}})
        assert s.realm == "练气"

    def test_list_add_fields_ignore_none(self) -> None:
        s = GameSession()
        s.apply_delta(
            {
                "character": {
                    "techniques_add": None,
                    "inventory_add": None,
                    "status_effects_add": None,
                    "breakthrough_flags_add": None,
                },
                "world": {
                    "npcs_present_add": None,
                    "active_quests_add": None,
                    "lore_add": None,
                    "discovered_add": None,
                },
            }
        )
        assert s.techniques == []
        assert s.inventory == []
        assert s.status_effects == []
        assert s.breakthrough_flags == []
        assert s.npcs_present == []
        assert s.active_quests == []
        assert s.lore_facts == []
        assert s.discovered_locations == []

    def test_combat_delta_is_ignored_in_game_mode(self) -> None:
        """Game-mode v5: structured combat delta is dropped (combat is event-based)."""
        s = GameSession()
        s.apply_delta({"character": {"combat": {"phase": "player_turn"}}})
        assert not hasattr(s, "combat")  # never set
        s.apply_delta({"character": {"combat": None}})
        assert not hasattr(s, "combat")
        s.apply_delta({"character": {"combat": {"phase": "player_turn"}}})
        s.apply_delta({"character": {"combat": {}}})
        assert not hasattr(s, "combat")


class TestParserDestructive:
    """LLM parser inputs should fail closed instead of crashing."""

    @pytest.mark.parametrize("text", ["", "plain text only", "<state_update>{bad json}</state_update>"])
    def test_narrator_parser_handles_malformed_output(self, text: str) -> None:
        narrative, delta, choices = _parse_narrator_output(text)
        assert isinstance(narrative, str)
        assert delta is None or isinstance(delta, dict)
        assert isinstance(choices, list)
        status = classify_narrator_result({
            "narrative": narrative,
            "state_delta": delta,
            "choices": choices,
        })
        assert status.kind in {ModelResultKind.OK, ModelResultKind.INCOMPLETE_OUTPUT}


class TestAsGameState:
    def test_produces_json_serializable_state(self) -> None:
        s = GameSession(char_name="许满", realm="筑基", lifespan=85)
        parsed = json.loads(json.dumps(s.as_game_state(), ensure_ascii=False))
        assert parsed["character"]["name"] == "许满"
        assert parsed["character"]["lifespan"] == 85
        assert "world" in parsed
