"""Narrator stream filtering and history-compaction tests."""

from __future__ import annotations

from agens_novel.agents.narrator.nodes import (
    _parse_narrator_output,
)


class TestNarrativeViewStreamFilter:
    """Test that <state_update> is correctly filtered from narrator output.

    NarrativeView strips the <state_update>...</state_update> block before
    displaying; these tests verify the parser does the stripping.
    """

    def test_state_tag_regex(self):
        """Verify the _parse_narrator_output correctly strips state_update."""

        text = "你静坐吐纳，灵气入体。\n\n<state_update>\n{\"character\": {\"attributes\": {\"luck\": 1}}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "你静坐吐纳，灵气入体。"
        assert delta == {"character": {"attributes": {"luck": 1}}}
        assert "<state_update>" not in narrative

    def test_state_tag_at_beginning(self):
        """If the entire output is a state_update, narrative should be empty."""

        text = "<state_update>\n{\"meta\": {\"game_over\": true}}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == ""
        assert delta.get("meta", {}).get("game_over") is True

    def test_no_state_tag(self):
        """If there's no state_update tag, full text is narrative."""

        text = "一段普通的叙事文本，没有 JSON。"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == text
        assert delta is None

    def test_malformed_json_in_tag(self):
        """Malformed structure tags should stay incomplete, not silently succeed."""

        text = "叙事内容\n\n<state_update>\n{invalid json}\n</state_update>"
        narrative, delta, choices = _parse_narrator_output(text)

        assert narrative == "叙事内容"
        assert delta is None


class TestNarratorHistoryCompaction:
    """The narrator prompt must compress chat_history before it reaches the storage cap."""

    def test_short_history_returned_verbatim(self) -> None:
        from agens_novel.agents.narrator.nodes import _compact_history_for_prompt

        history = [
            {"role": "assistant", "content": "开场"},
            {"role": "user", "content": "A"},
        ]
        assert _compact_history_for_prompt(history) is history

    def test_long_history_compresses_to_opening_stub_and_recent_window(self) -> None:
        from agens_novel.agents.narrator.nodes import (
            _RECENT_HISTORY_MESSAGES,
            _compact_history_for_prompt,
        )

        opening = {"role": "assistant", "content": "开局世界设定" * 200}  # >1200 chars
        history: list[dict] = [opening]
        for i in range(12):
            history.append({"role": "user", "content": f"行动{i}"})
            history.append({"role": "assistant", "content": f"叙事{i}"})

        compacted = _compact_history_for_prompt(history)

        # Opening (truncated) + summary stub + recent window.
        assert len(compacted) == 1 + 1 + _RECENT_HISTORY_MESSAGES
        # Opening entry preserved at the front and truncated to the 1200-char cap.
        assert compacted[0]["role"] == "assistant"
        assert compacted[0]["content"].startswith("开局世界设定")
        assert len(compacted[0]["content"]) <= 1200
        # Summary stub signals the omitted middle.
        assert "省略" in compacted[1]["content"]
        # Recent window is the verbatim tail.
        assert compacted[-_RECENT_HISTORY_MESSAGES:] == history[-_RECENT_HISTORY_MESSAGES:]
        # No uncompressed middle entries leak through.
        middle_dropped = {"role": "user", "content": "行动0"}
        assert middle_dropped not in compacted
