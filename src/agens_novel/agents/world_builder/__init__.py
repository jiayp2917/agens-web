"""World Builder Agent -- creates characters and world content."""

from __future__ import annotations


def build_world_builder_graph():
    from .graph import build_world_builder_graph as _build

    return _build()

__all__ = ["build_world_builder_graph"]
