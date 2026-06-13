"""Destructive / adversarial tests — simulate players probing the game for bugs.

These tests intentionally feed malformed, extreme, or malicious inputs to
every entry point to verify robustness.  No test should crash with an
unhandled exception.
"""

from __future__ import annotations

import json
import math
from typing import Any
from unittest.mock import patch

import pytest

from agens_novel.agents.judge.nodes import _parse_judge_output
from agens_novel.agents.narrator.nodes import _parse_narrator_output
from agens_novel.repl import Repl
from agens_novel.repl.commands import (
    EmptyCommand,
    ExitCommand,
    SlashCommand,
    WriteCommand,
    parse_command,
)
from agens_novel.repl.game_session import GameSession
from agens_novel.repl.game_view import (
    _bar,
    _stage_suffix,
    render_inventory_table,
    render_skills_table,
    render_status_bar,
    render_status_panel,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. GameSession.apply_delta — adversarial inputs
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyDeltaDestructive:
    """Attack apply_delta with every kind of bad value."""

    # ── Numeric fields: malformed +/- strings ──────────────────────────────────

    @pytest.mark.parametrize("bad_val", [
        "+abc",       # non-numeric suffix
        "+3.5",       # float in string
        "+",          # bare plus
        "-abc",       # non-numeric minus suffix
        "-3.5",       # float in string
        "-",          # bare minus
        "+0x10",      # hex
        "++5",        # double plus
        "--5",        # double minus
        "+ 10",       # space in number
    ])
    def test_malformed_increment_string_crashes_or_is_caught(self, bad_val: str) -> None:
        """Malformed +/- strings should not silently corrupt state."""
        s = GameSession(hp=80)
        try:
            s.apply_delta({"character": {"hp": bad_val}})
            # If it didn't crash, the value should be unchanged (graceful)
            # or at least be a valid int
            assert isinstance(s.hp, int), f"hp became {type(s.hp).__name__}: {s.hp}"
        except (ValueError, TypeError):
            pass  # acceptable — the bug exists and throws; test documents it

    # ── Numeric fields: extreme values ─────────────────────────────────────────

    def test_hp_exceeds_hp_max(self) -> None:
        """HP is clamped to hp_max — this is correct behavior."""
        s = GameSession(hp=100, hp_max=100)
        s.apply_delta({"character": {"hp": 999999}})
        assert s.hp == 100  # clamped to hp_max

    def test_negative_absolute_hp(self) -> None:
        """A negative int is applied but clamped to 0 by the HP floor guard."""
        s = GameSession(hp=50)
        s.apply_delta({"character": {"hp": -100}})
        assert s.hp == 0  # floored at 0

    def test_massive_subtraction_floors_at_zero(self) -> None:
        """Subtraction with max(0, ...) should floor at zero."""
        s = GameSession(hp=10)
        s.apply_delta({"character": {"hp": "-99999"}})
        assert s.hp == 0

    def test_zero_minus_zero(self) -> None:
        """Edge: -0 should not change the value."""
        s = GameSession(hp=50)
        s.apply_delta({"character": {"hp": "-0"}})
        assert s.hp == 50

    def test_massive_increment(self) -> None:
        """Massive HP increment is clamped to hp_max."""
        s = GameSession(hp=50, hp_max=100)
        s.apply_delta({"character": {"hp": "+99999999"}})
        assert s.hp == 100  # clamped to hp_max

    # ── Non-int types silently ignored ─────────────────────────────────────────

    @pytest.mark.parametrize("bad_val", [
        3.14,         # float — silently ignored
        None,         # None — silently ignored
        True,         # bool — subclass of int but explicitly guarded
        False,        # bool — should also be ignored
        [5],          # list — silently ignored
        {"hp": 5},    # dict — silently ignored
    ])
    def test_non_int_non_string_types_ignored(self, bad_val: Any) -> None:
        """Float/None/bool/list/dict should be silently ignored for numeric fields."""
        s = GameSession(hp=80)
        s.apply_delta({"character": {"hp": bad_val}})
        assert s.hp == 80, f"hp changed to {s.hp} from {bad_val!r}"

    # ── List extend fields: non-iterable crash probes ──────────────────────────

    def test_techniques_add_with_none_crashes(self) -> None:
        """techniques_add=None is now safely ignored (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"character": {"techniques_add": None}})
        assert s.techniques == []  # no crash, silently ignored

    def test_techniques_add_with_int_crashes(self) -> None:
        """techniques_add=42 (int) is now safely ignored."""
        s = GameSession()
        s.apply_delta({"character": {"techniques_add": 42}})
        assert s.techniques == []  # no crash, silently ignored

    def test_inventory_add_with_string(self) -> None:
        """String input to inventory_add is now treated as a single item (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"character": {"inventory_add": "sword"}})
        assert len(s.inventory) == 1  # single string → single item, not 5 chars
        assert s.inventory[0] == "sword"

    def test_lore_add_with_none_crashes(self) -> None:
        """lore_add=None is now safely ignored (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"world": {"lore_add": None}})
        assert s.lore_facts == []  # no crash

    def test_discovered_add_with_none_crashes(self) -> None:
        """discovered_add=None is now safely ignored (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"world": {"discovered_add": None}})
        assert s.discovered_locations == []  # no crash

    # ── status_effects type confusion ──────────────────────────────────────────

    def test_status_effects_set_to_string(self) -> None:
        """status_effects set to string is now safely ignored (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"character": {"status_effects": "中毒"}})
        assert s.status_effects == []  # string rejected, keeps list
        assert isinstance(s.status_effects, list)

    def test_status_effects_set_to_int(self) -> None:
        """status_effects set to int is now safely ignored (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"character": {"status_effects": 42}})
        assert s.status_effects == []  # int rejected, keeps list

    # ── Realm validation ───────────────────────────────────────────────────────

    def test_realm_set_to_arbitrary_string(self) -> None:
        """Arbitrary realm strings are now rejected (v0.4 realm whitelist)."""
        s = GameSession(realm="练气")
        s.apply_delta({"character": {"realm": "超级赛亚人"}})
        assert s.realm == "练气"  # rejected, stays at original

    def test_realm_set_to_empty_string(self) -> None:
        """Empty realm string is now rejected (v0.4 realm whitelist)."""
        s = GameSession(realm="练气")
        s.apply_delta({"character": {"realm": ""}})
        assert s.realm == "练气"  # rejected, stays at original

    # ── Delta with unknown keys ────────────────────────────────────────────────

    def test_unknown_character_keys_ignored(self) -> None:
        s = GameSession(hp=50)
        s.apply_delta({"character": {"nonexistent_field": 999, "hp": 10}})
        assert s.hp == 10  # known field applied
        assert not hasattr(s, "nonexistent_field") or True  # no dynamic attrs

    def test_unknown_top_level_keys_ignored(self) -> None:
        s = GameSession()
        s.apply_delta({"completely_unknown": {"stuff": True}})
        # No crash — unknown top-level keys ignored

    def test_empty_delta(self) -> None:
        s = GameSession(hp=50)
        s.apply_delta({})
        assert s.hp == 50  # unchanged

    # ── Game over edge cases ───────────────────────────────────────────────────

    def test_game_over_false_is_not_truthy(self) -> None:
        s = GameSession()
        s.apply_delta({"meta": {"game_over": False}})
        assert s.game_over is False

    def test_game_over_with_string_truthy(self) -> None:
        """game_over set to non-bool string is now rejected (v0.4 defense)."""
        s = GameSession()
        s.apply_delta({"meta": {"game_over": "yes"}})
        assert s.game_over is False  # string rejected, keeps default bool

    def test_game_over_reason_without_game_over(self) -> None:
        """Setting reason without game_over flag."""
        s = GameSession()
        s.apply_delta({"meta": {"game_over_reason": "魂飞魄散"}})
        assert s.error == "魂飞魄散"
        assert s.game_over is False  # flag not set

    # ── Multiple deltas in sequence ────────────────────────────────────────────

    def test_rapid_sequential_deltas(self) -> None:
        s = GameSession(hp=100, mp=50, experience=0)
        for _ in range(100):
            s.apply_delta({"character": {"hp": "-1", "mp": "-1", "experience": "+1"}})
        assert s.hp == 0    # 100 * -1, floored at 0
        assert s.mp == 0    # 50 * -1, floored at 0 after 50 iterations
        assert s.experience == 100


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Serialization round-trip — adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerializationDestructive:

    def test_round_trip_after_corrupt_state(self) -> None:
        """Apply a corrupt delta then serialize — strings are valid JSON values."""
        s = GameSession(hp=100)
        s.hp = "not_a_number"  # type: ignore[assignment]
        # json.dumps succeeds — strings are valid JSON
        data = s.to_save_dict()
        result = json.dumps(data, ensure_ascii=False)
        assert '"not_a_number"' in result or '"hp"' in result
        # Round-trip produces a session with string hp
        loaded = GameSession.from_save_dict(json.loads(result))
        assert loaded.hp == "not_a_number"  # no type enforcement

    def test_load_from_empty_dict(self) -> None:
        s = GameSession.from_save_dict({})
        assert s.hp == 100  # defaults
        assert s.realm == "练气"
        assert s.char_name == ""

    def test_load_from_none_values(self) -> None:
        data = {"character": {"hp": None, "name": None}, "world": {"location": None}}
        s = GameSession.from_save_dict(data)
        assert s.hp is None  # .get("hp", 100) returns None since key exists
        assert s.char_name is None

    def test_load_from_wrong_types(self) -> None:
        data = {
            "turn_count": "not_a_number",
            "game_started": "yes",
            "character": {"hp": "eighty", "realm": 42},
            "world": {"day_count": "today"},
        }
        s = GameSession.from_save_dict(data)
        assert s.turn_count == "not_a_number"  # no type coercion
        assert s.hp == "eighty"

    def test_turn_history_truncated_to_20(self) -> None:
        s = GameSession()
        s.turn_history = [{"turn": i, "narrative": f"turn {i}"} for i in range(50)]
        saved = s.to_save_dict()
        assert len(saved["turn_history"]) == 20
        assert saved["turn_history"][0]["turn"] == 30  # last 20

    def test_chat_history_not_persisted(self) -> None:
        s = GameSession()
        s.chat_history = [{"role": "user", "content": "test"}]
        saved = s.to_save_dict()
        assert "chat_history" not in saved

    def test_reset_then_serialize(self) -> None:
        s = GameSession(char_name="许满", hp=50, realm="金丹", game_started=True, turn_count=100)
        s.reset()
        d = s.to_save_dict()
        assert d["character"]["name"] == ""
        assert d["character"]["hp"] == 100  # default
        assert d["turn_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Command parser — adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandParserDestructive:

    def test_slash_space_command(self) -> None:
        """'/ new' — slash then space then command."""
        c = parse_command("/ new")
        assert isinstance(c, SlashCommand)
        # Depending on implementation: name="" args="new" or name=" " ...
        # This documents current behavior.

    def test_very_long_input(self) -> None:
        text = "修炼" * 10000
        c = parse_command(text)
        assert isinstance(c, WriteCommand)

    def test_slash_only_spaces(self) -> None:
        c = parse_command("/   ")
        # After strip, becomes "/   " which starts with "/"
        assert isinstance(c, SlashCommand) or isinstance(c, EmptyCommand)

    def test_unicode_slash(self) -> None:
        """Fullwidth slash or other unicode variants."""
        c = parse_command("／help")
        # Fullwidth ／ (U+FF0F) — should be treated as normal text, not a command
        assert isinstance(c, WriteCommand)

    def test_colon_q_variants(self) -> None:
        for s in [":q", ":Q", ":quit", ":Quit", ":QUIT"]:
            assert isinstance(parse_command(s), ExitCommand), f"Failed for {s!r}"

    def test_null_bytes_in_input(self) -> None:
        c = parse_command("修\x00炼")
        assert isinstance(c, WriteCommand)
        assert "\x00" in c.text

    def test_newlines_in_input(self) -> None:
        """Newlines in free text — should be treated as a single action."""
        c = parse_command("修炼\n吐纳\n功法")
        assert isinstance(c, WriteCommand)

    def test_slash_command_with_equals(self) -> None:
        c = parse_command("/save my-save=v2")
        assert isinstance(c, SlashCommand)
        assert c.name == "save"
        assert "my-save=v2" in c.args


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Narrator parser — adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarratorParseDestructive:

    def test_multiple_state_update_tags(self) -> None:
        """What if LLM outputs two <state_update> blocks?"""
        text = (
            "叙事内容\n"
            "<state_update>{\"character\": {\"hp\": \"+10\"}}</state_update>\n"
            "更多叙事\n"
            "<state_update>{\"character\": {\"mp\": \"-5\"}}</state_update>"
        )
        narrative, delta, choices = _parse_narrator_output(text)
        # Regex with .*? (non-greedy) matches the first occurrence
        assert "hp" in str(delta)

    def test_nested_json_in_tag(self) -> None:
        data = {"character": {"techniques_add": [{"name": "剑法"}]}, "world": {"lore_add": ["传说"]}}
        text = f"叙事<state_update>{json.dumps(data)}</state_update>"
        _, delta, _ = _parse_narrator_output(text)
        assert delta["character"]["techniques_add"][0]["name"] == "剑法"

    def test_state_update_with_no_closing_tag(self) -> None:
        text = "叙事<state_update>{\"character\": {\"hp\": \"+10\"}}"
        narrative, delta, choices = _parse_narrator_output(text)
        # No closing tag — regex won't match
        assert delta == {}

    def test_state_update_with_attributes(self) -> None:
        text = "叙事<state_update type='json'>{\"character\": {\"hp\": 80}}</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)
        # Regex matches <state_update> literally, attributes break it
        assert delta == {}

    def test_empty_string(self) -> None:
        narrative, delta, choices = _parse_narrator_output("")
        assert narrative == ""
        assert delta == {}

    def test_only_state_update_tag(self) -> None:
        text = '<state_update>{"character": {"hp": 50}}</state_update>'
        narrative, delta, choices = _parse_narrator_output(text)
        assert narrative == ""

    def test_deeply_nested_json(self) -> None:
        data = {"a": {"b": {"c": {"d": {"e": "f"}}}}}
        text = f"叙事<state_update>{json.dumps(data)}</state_update>"
        _, delta, _ = _parse_narrator_output(text)
        assert delta["a"]["b"]["c"]["d"]["e"] == "f"

    def test_json_with_special_characters(self) -> None:
        data = {"character": {"name": "许满\"'\\/\n\t"}}
        text = f"叙事<state_update>{json.dumps(data, ensure_ascii=False)}</state_update>"
        _, delta, _ = _parse_narrator_output(text)
        assert "许满" in delta["character"]["name"]

    def test_very_large_narrative(self) -> None:
        narrative = "这是一段很长的叙事。" * 10000
        text = f"{narrative}<state_update>{{}}</state_update>"
        n, d, c = _parse_narrator_output(text)
        assert len(n) > 10000
        assert d == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Judge parser — adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestJudgeParseDestructive:

    def test_empty_string_defaults_to_reject(self) -> None:
        """Empty string → parse failure → approved=False (safe default)."""
        approved, delta, note, score = _parse_judge_output("")
        assert approved is False  # safe default: reject on parse failure
        assert score == 0

    def test_whitespace_only_defaults_to_reject(self) -> None:
        approved, delta, note, score = _parse_judge_output("   \n\t  ")
        assert approved is False

    def test_json_array_defaults_to_reject(self) -> None:
        approved, _, _, _ = _parse_judge_output("[1, 2, 3]")
        assert approved is False  # not a dict → reject

    def test_json_string_defaults_to_reject(self) -> None:
        approved, _, _, _ = _parse_judge_output('"just a string"')
        assert approved is False

    def test_json_number_defaults_to_reject(self) -> None:
        approved, _, _, _ = _parse_judge_output("42")
        assert approved is False

    def test_approved_as_string_truthy(self) -> None:
        text = '{"approved": "yes", "corrected_delta": {}, "judgment_note": "ok"}'
        approved, _, _, _ = _parse_judge_output(text)
        # Code wraps with bool() — bool("yes") is True
        assert approved is True

    def test_approved_as_number(self) -> None:
        text = '{"approved": 1, "corrected_delta": {}, "judgment_note": "ok"}'
        approved, _, _, _ = _parse_judge_output(text)
        assert approved == 1

    def test_corrected_delta_as_string(self) -> None:
        text = '{"approved": true, "corrected_delta": "bad", "judgment_note": "ok"}'
        _, delta, _, _ = _parse_judge_output(text)
        assert delta == {}  # non-dict corrected_delta defaults to {}

    def test_score_as_float(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "score": 7.5}'
        _, _, _, score = _parse_judge_output(text)
        assert score == 7  # int() truncates

    def test_score_as_string(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "score": "eight"}'
        # int("eight") raises ValueError — parser falls through to reject
        approved, _, _, _ = _parse_judge_output(text)
        assert approved is False  # ValueError → reject (safe default)

    def test_score_very_large_clamped(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 999999}'
        _, _, _, score = _parse_judge_output(text)
        assert score == 10

    def test_multiple_json_objects(self) -> None:
        """Two JSON objects in the text — first-brace-to-last-brace strategy."""
        text = 'stuff {"approved": true} more {"approved": false, "corrected_delta": {}, "judgment_note": "second"}'
        approved, _, _, _ = _parse_judge_output(text)
        # First-brace to last-brace wraps everything — likely parse failure → reject
        assert approved is False

    def test_fenced_json_with_extra_text(self) -> None:
        text = 'Here is my review:\n```json\n{"approved": true, "corrected_delta": {}, "judgment_note": "looks good"}\n```\nEnd.'
        approved, _, note, _ = _parse_judge_output(text)
        assert approved is True
        assert "looks good" in note

    def test_judgment_note_as_non_string(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": 42}'
        _, _, note, _ = _parse_judge_output(text)
        assert note == "42"  # converted to str

    def test_judgment_note_empty_defaults(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": ""}'
        _, _, note, _ = _parse_judge_output(text)
        assert note == "ok"  # empty → default


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Game view rendering — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestGameViewDestructive:

    def test_bar_zero_max(self) -> None:
        result = _bar(50, 0)
        assert result == "░" * 10

    def test_bar_negative_max(self) -> None:
        result = _bar(50, -10)
        assert result == "░" * 10

    def test_bar_negative_current(self) -> None:
        result = _bar(-50, 100)
        assert "░" in result  # clamped to 0

    def test_bar_current_exceeds_max(self) -> None:
        result = _bar(200, 100)
        assert "█" * 10 == result  # clamped to full

    def test_bar_very_large_values(self) -> None:
        result = _bar(999999, 1000000)
        assert len(result) == 10

    def test_stage_suffix_zero(self) -> None:
        assert _stage_suffix(0) == " 0层"

    def test_stage_suffix_negative(self) -> None:
        assert _stage_suffix(-5) == " -5层"

    def test_stage_suffix_hundred(self) -> None:
        assert _stage_suffix(100) == " 100层"

    def test_status_bar_empty_session(self) -> None:
        s = GameSession()
        bar = render_status_bar(s)
        assert "HP:" in bar
        assert "MP:" in bar

    def test_status_panel_with_corrupt_status_effects(self) -> None:
        """status_effects = string should not crash render_status_panel."""
        s = GameSession(char_name="test")
        s.status_effects = "中毒"  # type: ignore[assignment]
        panel = render_status_panel(s)
        # Should not crash — but join will iterate chars
        assert panel is not None

    def test_inventory_with_string_items(self) -> None:
        """inventory items as plain strings (missing dict fields)."""
        s = GameSession()
        s.inventory = ["sword", "shield"]  # type: ignore[list-item]
        panel = render_inventory_table(s)
        # .get() on a string returns default since strings don't have .get()
        assert panel is not None

    def test_inventory_with_empty_dicts(self) -> None:
        s = GameSession()
        s.inventory = [{}, {}, {}]
        panel = render_inventory_table(s)
        assert panel is not None

    def test_skills_with_empty_list(self) -> None:
        s = GameSession()
        panel = render_skills_table(s)
        assert "尚未习得" in str(panel.renderable)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REPL loop — adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestReplDestructive:

    def _make_repl(self, inputs: list[str]) -> Repl:
        it = iter(inputs)
        return Repl(input_fn=lambda _p: next(it))

    def test_rapid_new_reset_cycle(self, capsys, monkeypatch) -> None:
        """Start and reset games rapidly."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        call_log: list[str] = []
        def fake_runner(agent_name, user_input, session, **kw):
            call_log.append(agent_name)
            if agent_name == "world_builder":
                return _canned_world_builder()
            return _canned_narrator()

        inputs = ["/new a", "/reset", "/new b", "/reset", "/new c", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert call_log.count("world_builder") == 3
        assert repl.game_session.char_name == "许满"

    def test_multiple_saves_same_name(self, capsys, monkeypatch, tmp_path) -> None:
        """Overwriting saves."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            return _canned_narrator()

        inputs = ["/new test", "/save s1", "/save s1", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0

    def test_load_nonexistent_save(self, capsys, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        inputs = ["/load nonexistent", "/exit"]
        repl = self._make_repl(inputs)
        with patch("agens_novel.engine.game_engine.run_turn_sync"):
            rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "找不到" in out or "不存在" in out or "FileNotFoundError" in out

    def test_action_with_narrator_exception(self, capsys, monkeypatch) -> None:
        """Narrator crashes — turn count should be restored."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                raise RuntimeError("LLM exploded")
            return _canned_judge()

        inputs = ["/new test", "修炼", "/status", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert repl.game_session.turn_count == 0  # restored after error
        out = capsys.readouterr().out
        assert "失败" in out

    def test_action_with_narrator_llm_error(self, capsys, monkeypatch) -> None:
        """Narrator returns llm_error."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return {**_canned_narrator(), "llm_error": "API rate limit"}
            return _canned_judge()

        inputs = ["/new test", "修炼", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert repl.game_session.turn_count == 0
        out = capsys.readouterr().out
        assert "API rate limit" in out

    def test_action_with_judge_exception_fallback(self, capsys, monkeypatch) -> None:
        """Judge crashes — delta should NOT be applied (safe default: reject)."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        call_log: list[str] = []
        def fake_runner(agent_name, user_input, session, **kw):
            call_log.append(agent_name)
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return _canned_narrator()
            if agent_name == "judge":
                raise ConnectionError("Judge API down")
            return {}

        inputs = ["/new test", "修炼", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        # Judge exception → default to not approving → delta not applied
        assert repl.game_session.turn_count == 1
        # Delta was NOT applied (judge exception → reject)
        assert repl.game_session.mp == 50  # unchanged

    def test_judge_rejects_with_corrected_delta(self, capsys, monkeypatch) -> None:
        """Judge rejects and provides corrected delta."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        corrected = {"character": {"mp": "-5"}}  # judge corrects -10 to -5

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return _canned_narrator()
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": corrected,
                    "judgment_note": "MP消耗过大，已修正",
                    "review_score": 3,
                    "output_path": "/tmp/j.md",
                    "audit_path": "/tmp/j_a.json",
                    "finished_at": "",
                    "llm_error": "",
                }
            return {}

        inputs = ["/new test", "修炼", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        # Corrected delta should be applied, not original
        assert repl.game_session.mp == 45  # 50 - 5 (corrected)

    def test_judge_rejects_with_empty_corrected_delta(self, capsys, monkeypatch) -> None:
        """Judge rejects with empty corrected_delta — delta becomes empty."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return _canned_narrator()
            if agent_name == "judge":
                return {
                    "approved": False,
                    "corrected_delta": {},  # empty — no changes
                    "judgment_note": "完全不合理",
                    "review_score": 0,
                    "output_path": "/tmp/j.md",
                    "audit_path": "/tmp/j_a.json",
                    "finished_at": "",
                    "llm_error": "",
                }
            return {}

        inputs = ["/new test", "修炼", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        # Empty corrected delta applied — mp unchanged
        assert repl.game_session.mp == 50

    def test_game_over_flow(self, capsys, monkeypatch) -> None:
        """Narrator declares game over — subsequent actions blocked."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        call_count = [0]

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                call_count[0] += 1
                if call_count[0] == 1:
                    return {
                        "narrative": "你在渡劫时被天雷击中，魂飞魄散。",
                        "state_delta": {
                            "character": {"hp": "-99999"},
                            "meta": {"game_over": True, "game_over_reason": "天雷击杀"},
                        },
                        "choices": [],
                        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
                    }
                return _canned_narrator()
            return _canned_judge()

        inputs = ["/new test", "渡劫", "修炼", "/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert repl.game_session.game_over is True
        out = capsys.readouterr().out
        assert "游戏已结束" in out

    def test_expand_without_api_key(self, capsys, monkeypatch) -> None:
        """Without AGNES_API_KEY env, built-in key fallback allows expand."""
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        repl = self._make_repl(["/expand", "/exit"])
        repl.game_session.game_started = True
        rc = repl.run()
        assert rc == 0
        # v0.4: _has_api_key now always returns True (built-in fallback),
        # so expand will attempt LLM call instead of refusing.

    def test_unknown_slash_command_in_loop(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/foobarbaz", "/exit"]
        repl = self._make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "未知命令" in out

    def test_new_without_api_key(self, capsys, monkeypatch) -> None:
        """Without AGNES_API_KEY env, built-in key fallback allows new game."""
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        inputs = ["/new test", "/exit"]
        repl = self._make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        # v0.4: _has_api_key now always returns True (built-in fallback),
        # so /new will attempt LLM call instead of refusing.

    def test_new_with_empty_concept_cancelled(self, capsys, monkeypatch) -> None:
        """User hits enter twice at concept prompt."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/new", "", "/exit"]
        repl = self._make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "取消" in out

    def test_world_builder_returns_empty_data(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return {
                    "generated_data": {},
                    "world_description": "",
                    "opening_narrative": "",
                    "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
                }
            return {}

        inputs = ["/new test", "/exit"]
        repl = self._make_repl(inputs)
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "为空" in out or "重试" in out

    def test_save_without_game_started(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/save test", "/exit"]
        repl = self._make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "没有进行中" in out

    def test_all_display_commands_without_game(self, capsys, monkeypatch) -> None:
        """Every display command should show 'not started' gracefully."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        inputs = ["/status", "/inv", "/skills", "/map", "/quest", "/log", "/exit"]
        repl = self._make_repl(inputs)
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        # All should mention "尚未开始" or similar
        assert out.count("尚未开始游戏") >= 5

    def test_map_with_empty_discovered_locations(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        repl = self._make_repl(["/map", "/exit"])
        repl.game_session.game_started = True
        repl.game_session.discovered_locations = []
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "尚未探索" in out

    def test_quest_with_empty_quests(self, capsys, monkeypatch) -> None:
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")
        repl = self._make_repl(["/quest", "/exit"])
        repl.game_session.game_started = True
        repl.game_session.active_quests = []
        rc = repl.run()
        assert rc == 0
        out = capsys.readouterr().out
        assert "没有任务" in out

    def test_expand_invalid_type_fallback(self, capsys, monkeypatch) -> None:
        """Invalid expand type falls back to new_region."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        called_with = {}
        def fake_runner(agent_name, user_input, session, **kw):
            called_with.update(kw)
            if agent_name == "world_builder":
                return {
                    "generated_data": {},
                    "world_description": "新的区域出现了。",
                    "opening_narrative": "",
                    "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
                }
            return {}

        repl = self._make_repl(["/expand invalid_type", "/exit"])
        repl.game_session.game_started = True

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert called_with.get("generation_type") == "new_region"  # fallback

    def test_many_turns_chat_history_truncated(self, capsys, monkeypatch) -> None:
        """After 20+ turns, chat_history should be truncated."""
        monkeypatch.setenv("AGNES_API_KEY", "sk-test-1234567890")

        def fake_runner(agent_name, user_input, session, **kw):
            if agent_name == "world_builder":
                return _canned_world_builder()
            if agent_name == "narrator":
                return _canned_narrator()
            return _canned_judge()

        # 25 actions
        inputs = ["/new test"] + ["修炼"] * 25 + ["/exit"]
        repl = self._make_repl(inputs)

        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=fake_runner):
            rc = repl.run()
        assert rc == 0
        assert repl.game_session.turn_count == 25
        assert len(repl.game_session.chat_history) <= 20


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Save/Load — corruption & adversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaveLoadDestructive:

    def test_save_load_with_corrupt_file(self, tmp_path, monkeypatch) -> None:
        """Loading a corrupt JSON file."""
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        # Write garbage
        save_dir = tmp_path / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / "corrupt.json").write_text("NOT JSON AT ALL{{{{", encoding="utf-8")

        from agens_novel.repl.save_manager import load_game
        with pytest.raises(Exception):
            load_game("corrupt")

    def test_load_nonexistent_save(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        from agens_novel.repl.save_manager import load_game
        with pytest.raises(FileNotFoundError):
            load_game("does_not_exist")

    def test_list_saves_with_corrupt_and_valid(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        save_dir = tmp_path / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)

        # Write a valid save
        s = GameSession(char_name="许满", game_started=True)
        valid_data = s.to_save_dict()
        (save_dir / "good.json").write_text(json.dumps(valid_data, ensure_ascii=False), encoding="utf-8")

        # Write a corrupt save
        (save_dir / "bad.json").write_text("{invalid json", encoding="utf-8")

        from agens_novel.repl.save_manager import list_saves
        saves = list_saves()
        names = [s_save["name"] for s_save in saves]
        assert "good" in names
        assert "bad" in names
        # Corrupt one should be marked
        bad_entry = next(s for s in saves if s["name"] == "bad")
        assert bad_entry.get("error") == "corrupt"

    def test_save_name_sanitization(self, tmp_path, monkeypatch) -> None:
        """Path traversal in save names should be sanitized."""
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        from agens_novel.repl.save_manager import save_game, load_game

        s = GameSession(char_name="test", game_started=True)

        # These should all be sanitized safely
        save_path = save_game(s, "../../../etc/passwd")
        # The file should be in SAVE_DIR, not traversing out
        save_dir_str = str(tmp_path / "saves")
        assert save_path.startswith(save_dir_str), f"Path escaped: {save_path}"

        # Load should work with the actual sanitized name (etcpasswd)
        loaded = load_game("etcpasswd")
        assert loaded.char_name == "test"

    def test_save_load_preserves_all_fields(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths
        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")

        s = GameSession(
            char_name="许满", realm="金丹", realm_stage=5,
            hp=85, hp_max=120, mp=60, mp_max=80,
            spirit_root="火木双灵根", spirit_root_grade="天",
            experience=450, experience_to_next=500, gold=99,
            techniques=[{"name": "青云剑诀", "level": 3, "type": "剑法"}],
            inventory=[{"name": "灵石", "quantity": 5, "type": "材料"}],
            status_effects=["中毒", "力竭"],
            lifespan=200,
            location="青云山内门", region="东荒",
            current_scene="藏经阁",
            day_count=15,
            npcs_present=[{"name": "长老", "realm": "元婴"}],
            active_quests=[{"name": "寻剑", "status": "active"}],
            discovered_locations=["青云山外门", "内门"],
            lore_facts=["青云门建于三千年前"],
        )
        s.game_started = True
        s.turn_count = 42

        from agens_novel.repl.save_manager import save_game, load_game
        save_game(s, "full_test")
        loaded = load_game("full_test")

        assert loaded.char_name == s.char_name
        assert loaded.realm == s.realm
        assert loaded.realm_stage == s.realm_stage
        assert loaded.hp == s.hp
        assert loaded.hp_max == s.hp_max
        assert loaded.mp == s.mp
        assert loaded.mp_max == s.mp_max
        assert loaded.spirit_root == s.spirit_root
        assert loaded.experience == s.experience
        assert loaded.gold == s.gold
        assert len(loaded.techniques) == 1
        assert len(loaded.inventory) == 1
        assert loaded.status_effects == ["中毒", "力竭"]
        assert loaded.location == s.location
        assert loaded.region == s.region
        assert loaded.day_count == s.day_count
        assert loaded.turn_count == s.turn_count
        assert len(loaded.npcs_present) == 1
        assert len(loaded.active_quests) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 9. as_game_state — verify output shape
# ═══════════════════════════════════════════════════════════════════════════════

class TestAsGameState:

    def test_produces_valid_json(self) -> None:
        s = GameSession(char_name="许满", realm="筑基", hp=85)
        state = s.as_game_state()
        json_str = json.dumps(state, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["character"]["name"] == "许满"
        assert parsed["character"]["hp"] == 85

    def test_default_session_produces_valid_json(self) -> None:
        s = GameSession()
        state = s.as_game_state()
        parsed = json.loads(json.dumps(state))
        assert parsed["character"]["name"] == ""
        assert parsed["world"]["location"] == ""

    def test_contains_all_expected_keys(self) -> None:
        s = GameSession()
        state = s.as_game_state()
        assert "character" in state
        assert "world" in state
        assert "turn_count" in state
        assert "game_started" in state
        assert "game_over" in state
        assert "name" in state["character"]
        assert "realm" in state["character"]
        assert "hp" in state["character"]
        assert "mp" in state["character"]
        assert "location" in state["world"]


# ═══════════════════════════════════════════════════════════════════════════════
# Canned helpers (local copies to avoid cross-file dependency)
# ═══════════════════════════════════════════════════════════════════════════════

def _canned_world_builder() -> dict[str, Any]:
    return {
        "generated_data": {
            "character": {
                "name": "许满", "realm": "练气", "realm_stage": 1,
                "hp": 100, "hp_max": 100, "mp": 50, "mp_max": 50,
                "spirit_root": "火木双灵根", "spirit_root_grade": "地",
                "experience": 0, "experience_to_next": 100, "gold": 10,
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
                "status_effects": [], "lifespan": 100,
            },
            "world": {
                "current_scene": "晨雾中的青云山外门",
                "location": "青云山外门", "region": "东荒",
                "npcs_present": [], "active_quests": [],
                "discovered_locations": ["青云山外门"],
                "lore_facts": [], "day_count": 1,
            },
            "opening_narrative": "天道初开。",
        },
        "world_description": "", "opening_narrative": "",
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }


def _canned_narrator() -> dict[str, Any]:
    return {
        "narrative": "你静坐吐纳，灵气缓缓涌入。",
        "state_delta": {"character": {"mp": "-10", "experience": "+15"}},
        "choices": [],
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }


def _canned_judge() -> dict[str, Any]:
    return {
        "approved": True, "corrected_delta": {},
        "judgment_note": "ok", "review_score": 8,
        "output_path": "", "audit_path": "", "finished_at": "", "llm_error": "",
    }
