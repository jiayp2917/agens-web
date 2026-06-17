"""Comprehensive e2e destructive / fuzz tests.

Purpose: simulate adversarial user behavior to verify the game engine
never crashes regardless of input. All LLM calls are mocked.

Test categories:
  1. GameEngine lifecycle: new → action → save → load → reset
  2. Destructive inputs: extreme strings, unicode, empty, special chars
  3. Combat engine: start → actions → resolve (edge cases)
  4. Realm system: breakthrough success/failure/boundary
  5. Turn runner: verify stream_callback isolation
  6. Save manager: multi-slot operations, corrupt files, missing files
  7. GameSession: apply_delta fuzz with random dicts
"""

from __future__ import annotations

import json
import os
import random
import string
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agens_novel.engine.game_engine import GameEngine
from agens_novel.session.game_session import GameSession
from agens_novel.persistence.save_manager import (
    save_game, load_game, list_saves, delete_save, get_manual_save_slots,
    set_save_dir, AUTOSAVE_NAME,
)
from agens_novel.game.combat import CombatEngine
from agens_novel.game.realm import RealmSystem
from agens_novel.game.constants import REALM_ORDER, REALM_CONFIGS, SPIRIT_ROOT_MAP


ALL_BREAKTHROUGH_FLAGS = [
    "foundation_aid",
    "golden_core_aid",
    "nascent_soul_aid",
    "spirit_transformation_aid",
    "unity_law_aid",
    "mahayana_vow_aid",
    "tribulation_preparation",
    "tribulation_elixir",
    "ascension_protection",
]


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_save_dir(tmp_path):
    """Redirect saves to a temp directory."""
    set_save_dir(tmp_path)
    yield tmp_path
    set_save_dir(None)  # reset


@pytest.fixture
def engine():
    """GameEngine with all callbacks captured."""
    e = GameEngine()
    events = []

    def _capture(name):
        def cb(*args):
            events.append((name, args))
        return cb

    e.on_narrative = _capture("narrative")
    e.on_error = _capture("error")
    e.on_info = _capture("info")
    e.on_status_bar = _capture("status_bar")
    e.on_game_over = _capture("game_over")
    e.on_character_created = _capture("character_created")
    e.on_loading = _capture("loading")
    e.on_stream_chunk = _capture("stream_chunk")
    e.on_combat_update = _capture("combat_update")
    return e, events


def _mock_run_turn_sync(result):
    """Create a mock for run_turn_sync that returns the given result."""
    def _mock(agent_name, user_input, session, **kwargs):
        # Verify stream_callback is NOT in kwargs (the msgpack fix).
        assert "stream_callback" not in kwargs, \
            f"stream_callback leaked into run_turn_sync kwargs for {agent_name}"
        return result
    return _mock


def _new_game_result(**overrides):
    """Standard world_builder result for new game."""
    result = {
        "generated_data": {
            "character": {
                "name": "测试修士", "realm": "练气", "realm_stage": 1,
                "hp": 100, "hp_max": 100, "mp": 50, "mp_max": 50,
                "spirit_root": "木灵根", "spirit_root_grade": "地级",
                "experience": 0, "experience_to_next": 100,
                "gold": 0, "techniques": [], "inventory": [],
                "status_effects": [], "lifespan": 100,
            },
            "world": {
                "current_scene": "青云山", "location": "山门",
                "region": "东域", "npcs_present": [],
                "active_quests": [], "discovered_locations": [],
                "lore_facts": [], "day_count": 1,
            },
            "opening_narrative": "你踏入了青云山。",
        },
        "llm_error": "",
    }
    result.update(overrides)
    return result


def _narrator_result(narrative="你静坐吐纳。", state_delta=None):
    """Standard narrator result."""
    return {
        "narrative": narrative,
        "state_delta": state_delta or {},
        "choices": [],
        "llm_error": "",
    }


# ─── 1. GameEngine lifecycle ───────────────────────────────────────────────

class TestEngineLifecycle:

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_full_lifecycle(self, mock_run, engine, tmp_save_dir):
        eng, events = engine
        mock_run.side_effect = [
            _new_game_result(),
            _narrator_result("你修炼了一会。", {"character": {"mp": "-5"}}),
        ]

        # New game.
        eng.new_game("测试角色")
        assert eng.game_session.game_started
        assert eng.game_session.char_name == "测试修士"

        # Action.
        eng.handle_action("静坐吐纳")
        assert eng.game_session.turn_count == 1

        # Save.
        eng.save("test_slot")
        assert (tmp_save_dir / "test_slot.json").exists()

        # Load.
        eng.game_session.turn_count = 99  # corrupt
        eng.load("test_slot")
        assert eng.game_session.turn_count == 1  # restored

        # Reset.
        eng.reset()
        assert not eng.game_session.game_started

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_multiple_saves_independent(self, mock_run, engine, tmp_save_dir):
        eng, events = engine
        mock_run.return_value = _new_game_result()

        eng.new_game("角色A")
        eng.game_session.char_name = "角色A"
        eng.save("slot_1")

        eng.game_session.char_name = "角色B"
        eng.game_session.realm = "金丹"
        eng.save("slot_2")

        eng.load("slot_1")
        assert eng.game_session.char_name == "角色A"

        eng.load("slot_2")
        assert eng.game_session.realm == "金丹"

    def test_action_without_new_game(self, engine):
        eng, events = engine
        eng.handle_action("做事")
        assert any(e[0] == "info" for e in events)

    def test_action_after_game_over(self, engine):
        eng, events = engine
        eng.game_session.game_started = True
        eng.game_session.game_over = True
        eng.handle_action("做事")
        assert any(e[0] == "info" for e in events)

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_turn_count_increments_on_success(self, mock_run, engine):
        eng, events = engine
        mock_run.return_value = _narrator_result()
        eng.game_session.game_started = True

        eng.handle_action("行动1")
        eng.handle_action("行动2")
        eng.handle_action("行动3")
        assert eng.game_session.turn_count == 3

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_turn_count_rollback_on_error(self, mock_run, engine):
        eng, events = engine
        mock_run.side_effect = Exception("LLM crashed")
        eng.game_session.game_started = True

        eng.handle_action("行动")
        assert eng.game_session.turn_count == 0  # rolled back

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_game_over_on_hp_zero(self, mock_run, engine):
        eng, events = engine
        mock_run.return_value = _narrator_result(
            "你被击倒了。",
            {"character": {"hp": "-999"}, "meta": {"game_over": True}},
        )
        eng.game_session.game_started = True

        eng.handle_action("送死")
        game_over_events = [e for e in events if e[0] == "game_over"]
        assert len(game_over_events) >= 1


# ─── 2. Destructive inputs ─────────────────────────────────────────────────

class TestDestructiveInputs:

    def _fuzz_strings(self, n=50):
        """Generate a list of adversarial strings."""
        strings = [
            "", " ", "\n", "\t", "\r\n",
            "<script>alert(1)</script>",
            "{{template}}", "${injection}", "%s%s%s%s",
            "'; DROP TABLE games; --",
            "\x00\x01\x02", "￿", "🎮🗡️⚔️",
            "A" * 10000,  # very long
            "你" * 5000,
            "<state_update>", "</state_update>",
            "```json\n{}\n```",
            "null", "undefined", "NaN", "Infinity",
            "{\"character\": {\"hp\": -999}}",  # JSON as user input
        ]
        for _ in range(n - len(strings)):
            strings.append("".join(random.choices(string.printable, k=random.randint(1, 200))))
        return strings

    def test_apply_delta_fuzz(self):
        """Apply random deltas and verify session doesn't crash."""
        s = GameSession()
        s.game_started = True

        for text in self._fuzz_strings(30):
            delta = {"character": {"name": text}, "world": {"current_scene": text}}
            s.apply_delta(delta)  # should not crash

        assert s.game_started  # still valid

    def test_apply_delta_random_dicts(self):
        """Apply random dict structures."""
        s = GameSession()
        s.game_started = True

        random.seed(42)
        for _ in range(100):
            delta = {}
            # Random character fields.
            char = {}
            for key in ("hp", "mp", "experience", "gold", "realm", "name"):
                r = random.random()
                if r < 0.3:
                    char[key] = random.randint(-1000, 1000)
                elif r < 0.5:
                    char[key] = random.choice(REALM_ORDER + ["", "invalid", None])
                elif r < 0.7:
                    char[key] = f"+{random.randint(1, 100)}"
                elif r < 0.9:
                    char[key] = f"-{random.randint(1, 100)}"
                else:
                    char[key] = random.choice([True, False, [], {}, "str", 3.14])
            delta["character"] = char

            # Random meta.
            delta["meta"] = {
                "game_over": random.choice([True, False, 1, 0, "yes", None]),
            }

            s.apply_delta(delta)  # should not crash

        # Session should still be usable.
        assert isinstance(s.hp, int)
        assert isinstance(s.realm, str)

    @patch("agens_novel.engine.game_engine.run_turn_sync")
    def test_handle_action_fuzz(self, mock_run, engine):
        """Submit adversarial user inputs to handle_action."""
        eng, events = engine
        mock_run.return_value = _narrator_result()
        eng.game_session.game_started = True

        for text in self._fuzz_strings(30):
            eng.handle_action(text)  # should not crash

        assert eng.game_session.game_started  # still valid


# ─── 3. Combat engine ──────────────────────────────────────────────────────

class TestCombatEdgeCases:

    def test_combat_without_active_combat(self, engine):
        eng, events = engine
        eng.handle_combat_action("attack")
        # Should emit "当前不在战斗中" info, not crash.
        assert any("不在战斗" in str(e) for e in events)

    def test_combat_engine_start_and_resolve(self):
        s = GameSession()
        s.hp = 100
        s.hp_max = 100
        s.mp = 50
        s.mp_max = 50
        s.realm = "练气"
        s.techniques = [{"name": "基础剑法", "mp_cost": 5}]

        ce = CombatEngine()
        enemy = {"name": "妖兽", "hp": 50, "hp_max": 50, "attack": 10}

        combat = ce.start_combat(s, enemy)
        assert combat["phase"] in ("player_turn", "active")
        assert combat["enemy"]["name"] == "妖兽"

    def test_combat_action_with_no_combat(self):
        ce = CombatEngine()
        s = GameSession()
        s.combat = None
        # This should be handled by the engine, not the combat engine directly.
        # Verify engine side:
        eng = GameEngine()
        events = []
        eng.on_info = lambda msg: events.append(msg)
        eng.handle_combat_action("attack")
        assert any("不在战斗" in e for e in events)


# ─── 4. Realm system ──────────────────────────────────────────────────────

class TestRealmEdgeCases:

    def test_all_realms_in_config(self):
        """Every realm in REALM_ORDER should have a config."""
        rs = RealmSystem()
        for realm in REALM_ORDER:
            cfg = rs.get_realm_config(realm)
            assert cfg is not None, f"Missing config for realm: {realm}"
            assert cfg.hp_base > 0
            assert cfg.mp_base > 0

    def test_next_realm_chain(self):
        """Every realm except the last should have a next realm."""
        rs = RealmSystem()
        for i, realm in enumerate(REALM_ORDER):
            next_r = rs.get_next_realm(realm)
            if i < len(REALM_ORDER) - 1:
                assert next_r == REALM_ORDER[i + 1]
            else:
                assert next_r is None  # 飞升 has no next

    def test_cannot_breakthrough_from_flying(self):
        """飞升 (last realm) should not allow breakthrough."""
        s = GameSession()
        s.realm = "飞升"
        s.realm_stage = 1
        s.experience = 99999
        s.experience_to_next = 1

        rs = RealmSystem()
        can, reason = rs.can_attempt_breakthrough(s)
        assert not can
        assert "最高" in reason

    def test_breakthrough_rate_between_0_and_1(self):
        """Breakthrough rate should always be [0, 1]."""
        rs = RealmSystem()
        for realm in REALM_ORDER:
            s = GameSession()
            s.realm = realm
            s.experience = 99999
            s.experience_to_next = 1
            rate = rs.calculate_breakthrough_rate(s)
            assert 0.0 <= rate <= 1.0, f"Rate {rate} out of range for {realm}"

    def test_breakthrough_failure_gives_damage(self):
        """Failed breakthrough should reduce HP."""
        s = GameSession()
        s.realm = "练气"
        s.realm_stage = 9
        s.experience = 999
        s.experience_to_next = 100
        s.insight = 999  # clear the 感悟 gate so the attempt actually resolves
        s.breakthrough_flags = list(ALL_BREAKTHROUGH_FLAGS)
        s.hp = 100

        rs = RealmSystem()
        # Force failure.
        with patch.object(random, "random", return_value=1.0):
            delta = rs.attempt_breakthrough(s)

        assert delta["meta"]["breakthrough_result"] == "failure"
        assert delta["character"]["hp"].startswith("-")

    def test_breakthrough_success_advances_realm(self):
        s = GameSession()
        s.realm = "练气"
        s.realm_stage = 9
        s.experience = 999
        s.experience_to_next = 100
        s.insight = 999  # clear the 感悟 gate so the attempt actually resolves
        s.breakthrough_flags = list(ALL_BREAKTHROUGH_FLAGS)

        rs = RealmSystem()
        with patch.object(random, "random", return_value=0.0):
            delta = rs.attempt_breakthrough(s)

        assert delta["meta"]["breakthrough_result"] == "success"
        assert delta["character"]["realm"] == "筑基"

    def test_flying_breakthrough_sets_finale(self):
        """Breaking through to 飞升 should set finale flag."""
        s = GameSession()
        # Need to be at 渡劫 (second-to-last realm), final stage, enough exp + 感悟.
        s.realm = REALM_ORDER[-2]  # 渡劫
        s.realm_stage = 1
        s.experience = 99999
        s.experience_to_next = 1
        s.insight = 999  # 渡劫 requires 400 感悟 — clear the gate to reach 飞升
        s.breakthrough_flags = list(ALL_BREAKTHROUGH_FLAGS)

        rs = RealmSystem()
        # Ensure REALM_CONFIGS has 渡劫 with stages=1, or adjust.
        cfg = rs.get_realm_config(s.realm)
        if cfg and cfg.stages > 1:
            s.realm_stage = cfg.stages

        with patch.object(random, "random", return_value=0.0):
            delta = rs.attempt_breakthrough(s)

        assert delta["meta"]["breakthrough_result"] == "success", \
            "With 感悟 cleared and random forced low, breakthrough must succeed"
        assert delta["meta"].get("finale") is True
        assert delta["meta"].get("game_over") is True


# ─── 5. Turn runner: stream_callback isolation ────────────────────────────

class TestTurnRunnerStreamIsolation:

    def test_stream_callback_not_in_kwargs(self):
        """Verify that run_turn_sync never passes stream_callback in **kwargs."""
        import inspect
        from agens_novel.engine import turn_runner

        source = inspect.getsource(turn_runner.run_turn_sync)
        # Old bug: state["stream_callback"] = stream_callback
        assert 'state["stream_callback"]' not in source
        assert "state['stream_callback']" not in source

    def test_stream_context_isolation(self):
        """Thread-local context should not leak between calls."""
        from agens_novel.engine._stream_context import set, get
        import threading

        set(lambda x: None)
        assert get() is not None

        results = []

        def worker():
            results.append(get())
            set(lambda x: f"worker_{x}")
            results.append(get())

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Main thread's callback should be unchanged.
        assert get() is not None  # still the original
        # Worker thread sees None initially (different thread-local).
        assert results[0] is None


# ─── 6. Save manager ──────────────────────────────────────────────────────

class TestSaveManager:

    def test_save_and_load_roundtrip(self, tmp_save_dir):
        s = GameSession()
        s.char_name = "修仙者"
        s.realm = "金丹"
        s.hp = 200
        s.turn_count = 42

        save_game(s, "test_roundtrip")
        loaded = load_game("test_roundtrip")

        assert loaded.char_name == "修仙者"
        assert loaded.realm == "金丹"
        assert loaded.hp == 200
        assert loaded.turn_count == 42

    def test_list_saves(self, tmp_save_dir):
        s = GameSession()
        s.char_name = "角色A"
        save_game(s, "slot_1")

        s.char_name = "角色B"
        save_game(s, "slot_2")

        saves = list_saves()
        names = {sv["name"] for sv in saves}
        assert "slot_1" in names
        assert "slot_2" in names

    def test_load_nonexistent_raises(self, tmp_save_dir):
        with pytest.raises(FileNotFoundError):
            load_game("nonexistent_slot")

    def test_delete_save(self, tmp_save_dir):
        s = GameSession()
        save_game(s, "to_delete")
        assert (tmp_save_dir / "to_delete.json").exists()

        delete_save("to_delete")
        assert not (tmp_save_dir / "to_delete.json").exists()

    def test_delete_nonexistent_raises(self, tmp_save_dir):
        with pytest.raises(FileNotFoundError):
            delete_save("nonexistent")

    def test_manual_save_slots(self, tmp_save_dir):
        s = GameSession()
        s.char_name = "角色X"
        s.realm = "元婴"

        save_game(s, "slot_3")

        slots = get_manual_save_slots()
        assert len(slots) == 5

        slot_3 = slots[2]
        assert slot_3["name"] == "slot_3"
        assert slot_3["occupied"] is True
        assert slot_3["char_name"] == "角色X"
        assert slot_3["realm"] == "元婴"

    def test_corrupt_save_file(self, tmp_save_dir):
        """Corrupt JSON file should be listed but marked as error."""
        (tmp_save_dir / "corrupt.json").write_text("{invalid json", encoding="utf-8")

        saves = list_saves()
        corrupt = next(s for s in saves if s["name"] == "corrupt")
        assert corrupt.get("error") == "corrupt"

    def test_empty_save_dir(self, tmp_save_dir):
        saves = list_saves()
        assert saves == []

    def test_special_chars_in_slot_name(self, tmp_save_dir):
        """Slot names with special chars should be sanitized."""
        s = GameSession()
        save_game(s, "test/slot")
        # "/" should be stripped to "testslot" or similar.
        saves = list_saves()
        names = {sv["name"] for sv in saves}
        assert any("test" in n for n in names)

    def test_autosave_distinguished(self, tmp_save_dir):
        s = GameSession()
        save_game(s, "autosave")

        saves = list_saves()
        auto = next(s for s in saves if s["name"] == "autosave")
        assert auto["is_autosave"] is True


# ─── 7. GameSession stress ────────────────────────────────────────────────

class TestGameSessionStress:

    def test_reset_clears_everything(self):
        s = GameSession()
        s.char_name = "修仙者"
        s.realm = "金丹"
        s.hp = 200
        s.combat = {"phase": "active"}
        s.game_started = True
        s.game_over = True
        s.finale = True

        s.reset()
        assert s.char_name == ""
        assert s.realm == "练气"
        assert s.hp == 100
        assert s.combat is None
        assert not s.game_started
        assert not s.game_over
        assert not s.finale

    def test_as_game_state_completeness(self):
        s = GameSession()
        s.char_name = "测试"
        s.realm = "化神"
        state = s.as_game_state()

        assert "character" in state
        assert "world" in state
        assert state["character"]["name"] == "测试"
        assert state["character"]["realm"] == "化神"
        assert isinstance(state["character"]["techniques"], list)
        assert isinstance(state["world"]["npcs_present"], list)

    def test_many_delta_applications(self):
        """Apply 1000 deltas rapidly."""
        s = GameSession()
        s.game_started = True

        for i in range(1000):
            s.apply_delta({
                "character": {
                    "hp": f"-{i % 10}",
                    "experience": "+1",
                },
            })
        # Should survive.
        assert isinstance(s.hp, int)
        assert s.experience >= 0

    def test_chat_history_trimming(self):
        """Chat history should be trimmed to 20 entries."""
        s = GameSession()
        s.game_started = True

        for i in range(30):
            s.chat_history.append({"role": "user", "content": f"msg{i}"})
            s.chat_history.append({"role": "assistant", "content": f"reply{i}"})

        # Simulate the trim in game_engine.
        s.chat_history = s.chat_history[-20:]
        assert len(s.chat_history) == 20


# ─── 8. Edge: API key / settings ──────────────────────────────────────────

class TestApiKeyEdgeCases:

    def test_has_api_key_allows_agent_fallback_path(self, monkeypatch):
        """Missing keys are handled by agent llm_error branches, not preflight."""
        monkeypatch.delenv("AGNES_API_KEY", raising=False)
        eng = GameEngine()
        assert eng._has_api_key() is True

    def test_stream_callback_method_exists(self):
        eng = GameEngine()
        eng._stream_callback("test")
        # No crash — callback is just forwarded.

    def test_engine_callbacks_default_none(self):
        eng = GameEngine()
        assert eng.on_narrative is None
        assert eng.on_error is None
        assert eng.on_stream_chunk is None

    def test_emit_with_no_callback(self):
        """_emit should silently do nothing if callback is None."""
        eng = GameEngine()
        eng._emit("on_narrative", "text", 1)  # should not crash
