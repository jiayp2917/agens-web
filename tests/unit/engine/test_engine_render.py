"""Tests for UI-agnostic engine render functions."""

from __future__ import annotations

from agens_novel.engine.render import (
    format_inventory,
    format_log,
    format_map,
    format_quests,
    format_skills,
    format_status_bar,
    format_status_card,
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


class TestFormatStatusCard:
    def test_full_card(self) -> None:
        s = GameSession(
            char_name="许满", realm="金丹", realm_stage=5,
            spirit_root="火木双灵根", spirit_root_grade="天",
            experience=450, experience_to_next=500,
            gold=99, lifespan=200,
            location="青云山内门", region="东荒",
        )
        text = format_status_card(s)
        assert "许满" in text
        assert "金丹" in text
        assert "火木双灵根" in text
        assert "青云山内门" in text
        assert "99" in text  # gold
        # Game-mode v5: no HP/MP rows in the status card.
        assert "HP" not in text
        assert "MP" not in text

    def test_empty_name(self) -> None:
        s = GameSession()
        text = format_status_card(s)
        assert "未命名" in text

    def test_status_effects(self) -> None:
        s = GameSession()
        s.status_effects = ["中毒", "力竭"]
        text = format_status_card(s)
        assert "中毒" in text
        assert "力竭" in text

    def test_no_status_effects(self) -> None:
        s = GameSession()
        text = format_status_card(s)
        assert "状态" not in text


class TestFormatInventory:
    def test_empty(self) -> None:
        s = GameSession()
        assert "背包为空" in format_inventory(s)

    def test_with_items(self) -> None:
        s = GameSession()
        s.inventory = [
            {"name": "灵石", "quantity": 5, "type": "材料"},
            {"name": "粗布道袍", "quantity": 1, "type": "防具"},
        ]
        text = format_inventory(s)
        assert "灵石" in text
        assert "x5" in text
        assert "粗布道袍" in text


class TestFormatSkills:
    def test_empty(self) -> None:
        assert "尚未习得" in format_skills(GameSession())

    def test_with_techniques(self) -> None:
        s = GameSession()
        s.techniques = [{"name": "基础吐纳术", "level": 1, "type": "内功"}]
        text = format_skills(s)
        assert "基础吐纳术" in text
        assert "Lv.1" in text


class TestFormatMap:
    def test_empty(self) -> None:
        assert "尚未探索" in format_map(GameSession())

    def test_with_locations(self) -> None:
        s = GameSession()
        s.discovered_locations = ["青云山外门", "后山"]
        s.location = "后山"
        text = format_map(s)
        assert "青云山外门" in text
        assert "后山" in text
        assert "当前" in text


class TestFormatQuests:
    def test_empty(self) -> None:
        assert "没有任务" in format_quests(GameSession())

    def test_with_quests(self) -> None:
        s = GameSession()
        s.active_quests = [{"name": "入门修行", "description": "完成修炼", "status": "active"}]
        text = format_quests(s)
        assert "入门修行" in text
        assert "●" in text  # active marker


class TestFormatLog:
    def test_empty(self) -> None:
        assert "暂无" in format_log(GameSession())

    def test_with_history(self) -> None:
        s = GameSession()
        s.turn_history = [
            {"turn": 1, "narrative": "第一回合叙事。"},
            {"turn": 2, "narrative": "第二回合叙事。"},
        ]
        text = format_log(s)
        assert "第 1 回合" in text
        assert "第 2 回合" in text
