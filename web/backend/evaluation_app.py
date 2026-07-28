"""Local evaluation application assembly kept outside product services."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationCallObserver,
    EvaluationLedger,
    configured_evaluation_limits,
    evaluation_budget_root,
    evaluation_record_only,
)
from agens_novel.evaluation.model_config import (
    EvaluationModelConfig,
    EvaluationModelConfigResolver,
)
from agens_novel.evaluation.playthrough import (
    authority_state_hash,
    canonical_action_for_slot,
    install_canonical_authority,
)
from agens_novel.evaluation.scenarios import CanonicalScenarioV1, canonical_v3_scenarios

from .database import WebDatabaseProtocol
from .evaluation_hooks import EvaluationHooks, EvaluationScenario
from .service import WebGameService

if TYPE_CHECKING:
    from agens_novel.engine.game_engine import GameEngine
    from agens_novel.session.game_session import GameSession


class CanonicalEvaluationHooks(EvaluationHooks):
    """Adapt evaluator-owned canonical scenarios to the product hook contract."""

    def __init__(self, scenarios: tuple[CanonicalScenarioV1, ...] | None = None) -> None:
        registered = scenarios or canonical_v3_scenarios()
        self._scenarios = {scenario.key: scenario for scenario in registered}
        self._story_version = _evaluation_story_version()

    def active_scenario(self) -> EvaluationScenario | None:
        key = os.environ.get("AGENS_EVALUATION_SCENARIO", "").strip()
        if not key:
            return None
        scenario = self._scenarios.get(key)
        if scenario is None:
            raise ValueError("evaluation scenario is not registered")
        return EvaluationScenario(key=scenario.key, profile=dict(scenario.profile))

    def install_authority(self, engine: GameEngine, scenario: EvaluationScenario) -> None:
        install_canonical_authority(engine, self._canonical(scenario), story_version=self._story_version)

    def canonical_action_for_slot(self, slot: str) -> str:
        return canonical_action_for_slot(slot)

    def authority_state_hash(self, session: GameSession) -> str:
        return authority_state_hash(session)

    def _canonical(self, scenario: EvaluationScenario) -> CanonicalScenarioV1:
        canonical = self._scenarios.get(scenario.key)
        if canonical is None:
            raise ValueError("evaluation scenario is not registered")
        return canonical


def create_evaluation_game_service(
    database_factory: Callable[[], WebDatabaseProtocol],
) -> tuple[WebGameService, EvaluationLedger]:
    """Build the isolated evaluator service after proving its database boundary."""
    _validate_evaluation_database_url()
    database = database_factory()
    config = EvaluationModelConfig.from_environment()
    root = ensure_evaluation_sink_ready()
    if root is None:
        raise RuntimeError("evaluation artifact root is unavailable")
    record_only = evaluation_record_only()
    budget = None
    if not record_only:
        max_total_calls, max_narrator_calls = configured_evaluation_limits()
        budget = EvaluationBudget(
            evaluation_budget_root(root),
            max_total_calls=max_total_calls,
            max_narrator_calls=max_narrator_calls,
        )
    ledger = EvaluationLedger(
        provider=config.provider,
        model=config.model,
        shared_budget=budget,
        record_only=record_only,
    )
    resolver = EvaluationModelConfigResolver(
        config,
        model_call_observer=EvaluationCallObserver(ledger),
    )
    return WebGameService(
        database,
        model_config_resolver=resolver,
        evaluation_hooks=CanonicalEvaluationHooks(),
    ), ledger


def _validate_evaluation_database_url() -> None:
    """Reject an evaluation process pointed at a non-local product database."""
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise RuntimeError("evaluation mode requires an isolated local PostgreSQL database") from exc
    host = str(url.host or "").lower()
    database = str(url.database or "").lower()
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("evaluation mode requires an isolated local PostgreSQL database")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("evaluation mode requires an isolated local PostgreSQL database")
    if "eval" not in database and "chrome" not in database:
        raise RuntimeError("evaluation mode requires an explicitly named evaluation database")


def _evaluation_story_version() -> int:
    raw = os.environ.get("AGENS_EVALUATION_STORY_VERSION", "3").strip()
    if raw not in {"1", "2", "3"}:
        raise RuntimeError("evaluation story version must be 1, 2, or 3")
    return int(raw)
