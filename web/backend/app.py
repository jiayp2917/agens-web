"""FastAPI application for agens-web."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agens_novel.artifacts.sink import ensure_evaluation_sink_ready, evaluation_mode_enabled
from agens_novel.evaluation.ledger import (
    EvaluationBudget,
    EvaluationCallObserver,
    EvaluationLedger,
    configured_evaluation_limits,
    evaluation_budget_root,
)
from agens_novel.evaluation.model_config import (
    EvaluationModelConfig,
    EvaluationModelConfigResolver,
)
from agens_novel.llm.client import InvalidEgressProxyUrl, validate_egress_proxy_url
from agens_novel.logging_setup import setup_logging

from .auth import DEV_SESSION_SECRET
from .database import create_database
from .router_auth import router as auth_router
from .router_catalog import router as catalog_router
from .router_sessions import router as sessions_router
from .router_settings import router as settings_router
from .security import (
    BodySizeLimitMiddleware,
    create_rate_limiter,
    enforce_same_origin,
    is_production_mode,
)
from .service import WebGameService

logger = logging.getLogger(__name__)

FRONTEND_REACT_DIST = Path(__file__).resolve().parents[1] / "frontend-react" / "dist"
SAFE_ERROR = "请求无法完成，请稍后再试。"
_PLACEHOLDER_MARKERS = ("change_me", "changeme", "replace_me", "example.com", "<", ">")


def validate_runtime_config() -> None:
    if is_production_mode() and evaluation_mode_enabled():
        raise RuntimeError("AGENS_EVALUATION_MODE is disabled in production.")
    if not is_production_mode():
        return
    _validate_production_runtime_services()
    configured = _required_production_values()
    _validate_production_secrets(configured)
    _validate_production_transport(configured["AGENS_ALLOWED_ORIGINS"])


def _validate_production_runtime_services() -> None:
    if os.environ.get("AGENS_VALIDATION_SEED", "").strip():
        raise RuntimeError("AGENS_VALIDATION_SEED must not be set in production.")
    if os.environ.get("AGENS_RATE_LIMIT_BACKEND", "").strip().lower() != "redis":
        raise RuntimeError("AGENS_RATE_LIMIT_BACKEND must be redis in production.")
    if not os.environ.get("AGENS_RATE_LIMIT_REDIS_URL", "").strip():
        raise RuntimeError("AGENS_RATE_LIMIT_REDIS_URL required in production.")
    proxy_url = os.environ.get("AGENS_EGRESS_PROXY_URL", "").strip()
    if not proxy_url:
        raise RuntimeError("AGENS_EGRESS_PROXY_URL required in production.")
    try:
        validate_egress_proxy_url(proxy_url)
    except InvalidEgressProxyUrl as exc:
        raise RuntimeError("AGENS_EGRESS_PROXY_URL must be a valid HTTP(S) proxy URL.") from exc


def _required_production_values() -> dict[str, str]:
    required = {
        "DATABASE_URL": os.environ.get("DATABASE_URL", "").strip(),
        "INVITE_ADMIN_CODE": os.environ.get("INVITE_ADMIN_CODE", "").strip(),
        "AGENS_ALLOWED_ORIGINS": os.environ.get("AGENS_ALLOWED_ORIGINS", "").strip(),
        "MODEL_CONFIG_SECRET": os.environ.get("MODEL_CONFIG_SECRET", "").strip(),
    }
    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret:
        raise RuntimeError("SESSION_SECRET required in production.")
    if session_secret == DEV_SESSION_SECRET or _looks_like_placeholder(session_secret):
        raise RuntimeError("SESSION_SECRET must not use a placeholder value in production.")
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"{', '.join(missing)} required in production.")
    configured = {**required, "SESSION_SECRET": session_secret}
    optional_api_key = os.environ.get("AGNES_API_KEY", "").strip()
    if optional_api_key:
        configured["AGNES_API_KEY"] = optional_api_key
    return configured


def _validate_production_secrets(configured: dict[str, str]) -> None:
    placeholders = [name for name, value in configured.items() if _looks_like_placeholder(value)]
    if placeholders:
        raise RuntimeError(
            f"{', '.join(placeholders)} must not use placeholder values in production."
        )
    weak = [
        name
        for name, minimum in (
            ("SESSION_SECRET", 32),
            ("MODEL_CONFIG_SECRET", 32),
            ("INVITE_ADMIN_CODE", 16),
        )
        if len(configured[name]) < minimum
    ]
    if weak:
        raise RuntimeError(f"{', '.join(weak)} must use sufficiently long production values.")


def _validate_production_transport(allowed_origins: str) -> None:
    secure_cookie = os.environ.get("SESSION_COOKIE_SECURE", "1").strip().lower()
    if secure_cookie in {"0", "false", "no"}:
        raise RuntimeError("SESSION_COOKIE_SECURE must remain enabled in production.")
    origins = [item.strip() for item in allowed_origins.split(",") if item.strip()]
    if any(urlparse(origin).scheme.lower() != "https" for origin in origins):
        raise RuntimeError("AGENS_ALLOWED_ORIGINS must contain only HTTPS origins in production.")


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def allowed_hosts_from_env() -> list[str]:
    hosts = {
        item.strip().lower()
        for item in os.environ.get("AGENS_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    for origin in os.environ.get("AGENS_ALLOWED_ORIGINS", "").split(","):
        parsed = urlparse(origin.strip())
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    if hosts:
        hosts.update({"127.0.0.1", "localhost", "agens-web"})
    return sorted(hosts)


def create_app() -> FastAPI:
    setup_logging()
    validate_runtime_config()
    production = is_production_mode()
    app = FastAPI(
        title="agens-web",
        version="0.1.0",
        dependencies=[Depends(enforce_same_origin)],
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.service, app.state.evaluation_ledger = _create_game_service()
    app.state.rate_limiter = create_rate_limiter()
    _configure_middleware(app, production)
    _configure_handlers(app)
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(sessions_router)
    app.include_router(settings_router)
    _mount_frontend(app)
    return app


def _create_game_service() -> tuple[WebGameService, EvaluationLedger | None]:
    """Create the product service or an explicitly isolated evaluation service."""
    if evaluation_mode_enabled():
        _validate_evaluation_database_url()
    database = create_database()
    if not evaluation_mode_enabled():
        return WebGameService(database), None
    config = EvaluationModelConfig.from_environment()
    root = ensure_evaluation_sink_ready()
    if root is None:
        raise RuntimeError("evaluation artifact root is unavailable")
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
    )
    resolver = EvaluationModelConfigResolver(
        config,
        model_call_observer=EvaluationCallObserver(ledger),
    )
    return WebGameService(database, model_config_resolver=resolver), ledger


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


def _configure_middleware(app: FastAPI, production: bool) -> None:
    allowed_hosts = allowed_hosts_from_env()
    if production or allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"],
        )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=int(os.environ.get("AGENS_MAX_REQUEST_BYTES", str(64 * 1024))),
    )


def _configure_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, _exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception in request")
        return JSONResponse({"detail": SAFE_ERROR}, status_code=500)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        try:
            database_ok = bool(app.state.service.db.ping())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="数据库暂不可用。") from exc
        if not database_ok:
            raise HTTPException(status_code=503, detail="数据库暂不可用。")
        if not app.state.rate_limiter.ping():
            raise HTTPException(status_code=503, detail="请求保护服务暂不可用。")
        return {"status": "ok", "database": "ok", "rate_limiter": "ok"}


def _mount_frontend(app: FastAPI) -> None:
    if not FRONTEND_REACT_DIST.exists():
        return
    assets_dir = FRONTEND_REACT_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    app.mount("/static", StaticFiles(directory=FRONTEND_REACT_DIST), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_REACT_DIST / "index.html")


def __getattr__(name: str):
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
