"""Judge Agent -- rules arbiter for the xianxia simulator."""

from __future__ import annotations


def build_judge_graph():
    from .graph import build_judge_graph as _build

    return _build()

__all__ = ["build_judge_graph"]
