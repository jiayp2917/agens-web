"""Tests for judge output parsing (JSON verdict extraction)."""

from __future__ import annotations

from agens_novel.agents.judge.nodes import _parse_judge_output


class TestJudgeParse:
    def test_clean_json(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 8}'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True
        assert delta == {}
        assert note == "ok"
        assert score == 8

    def test_fenced_json(self) -> None:
        text = '```json\n{"approved": false, "corrected_delta": {"character": {"hp": 50}}, "judgment_note": "HP变化过大", "review_score": 3}\n```'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False
        assert delta["character"]["hp"] == 50
        assert "HP" in note
        assert score == 3

    def test_json_embedded_in_prose(self) -> None:
        text = '审查结果如下：{"approved": true, "corrected_delta": {}, "judgment_note": "数值合理", "review_score": 9} 审查完毕。'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True
        assert score == 9

    def test_missing_score_defaults(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok"}'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True
        assert score == 5  # default

    def test_malformed_json_defaults_to_reject(self) -> None:
        text = "This is not JSON at all."
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False  # Safe default: reject on parse failure

    def test_score_clamped_to_0_10(self) -> None:
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 15}'
        approved, delta, note, score = _parse_judge_output(text)
        assert score == 10

    def test_negative_score_clamped(self) -> None:
        text = '{"approved": false, "corrected_delta": {}, "judgment_note": "bad", "review_score": -5}'
        approved, delta, note, score = _parse_judge_output(text)
        assert score == 0

    def test_non_dict_json_rejected(self) -> None:
        text = '[1, 2, 3]'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False  # Not a dict → reject (safe default)
