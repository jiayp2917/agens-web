"""Narrator Agent -- the primary game engine for the xianxia simulator."""

from __future__ import annotations


def build_narrator_graph():
    from .graph import build_narrator_graph as _build

    return _build()

__all__ = ["build_narrator_graph"]
