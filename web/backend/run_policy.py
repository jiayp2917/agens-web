"""Optional application policy for controlled local game runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agens_novel.engine.game_engine import GameEngine


class SessionRunPolicy(Protocol):
    """Apply non-product runtime setup without changing public routes."""

    def profile_for_start(self, profile: dict[str, object]) -> dict[str, object]: ...

    def apply_started_session(self, engine: GameEngine) -> None: ...

    def action_for_choice(self, index: int, semantic_action: str) -> str: ...


class NoopSessionRunPolicy:
    """Normal product behavior."""

    def profile_for_start(self, profile: dict[str, object]) -> dict[str, object]:
        return dict(profile)

    def apply_started_session(self, _engine: GameEngine) -> None:
        return None

    def action_for_choice(self, _index: int, semantic_action: str) -> str:
        return semantic_action
