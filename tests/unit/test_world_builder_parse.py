"""Tests for world builder output parsing."""

from __future__ import annotations

import json

from agens_novel.agents.world_builder.nodes import _parse_world_output


def test_parse_world_output_preserves_opening_choices() -> None:
    payload = {
        "character": {"name": "许满", "realm": "练气"},
        "world": {"location": "青玄宗山门"},
        "opening_narrative": "晨雾漫过山门。",
        "choices": [
            {"id": "A", "text": "留在山门吐纳"},
            {"id": "B", "action": "询问接引弟子"},
            "观察灵气流向",
            "多余选项",
        ],
    }
    text = f"前言\n<world_data>\n{json.dumps(payload, ensure_ascii=False)}\n</world_data>"

    data, world_description, opening = _parse_world_output(text)

    assert world_description == "前言"
    assert opening == "晨雾漫过山门。"
    assert data["choices"] == ["留在山门吐纳", "询问接引弟子", "观察灵气流向"]
