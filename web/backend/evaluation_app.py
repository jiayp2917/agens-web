"""Local evaluation application assembly kept outside product services."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready, evaluation_mode_enabled
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationCallObserver,
    EvaluationLedger,
    evaluation_budget_root,
)
from agens_novel.evaluation.model_config import (
    EvaluationModelConfig,
    EvaluationModelConfigResolver,
)
from agens_novel.evaluation.playthrough import (
    canonical_action_for_slot,
    install_canonical_authority,
)
from agens_novel.evaluation.scenarios import CanonicalScenarioV1, canonical_v3_scenarios

from .database import WebDatabaseProtocol, create_database
from .run_policy import SessionRunPolicy
from .service import WebGameService

if TYPE_CHECKING:
    from agens_novel.engine.game_engine import GameEngine


class CanonicalSessionRunPolicy(SessionRunPolicy):
    """Adapt one evaluator-owned scenario to the neutral product policy interface."""

    def __init__(self, scenarios: tuple[CanonicalScenarioV1, ...] | None = None) -> None:
        registered = scenarios or canonical_v3_scenarios()
        self._scenarios = {scenario.key: scenario for scenario in registered}
        self._story_version = _evaluation_story_version()
        key = os.environ.get("AGENS_EVALUATION_SCENARIO", "").strip()
        if not key:
            self._scenario: CanonicalScenarioV1 | None = None
        else:
            self._scenario = self._scenarios.get(key)
            if self._scenario is None:
                raise ValueError("evaluation scenario is not registered")

    def profile_for_start(self, profile: dict[str, object]) -> dict[str, object]:
        if self._scenario is None:
            return dict(profile)
        return dict(self._scenario.profile)

    def apply_started_session(self, engine: GameEngine) -> None:
        if self._scenario is not None:
            install_canonical_authority(engine, self._scenario, story_version=self._story_version)

    def action_for_choice(self, index: int, semantic_action: str) -> str:
        if self._scenario is None:
            return semantic_action
        return canonical_action_for_slot("ABCD"[index])


def create_evaluation_app() -> FastAPI:
    """Create the local-only FastAPI application used by qualification tools."""
    if not evaluation_mode_enabled():
        raise RuntimeError("evaluation application requires AGENS_EVALUATION_MODE")
    from .app import create_app

    return create_app(
        service_factory=lambda: create_evaluation_game_service(create_database)
    )


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
    call_record = EvaluationBudget(evaluation_budget_root(root))
    ledger = EvaluationLedger(
        provider=config.provider,
        model=config.model,
        shared_budget=call_record,
    )
    resolver = EvaluationModelConfigResolver(
        config,
        model_call_observer=EvaluationCallObserver(ledger),
    )
    return WebGameService(
        database,
        model_config_resolver=resolver,
        run_policy=CanonicalSessionRunPolicy(),
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
    if database != "agens_web_local" and "eval" not in database and "chrome" not in database:
        raise RuntimeError("evaluation mode requires an explicitly named evaluation database")


def _evaluation_story_version() -> int:
    raw = os.environ.get("AGENS_EVALUATION_STORY_VERSION", "3").strip()
    if raw not in {"1", "2", "3"}:
        raise RuntimeError("evaluation story version must be 1, 2, or 3")
    return int(raw)


def __getattr__(name: str):
    if name == "app":
        return create_evaluation_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
