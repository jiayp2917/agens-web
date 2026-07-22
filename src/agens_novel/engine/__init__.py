"""Engine package: UI-agnostic game logic and rendering."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game_engine import GameEngine


def __getattr__(name: str):
    """Keep the package export without importing the full Agent graph eagerly."""
    if name == "GameEngine":
        from .game_engine import GameEngine

        return GameEngine
    raise AttributeError(name)

__all__ = ["GameEngine"]
