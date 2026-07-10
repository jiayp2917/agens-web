"""FastAPI application for agens-web."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agens_novel.logging_setup import setup_logging

from .auth import DEV_SESSION_SECRET
from .database import create_database
from .router_auth import router as auth_router
from .router_catalog import router as catalog_router
from .router_sessions import router as sessions_router
from .router_settings import router as settings_router
from .security import (
    BodySizeLimitMiddleware,
    RateLimiter,
    enforce_same_origin,
    is_production_mode,
)
from .service import WebGameService

logger = logging.getLogger(__name__)

FRONTEND_REACT_DIST = Path(__file__).resolve().parents[1] / "frontend-react" / "dist"
SAFE_ERROR = "请求无法完成，请稍后再试。"


def validate_runtime_config() -> None:
    if not is_production_mode():
        return
    required = {
        "DATABASE_URL": os.environ.get("DATABASE_URL", "").strip(),
        "INVITE_ADMIN_CODE": os.environ.get("INVITE_ADMIN_CODE", "").strip(),
        "AGENS_ALLOWED_ORIGINS": os.environ.get("AGENS_ALLOWED_ORIGINS", "").strip(),
        "MODEL_CONFIG_SECRET": os.environ.get("MODEL_CONFIG_SECRET", "").strip(),
    }
    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret or session_secret == DEV_SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be set to a non-default value in production.")
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"{', '.join(missing)} required in production.")


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
    app.state.service = WebGameService(create_database())
    app.state.rate_limiter = RateLimiter()
    _configure_middleware(app, production)
    _configure_handlers(app)
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(sessions_router)
    app.include_router(settings_router)
    _mount_frontend(app)
    return app


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
            if app.state.service.db.ping():
                return {"status": "ok", "database": "ok"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="数据库暂不可用。") from exc
        raise HTTPException(status_code=503, detail="数据库暂不可用。")


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
