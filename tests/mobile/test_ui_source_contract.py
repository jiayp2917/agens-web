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
        source = (REPO_ROOT / "mobile" / "service" / "model_presets.py").read_text(
            encoding="utf-8"
        )
        agens_index = source.index('"Agens / agnes-2.0-flash"')
        deepseek_index = source.index('"DeepSeek"')

        assert agens_index < deepseek_index
        assert '"https://apihub.agnes-ai.com/v1", "agnes-2.0-flash"' in source
        assert '"https://api.deepseek.com/v1", "deepseek-chat"' in source

    def test_home_screen_delegates_settings_popup(self):
        source = (REPO_ROOT / "mobile" / "screens" / "home_screen.py").read_text(
            encoding="utf-8"
        )

        assert "from screens.settings_popup import SettingsPopup" in source
        assert "SettingsPopup(self.audio" in source
        assert "input_api_key" not in source

    def test_settings_popup_keeps_key_out_of_plain_settings(self):
        source = (REPO_ROOT / "mobile" / "screens" / "settings_popup.py").read_text(
            encoding="utf-8"
        )

        assert "save_api_key(entered_key)" in source
        assert 'runtime_data = {**data, "api_key": entered_key}' in source
        assert "save_settings(data)" in source
        assert "save_settings(runtime_data)" not in source

    def test_action_bar_has_input_preview_and_keyboard_resize(self):
        action_bar = (REPO_ROOT / "mobile" / "widgets" / "action_bar.py").read_text(
            encoding="utf-8"
        )
        startup = (REPO_ROOT / "mobile" / "main.py").read_text(encoding="utf-8")

        assert "preview_label" in action_bar
        assert "当前输入预览" in action_bar
        assert 'Window.softinput_mode = "resize"' in startup

    def test_character_creation_uses_random_profile_summary(self):
        source = (REPO_ROOT / "mobile" / "screens" / "character_create_screen.py").read_text(
            encoding="utf-8"
        )

        assert "random_summary" in source
        assert "self.spinner_talent" not in source
        assert "self.spinner_root" not in source
        assert "self.spinner_family" not in source

    def test_character_creation_shows_only_guided_mode_enabled(self):
        source = (REPO_ROOT / "mobile" / "screens" / "character_create_screen.py").read_text(
            encoding="utf-8"
        )

        assert "self.selected_mode = \"guided\"" in source
        assert "(\"guided\", \"引导模式\", \"A/B/C + D键入\", True)" in source
        assert "(\"novel\", \"小说模式\", \"暂未开放\", False)" in source
        assert "(\"game\", \"游戏模式\", \"暂未开放\", False)" in source
        assert '"game_mode": "abcd"' in source
        assert '"ui_mode": self.selected_mode' in source
        assert "adapter.start_from_profile(profile)" in source

    def test_model_failure_popup_distinguishes_failure_types_and_redacts_keys(self):
        source = (REPO_ROOT / "mobile" / "screens" / "game_screen.py").read_text(
            encoding="utf-8"
        )

        assert "def _failure_prompt" in source
        assert "推演输出不完整" in source
        assert "天道审判受阻" in source
        assert "模型配置未完成" in source
        assert "模型请求失败" in source
        assert "secret_markers" in source
        assert "sk-" in source

    def test_model_failure_prompt_classifies_missing_key_before_redaction(self):
        source = (REPO_ROOT / "mobile" / "screens" / "game_screen.py").read_text(
            encoding="utf-8"
        )

        assert "raw_reason = reason or \"\"" in source
        assert 'elif "AGNES_API_KEY" in raw_reason or "未设置" in raw_reason:' in source
        assert "safe_reason = _safe_failure_reason(reason)" in source
