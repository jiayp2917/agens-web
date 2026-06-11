"""Unit tests for the Reviewer Agent's JSON verdict parser."""

from __future__ import annotations

from agens_novel.agents.reviewer.nodes import _parse_review_output


def test_parses_clean_json() -> None:
    score, passed, feedback = _parse_review_output(
        '{"score": 8, "passed": true, "feedback": "ok"}'
    )
    assert score == 8
    assert passed is True
    assert feedback == "ok"


def test_parses_fenced_json() -> None:
    text = "```json\n{\"score\": 5, \"passed\": false, \"feedback\": \"缺动作\"}\n```"
    score, passed, feedback = _parse_review_output(text)
    assert score == 5
    assert passed is False
    assert feedback == "缺动作"


def test_extracts_json_from_prose() -> None:
    text = (
        "我审完了,以下是结论:\n"
        "```\n"
        '{"score": 9, "passed": true, "feedback": "节奏很好"}\n'
        "```\n"
        "请 Editor 修订。"
    )
    score, passed, feedback = _parse_review_output(text)
    assert score == 9
    assert passed is True
    assert feedback == "节奏很好"


def test_score_clamped_to_0_10() -> None:
    score, _, _ = _parse_review_output('{"score": 99, "passed": true, "feedback": ""}')
    assert score == 10
    score, _, _ = _parse_review_output('{"score": -3, "passed": false, "feedback": ""}')
    assert score == 0


def test_missing_passed_defaults_to_score_threshold() -> None:
    # score=8 implies passed=True
    _, passed, _ = _parse_review_output('{"score": 8, "feedback": "ok"}')
    assert passed is True
    _, passed, _ = _parse_review_output('{"score": 5, "feedback": ""}')
    assert passed is False


def test_unparseable_returns_low_score_safe_default() -> None:
    score, passed, feedback = _parse_review_output("这不是 JSON,只是一些评论。")
    assert score == 0
    assert passed is False
    assert "JSON" in feedback or "json" in feedback.lower()
