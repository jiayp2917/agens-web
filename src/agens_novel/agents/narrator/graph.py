"""Narrator Agent -- graph assembly."""

from __future__ import annotations

from typing import Any

from ..sequential import SequentialAgentGraph
from .nodes import build_prompt, call_agnes_llm, load_settings, save_artifact


def build_narrator_graph() -> Any:
    return SequentialAgentGraph([
        load_settings,
        build_prompt,
        call_agnes_llm,
        save_artifact,
    ])
