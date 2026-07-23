"""Tests for GameEngine state management, persistence, and game lifecycle — UI-agnostic game logic service."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.session.game_session import GameSession
from tests.unit.engine.fixtures import canned_judge as _canned_judge
from tests.unit.engine.fixtures import canned_world_builder as _canned_world_builder
from tests.unit.engine.fixtures import patch_turn_runner as _patch_turn_runner_base

# ═══════════════════════════════════════════════════════════════════════════════
# Canned helpers
# ═══════════════════════════════════════════════════════════════════════════════


class _FixedRuleRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self, _stream: str) -> float:
        return self.value


def _patch_turn_runner(call_log: list | None = None) -> Any:
    return _patch_turn_runner_base(
        judge=_canned_judge,
        world_builder=_canned_world_builder,
        call_log=call_log,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGameSessionRoundtrip:
    """Session serialization roundtrip via to_save_dict / from_save_dict."""

    def test_session_serialization_roundtrip(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        data = engine.game_session.to_save_dict()
        restored = GameSession.from_save_dict(data)

        assert restored.char_name == "许满"
        assert restored.game_started is True
        assert restored.realm == "练气"

    def test_session_from_empty_dict(self) -> None:
        session = GameSession.from_save_dict({})
        assert session.char_name == ""
        assert not session.game_started

    def test_session_serialization_excludes_legacy_fields(self, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        engine = GameEngine()
        with _patch_turn_runner():
            engine.new_game("许满")

        data = engine.game_session.to_save_dict()
        assert "hp" not in data.get("character", data)
        assert "mp" not in data.get("character", data)
        assert "combat" not in data.get("character", data)


class TestFinaleCallback:
    """Tests for ascension finale handling."""

    def test_finale_callback_on_ascension(self, monkeypatch) -> None:
        """Breaking through to 飞升 fires on_finale."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        finales: list[str] = []
        game_overs: list[str] = []
        engine.on_finale = lambda reason: finales.append(reason)
        engine.on_game_over = lambda reason: game_overs.append(reason)

        with _patch_turn_runner():
            engine.new_game("许满")

        # Set to max stage of 渡劫 with the required breakthrough resources.
        engine.game_session.realm = "渡劫"
        engine.game_session.realm_stage = 4
        engine.game_session.breakthrough_flags = ["tribulation_elixir", "ascension_protection"]

        # Mock random and LLM to guarantee deterministic unit behavior.
        with _patch_turn_runner():
            with patch(
                "agens_novel.game.realm.rule_rng_for_session",
                return_value=_FixedRuleRng(0.001),
            ):
                engine.attempt_breakthrough()

        assert len(finales) == 1
        assert game_overs == []
        assert "飞升" in finales[0]
        assert engine.game_session.finale is True
        assert engine.game_session.game_over is True
        assert engine.game_session.realm == "飞升"
        assert engine.game_session.turn_count == 1
        assert len(engine.game_session.turn_history) == 1
        assert engine.game_session.turn_history[-1]["delta"]["meta"]["finale"] is True
        assert engine.game_session.last_choices == []

    def test_death_screen_no_finale_for_normal_death(self, monkeypatch) -> None:
        """Game-mode v5: a normal death (game_over set, no finale) does not
        raise the finale/ascension screen."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        engine = GameEngine()
        game_overs: list[str] = []
        engine.on_game_over = lambda reason: game_overs.append(reason)

        engine.game_session.game_started = True
        engine.game_session.game_over = True
        engine.game_session.finale = False
        engine.game_session.error = "天命难违"
        engine.game_session.char_name = "许满"
        engine.check_game_over()

        assert engine.game_session.finale is False
        assert engine.game_session.game_over is True
        assert len(game_overs) == 1
        assert engine.game_session.turn_count == 0
