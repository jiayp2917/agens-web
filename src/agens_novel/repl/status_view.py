"""REPL helper views -- game status display."""

from __future__ import annotations

from .game_session import GameSession
from .game_view import render_status_panel


def show_game_status(console: "rich.console.Console", session: GameSession) -> None:
    """Display full character status panel."""
    console.print(render_status_panel(session))
