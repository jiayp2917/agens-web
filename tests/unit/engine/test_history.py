"""Tests for semantic narrator-history storage and legacy compatibility."""

from __future__ import annotations

from agens_novel.engine.history import render_history_entry
from agens_novel.session.game_session import GameSession


def test_semantic_history_entry_renders_context_without_state_delta() -> None:
    session = GameSession(story_key="border-vein-crisis", story_version=3)
    session.story_state = {"recent_motifs": ["frontier-record-1"]}
    session.last_choices = ["稳固根基", "寻访机缘", "踏入险地", "静候气运"]

    session.record_turn(
        "稳固根基",
        "其人在外门静修一年。",
        {
            "character": {"age": "+1"},
            "world": {"story_update": {"pressure": 0}},
            "meta": {
                "choice_slot": "A",
                "choice_category": "稳妥",
                "event_id": "steady-root-ledger",
                "turn_summary": "稳妥路线推进了一年。",
            },
        },
    )

    rendered = render_history_entry(session.chat_history[-1])

    assert "其人在外门静修一年。" in rendered
    assert "槽位A" in rendered
    assert "路线稳妥" in rendered
    assert "steady-root-ledger" in rendered
    assert "<state_update>" not in rendered
    assert "story_update" not in rendered


def test_legacy_tag_history_remains_readable_after_save_round_trip() -> None:
    legacy_content = (
        "旧叙事。\n<state_update>{}</state_update>\n"
        '<choices>["甲", "乙", "丙", "丁"]</choices>'
    )
    restored = GameSession.from_save_dict(
        {"chat_history": [{"role": "assistant", "content": legacy_content}]}
    )

    assert render_history_entry(restored.chat_history[0]) == legacy_content
