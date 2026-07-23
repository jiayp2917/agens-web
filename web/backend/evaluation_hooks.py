"""Product-facing hooks for isolated local evaluation behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agens_novel.engine.game_engine import GameEngine
    from agens_novel.session.game_session import GameSession


@dataclass(frozen=True)
class EvaluationScenario:
    """The product-visible portion of one pre-registered evaluation scenario."""

    key: str
    profile: dict[str, object]


class EvaluationHooks(Protocol):
    """Optional evaluation behavior injected at the web application boundary."""

    def active_scenario(self) -> EvaluationScenario | None: ...

    def install_authority(self, engine: GameEngine, scenario: EvaluationScenario) -> None: ...

    def canonical_action_for_slot(self, slot: str) -> str: ...

    def authority_state_hash(self, session: GameSession) -> str | None: ...


class NoopEvaluationHooks:
    """Default product behavior with no evaluator-specific state or actions."""

    def active_scenario(self) -> EvaluationScenario | None:
        return None

    def install_authority(self, _engine: GameEngine, _scenario: EvaluationScenario) -> None:
        return None

    def canonical_action_for_slot(self, slot: str) -> str:
        return slot

    def authority_state_hash(self, _session: GameSession) -> str | None:
        return None
