"""Tests for Judge agent — default rejection on parse failure."""

from __future__ import annotations

import json
import pytest

from agens_novel.agents.judge.nodes import _parse_judge_output


class TestParseJudgeOutput:
    """Test _parse_judge_output — defaults to approved=False on failure."""

    def test_clean_json_approved(self):
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 8}'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True
        assert delta == {}
        assert note == "ok"
        assert score == 8

    def test_clean_json_rejected(self):
        text = '{"approved": false, "corrected_delta": {"character": {"hp": 50}}, "judgment_note": "HP变化过大", "review_score": 3}'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False
        assert "character" in delta
        assert "HP" in note
        assert score == 3

    def test_fenced_json(self):
        text = '```json\n{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 9}\n```'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True
        assert score == 9

    def test_json_in_prose(self):
        text = 'Here is my verdict: {"approved": true, "corrected_delta": {}, "judgment_note": "fine", "review_score": 7} and that is it.'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is True

    def test_garbage_input_defaults_to_reject(self):
        """CRITICAL: parse failure must default to approved=False."""
        text = "This is not JSON at all, just some random text."
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False, "Parse failure should default to approved=False"
        assert delta == {}
        assert score == 0

    def test_empty_input_defaults_to_reject(self):
        approved, delta, note, score = _parse_judge_output("")
        assert approved is False
        assert score == 0

    def test_malformed_json_defaults_to_reject(self):
        text = '{"approved": true, "broken json'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False

    def test_missing_approved_defaults_false(self):
        text = '{"judgment_note": "ok", "review_score": 8}'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False  # approved defaults to False when missing

    def test_non_dict_json_defaults_to_reject(self):
        text = '[1, 2, 3]'
        approved, delta, note, score = _parse_judge_output(text)
        assert approved is False

    def test_corrected_delta_non_dict_becomes_empty(self):
        text = '{"approved": true, "corrected_delta": "not a dict", "judgment_note": "ok"}'
        approved, delta, note, score = _parse_judge_output(text)
        assert delta == {}

    def test_score_clamped_to_0_10(self):
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": 15}'
        approved, delta, note, score = _parse_judge_output(text)
        assert score == 10

    def test_score_negative_clamped(self):
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "review_score": -5}'
        approved, delta, note, score = _parse_judge_output(text)
        assert score == 0

    def test_score_from_score_key(self):
        """Should also accept 'score' key as fallback."""
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "ok", "score": 6}'
        approved, delta, note, score = _parse_judge_output(text)
        assert score == 6

    def test_empty_judgment_note_becomes_ok(self):
        text = '{"approved": true, "corrected_delta": {}, "judgment_note": "", "review_score": 5}'
        approved, delta, note, score = _parse_judge_output(text)
        assert note == "ok"
