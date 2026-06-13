"""Tests for prototype-driven character creation flow."""

from __future__ import annotations

from agens_novel.engine.game_engine import GameEngine
from agens_novel.game.constants import ATTRIBUTE_KEYS, SPECIAL_START_ATTRIBUTES

SPECIAL_TALENT = "天命道胎"
SPECIAL_FAMILY = "隐世仙族"
SPECIAL_ROOT = "混沌天灵根"


def test_start_from_profile_initializes_session(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    narratives = []
    engine.on_narrative = lambda text, turn: narratives.append((text, turn))

    engine.start_from_profile({
        "char_name": "许满",
        "talent": "剑心微明",
        "spirit_root": "火灵根",
        "family_background": "寒门",
        "difficulty": "普通",
        "attributes": {key: 60 for key in ATTRIBUTE_KEYS},
        "choices": ["留在山门吐纳", "询问接引弟子", "观察灵气流向"],
    })

    s = engine.game_session
    assert s.game_started is True
    assert s.char_name == "许满"
    assert s.talent == "剑心微明"
    assert s.spirit_root == "火灵根"
    assert s.family_background == "寒门"
    assert s.game_mode == "abcd"
    assert s.last_choices == ["留在山门吐纳", "询问接引弟子", "观察灵气流向"]
    assert narratives and narratives[0][1] == 0


def test_hidden_2917_result_profile(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    engine.start_from_profile({
        "game_name": "2917",
        "char_name": "阿清",
        "talent": "天命道胎",
        "spirit_root": "混沌天灵根",
        "family_background": "隐世仙族",
        "attributes": dict(SPECIAL_START_ATTRIBUTES),
        "special_start": True,
    })

    s = engine.game_session
    assert s.char_name == "阿清"
    assert s.attributes == SPECIAL_START_ATTRIBUTES
    assert s.family_background == "隐世仙族"
    assert s.talent == "天命道胎"
    assert s.spirit_root == "混沌天灵根"
    assert s.hp == 999
    assert s.mp == 999


def test_special_profile_result_can_be_built_without_pre_reveal(tmp_path, monkeypatch):
    from agens_novel import paths
    monkeypatch.setattr(paths, "SAVE_DIR", tmp_path)

    engine = GameEngine()
    visible_form = {
        "game_name": "2917",
        "char_name": "许满",
        "talent": "剑心微明",
        "spirit_root": "火灵根",
        "family_background": "寒门",
        "attributes": {key: 50 for key in ATTRIBUTE_KEYS},
        "special_start": True,
    }
    start_profile = {
        **visible_form,
        "char_name": "阿清",
        "talent": SPECIAL_TALENT,
        "spirit_root": SPECIAL_ROOT,
        "family_background": SPECIAL_FAMILY,
        "attributes": dict(SPECIAL_START_ATTRIBUTES),
    }

    engine.start_from_profile(start_profile)

    s = engine.game_session
    assert visible_form["char_name"] == "许满"
    assert s.char_name == "阿清"
    assert s.talent == SPECIAL_TALENT
    assert s.spirit_root == SPECIAL_ROOT
    assert s.family_background == SPECIAL_FAMILY
