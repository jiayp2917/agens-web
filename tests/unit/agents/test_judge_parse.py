from __future__ import annotations

import json

import pytest

from agens_novel.agents.judge.nodes import _parse_judge_output


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_judge_approved_requires_json_boolean(value) -> None:
    approved, corrected, _note, _score = _parse_judge_output(
        json.dumps(
            {
                "approved": value,
                "corrected_delta": {"character": {"realm": "筑基"}},
            }
        )
    )

    assert approved is False
    assert corrected == {"character": {"realm": "筑基"}}


def test_judge_accepts_real_json_true() -> None:
    approved, _corrected, _note, _score = _parse_judge_output(
        '{"approved": true, "corrected_delta": {}}'
    )
    assert approved is True
