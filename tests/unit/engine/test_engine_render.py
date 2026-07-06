"""Tests for UI-agnostic engine render functions."""

from __future__ import annotations

from agens_novel.engine.render import (
    format_status_bar,
)
from agens_novel.session.game_session import GameSession


class TestFormatStatusBar:
    def test_default_session(self) -> None:
        s = GameSession()
        text = format_status_bar(s)
        assert "练气" in text
        assert "寿元" in text  # game-mode v5: lifespan replaces HP/MP

    def test_with_name_and_realm(self) -> None:
        s = GameSession(char_name="许满", realm="筑基", realm_stage=3, lifespan=80)
        text = format_status_bar(s)
        assert "筑基" in text
        assert "寿元" in text
        # No HP/MP segments in the game-mode status bar.
        assert "HP" not in text
        assert "MP" not in text
