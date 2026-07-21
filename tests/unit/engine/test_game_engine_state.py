"""Tests for GameEngine state management, persistence, and game lifecycle — UI-agnostic game logic service."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from agens_novel.engine.game_engine import GameEngine
from agens_novel.engine.world_generator import build_world_fallback
from agens_novel.session.game_session import GameSession

# ═══════════════════════════════════════════════════════════════════════════════
# Canned helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _canned_world_builder() -> dict[str, Any]:
    generated = build_world_fallback(
        {
            "char_name": "许满",
            "spirit_root": "火木双灵根",
            "spirit_root_grade": "地",
        }
    )
    generated["world"].update(
        {
            "current_scene": "晨雾中的青云山外门",
            "location": "青云山外门",
            "region": "东荒",
        }
    )
    return {
        "generated_data": generated,
        "world_description": "",
        "opening_narrative": "",
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


class _FixedRuleRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self, _stream: str) -> float:
        return self.value


def _canned_judge() -> dict[str, Any]:
    return {
        "approved": True,
        "corrected_delta": {},
        "judgment_note": "ok",
        "review_score": 8,
        "output_path": "",
        "audit_path": "",
        "finished_at": "",
        "llm_error": "",
    }


def _patch_turn_runner(call_log: list | None = None) -> Any:
    if call_log is None:
        call_log = []

    def fake_run_turn_sync(
        agent_name: str, user_input: str, session: GameSession, **kwargs
    ) -> dict:
        call_log.append(agent_name)
        if agent_name == "judge":
            return _canned_judge()
        if agent_name == "world_builder":
            return _canned_world_builder()
        return {}

    return patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_run_turn_sync)


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
