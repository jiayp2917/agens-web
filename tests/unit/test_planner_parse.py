"""Unit tests for the Planner Agent's bullet/notes parser."""

from __future__ import annotations

from agens_novel.agents.planner.nodes import _parse_plan_output


def test_parses_bullets_and_plan_notes() -> None:
    # Use ASCII bullets ('-') to avoid Windows-terminal encoding roundtrips.
    text = (
        "plan_notes: fast pacing, 30-50 chars, key motif: spirit qi.\n"
        "outline:\n"
        "- hero puts down the delivery box and looks at the sky.\n"
        "- brow furrows, chest feels warm.\n"
        "- pulls out something like a marble, realizes it's qi.\n"
    )
    outline, notes = _parse_plan_output(text)
    assert "delivery box" in outline
    assert "brow furrows" in outline
    assert "marble" in outline
    assert "fast pacing" in notes
    assert "spirit qi" in notes


def test_handles_dash_and_asterisk_bullets() -> None:
    text = "- step one\n- step two\n"
    outline, notes = _parse_plan_output(text)
    assert outline == "- step one\n- step two"
    assert notes == ""


def test_handles_middot_bullets() -> None:
    # Unicode middot bullets (·) should also be accepted.
    text = "step one\n· hero looks up\n· chest warms up\n"
    outline, notes = _parse_plan_output(text)
    assert "hero looks up" in outline
    assert "chest warms up" in outline
    assert notes == "step one"


def test_empty_input_returns_empty() -> None:
    outline, notes = _parse_plan_output("")
    assert outline == ""
    assert notes == ""


def test_fallback_when_no_bullets() -> None:
    text = "  some unstructured text  \n  more text  "
    outline, notes = _parse_plan_output(text)
    # No bullet markers, so the whole block becomes plan_notes.
    assert "unstructured text" in notes
    assert "more text" in notes
    assert outline == ""


def test_multiline_plan_notes() -> None:
    text = "plan_notes: line one\nline two\n- bullet1\n- bullet2\n"
    outline, notes = _parse_plan_output(text)
    assert "line one" in notes
    assert "line two" in notes
    assert "bullet1" in outline
    assert "bullet2" in outline
