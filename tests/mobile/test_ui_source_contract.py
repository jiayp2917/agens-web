"""Source-contract tests for the Android mobile UI.

These tests read the mobile screen / widget source files and assert
that forbidden constructs (slash-command routing, persistent combat
buttons, etc.) are NOT present. They guard the architectural decision
"Android is A/B/C/D only" against accidental regressions.
"""

from __future__ import annotations

import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestAndroidFreeTextInput:
    """Test that Android does not expose terminal-style command routing."""

    def test_game_screen_has_no_slash_command_router(self):
        source = (REPO_ROOT / "mobile" / "screens" / "game_screen.py").read_text(
            encoding="utf-8"
        )

        assert "_SLASH_COMMANDS" not in source
        assert "_parse_slash_command" not in source
        assert 'startswith("/")' not in source
        assert "handle_combat_action(action, target)" not in source

    def test_choices_ui_is_compact_and_keeps_d_input_hint(self):
        narrative_view = (REPO_ROOT / "mobile" / "widgets" / "narrative_view.py").read_text(
            encoding="utf-8"
        )
        assert "height=dp(44)" in narrative_view
        assert "D. 自行键入行动" in narrative_view

        action_bar = (REPO_ROOT / "mobile" / "widgets" / "action_bar.py").read_text(
            encoding="utf-8"
        )
        assert "BUTTONS =" not in action_bar
        assert '"更多"' in action_bar

    def test_normal_game_over_resets_finale_flag(self):
        source = (REPO_ROOT / "mobile" / "screens" / "game_screen.py").read_text(
            encoding="utf-8"
        )
        assert "death.is_finale = False" in source
        assert "death.is_finale = True" in source

    def test_settings_keeps_agens_default_and_deepseek_test_preset(self):
        source = (REPO_ROOT / "mobile" / "screens" / "home_screen.py").read_text(
            encoding="utf-8"
        )
        agens_index = source.index('"Agens · agnes-2.0-flash"')
        deepseek_index = source.index('"DeepSeek"')

        assert agens_index < deepseek_index
        assert '"https://apihub.agnes-ai.com/v1", "agnes-2.0-flash"' in source
        assert '"https://api.deepseek.com/v1", "deepseek-chat"' in source
