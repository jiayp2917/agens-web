"""Destructive tests for the Android-first core runtime.

The terminal REPL product surface has been removed. These tests keep the
adversarial coverage on the shared session, parser, and save/load layers that
the Android UI still depends on.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agens_novel.agents.judge.nodes import _parse_judge_output
from agens_novel.agents.narrator.nodes import _parse_narrator_output
from agens_novel.persistence.save_manager import load_game, list_saves, save_game
from agens_novel.session.game_session import GameSession


class TestApplyDeltaDestructive:
    """Attack GameSession.apply_delta with malformed LLM-style values."""

    @pytest.mark.parametrize(
        "bad_val",
        ["+abc", "+3.5", "+", "-abc", "-3.5", "-", "+0x10", "++5", "--5", "+ 10"],
    )
    def test_malformed_increment_string_is_ignored(self, bad_val: str) -> None:
        s = GameSession(hp=80)
        s.apply_delta({"character": {"hp": bad_val}})
        assert isinstance(s.hp, int)
        assert 0 <= s.hp <= s.hp_max

    @pytest.mark.parametrize("bad_val", [3.14, None, True, False, [5], {"hp": 5}])
    def test_non_numeric_types_are_ignored(self, bad_val: Any) -> None:
        s = GameSession(hp=80)
        s.apply_delta({"character": {"hp": bad_val}})
        assert s.hp == 80

    def test_stat_clamps_survive_extreme_values(self) -> None:
        s = GameSession(hp=100, hp_max=100, mp=50, mp_max=50, gold=0)
        s.apply_delta({"character": {"hp": "+999999", "mp": "-999999", "gold": "-10"}})
        assert s.hp == 100
        assert s.mp == 0
        assert s.gold == 0

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

    def test_combat_none_and_empty_dict_clear_state(self) -> None:
        s = GameSession()
        s.apply_delta({"character": {"combat": {"phase": "player_turn"}}})
        assert s.combat is not None
        s.apply_delta({"character": {"combat": None}})
        assert s.combat is None
        s.apply_delta({"character": {"combat": {"phase": "player_turn"}}})
        s.apply_delta({"character": {"combat": {}}})
        assert s.combat is None


class TestParserDestructive:
    """LLM parser inputs should fail closed instead of crashing."""

    @pytest.mark.parametrize("text", ["", "plain text only", "<state_update>{bad json}</state_update>"])
    def test_narrator_parser_handles_malformed_output(self, text: str) -> None:
        narrative, delta, choices = _parse_narrator_output(text)
        assert isinstance(narrative, str)
        assert isinstance(delta, dict)
        assert isinstance(choices, list)

    @pytest.mark.parametrize("text", ["", "not json", '{"approved": "yes"}'])
    def test_judge_parser_handles_malformed_output(self, text: str) -> None:
        approved, corrected_delta, note, score = _parse_judge_output(text)
        assert isinstance(approved, bool)
        assert isinstance(corrected_delta, dict)
        assert isinstance(note, str)
        assert isinstance(score, int)


class TestSaveLoadDestructive:
    """Save/load must stay constrained to the configured save directory."""

    def test_load_corrupt_save_raises(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        save_dir = tmp_path / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / "corrupt.json").write_text("NOT JSON AT ALL{{{{", encoding="utf-8")

        with pytest.raises(Exception):
            load_game("corrupt")

    def test_load_nonexistent_save_raises(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        with pytest.raises(FileNotFoundError):
            load_game("does_not_exist")

    def test_list_saves_reports_corrupt_and_valid_entries(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        save_dir = tmp_path / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        good = GameSession(char_name="许满", game_started=True).to_save_dict()
        (save_dir / "good.json").write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        (save_dir / "bad.json").write_text("{invalid json", encoding="utf-8")

        saves = list_saves()
        names = {item["name"] for item in saves}
        assert {"good", "bad"}.issubset(names)
        assert next(item for item in saves if item["name"] == "bad").get("error") == "corrupt"

    def test_save_name_sanitization(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        s = GameSession(char_name="test", game_started=True)
        save_path = save_game(s, "../../../etc/passwd")
        assert save_path.startswith(str(tmp_path / "saves"))
        assert load_game("etcpasswd").char_name == "test"

    def test_save_load_preserves_session_fields(self, tmp_path, monkeypatch) -> None:
        from agens_novel import paths

        monkeypatch.setattr(paths, "SAVE_DIR", tmp_path / "saves")
        s = GameSession(
            char_name="许满",
            realm="金丹",
            realm_stage=5,
            hp=85,
            hp_max=120,
            mp=60,
            mp_max=80,
            spirit_root="火木双灵根",
            spirit_root_grade="天",
            experience=450,
            experience_to_next=500,
            gold=99,
            techniques=[{"name": "青云剑诀", "level": 3, "type": "剑法"}],
            inventory=[{"name": "灵石", "quantity": 5, "type": "材料"}],
            status_effects=["中毒", "力竭"],
            lifespan=200,
            location="青云山内门",
            region="东荒",
            current_scene="藏经阁",
            day_count=15,
            npcs_present=[{"name": "长老", "realm": "元婴"}],
            active_quests=[{"name": "寻剑", "status": "active"}],
            discovered_locations=["青云山外门", "内门"],
            lore_facts=["青云门建于三千年前"],
        )
        s.game_started = True
        s.turn_count = 42

        save_game(s, "full_test")
        loaded = load_game("full_test")

        assert loaded.char_name == s.char_name
        assert loaded.realm == s.realm
        assert loaded.realm_stage == s.realm_stage
        assert loaded.hp == s.hp
        assert loaded.mp == s.mp
        assert loaded.spirit_root == s.spirit_root
        assert loaded.gold == s.gold
        assert loaded.status_effects == ["中毒", "力竭"]
        assert loaded.location == s.location
        assert loaded.turn_count == s.turn_count


class TestAsGameState:
    def test_produces_json_serializable_state(self) -> None:
        s = GameSession(char_name="许满", realm="筑基", hp=85)
        parsed = json.loads(json.dumps(s.as_game_state(), ensure_ascii=False))
        assert parsed["character"]["name"] == "许满"
        assert parsed["character"]["hp"] == 85
        assert "world" in parsed
