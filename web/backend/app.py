"""FastAPI application for agens-web."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import (
    DEV_SESSION_SECRET,
    GUEST_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    cookie_kwargs,
    create_guest_token,
    create_session_token,
    hash_invite_code,
    hash_password,
    parse_session_token,
    public_auth_response,
    verify_password,
)
from .database import create_database
from .database_common import public_user
from .security import BodySizeLimitMiddleware, RateLimiter, client_key, enforce_same_origin, is_production_mode
from .service import GUEST_USER_PREFIX, WebGameService, is_guest_user_id
from agens_novel.logging_setup import setup_logging
from .catalog_seed import catalog_as_json

FRONTEND_REACT_DIST = Path(__file__).resolve().parents[1] / "frontend-react" / "dist"
SAFE_ERROR = "请求无法完成，请稍后再试。"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$")
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class CreateSessionRequest(BaseModel):
    title: str = "新局"


class StartRequest(BaseModel):
    char_name: str = ""
    talent: str = ""
    spirit_root: str = ""
    family_background: str = ""
    difficulty: str = "普通"
    attributes: dict[str, int] = Field(default_factory=dict)
    randomize_attributes: bool = False


class ChoiceRequest(BaseModel):
    choice: str = ""
    choice_index: int | None = None


class ActionRequest(BaseModel):
    action: str


class SaveRequest(BaseModel):
    name: str = "slot_1"


class EndSessionRequest(BaseModel):
    reason: str = "玩家结束本局。"


class ModelSettingsRequest(BaseModel):
    provider: str = Field(default="Agens", max_length=64)
    base_url: str = Field(
        default="https://apihub.agnes-ai.com/v1", max_length=512
    )
    model: str = Field(default="agnes-2.0-flash", max_length=128)
    api_key: str = Field(default="", max_length=512)


class InviteCreateRequest(BaseModel):
    code: str = Field(min_length=8, max_length=256)
    role: str = Field(default="user", pattern=r"^(user|admin)$")
    max_uses: int = Field(default=1, ge=1, le=100)



def validate_runtime_config() -> None:
    if not is_production_mode():
        return

    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret or session_secret == DEV_SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be set to a non-default value in production.")
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required in production.")
    if not os.environ.get("INVITE_ADMIN_CODE", "").strip():
        raise RuntimeError("INVITE_ADMIN_CODE is required in production.")
    if not os.environ.get("AGENS_ALLOWED_ORIGINS", "").strip():
        raise RuntimeError("AGENS_ALLOWED_ORIGINS is required in production.")


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


def service_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def create_app(db_path: Path | None = None) -> FastAPI:
    setup_logging()
    validate_runtime_config()
    service = WebGameService(create_database(db_path))
    production = is_production_mode()
    app = FastAPI(
        title="agens-web",
        version="0.1.0",
        dependencies=[Depends(enforce_same_origin)],
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.state.service = service
    app.state.rate_limiter = RateLimiter()
    allowed_hosts = allowed_hosts_from_env()
    if production or allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"])
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=int(os.environ.get("AGENS_MAX_REQUEST_BYTES", str(64 * 1024))),
    )

    def rate_limit(request: Request, action: str, limit: int, window_seconds: int) -> None:
        app.state.rate_limiter.check(
            client_key(request, action),
            limit=limit,
            window_seconds=window_seconds,
        )

    def service_call(operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except (KeyError, PermissionError, ValueError) as exc:
            raise service_http_error(exc) from exc

    def current_user(request: Request) -> dict[str, Any]:
        token = request.cookies.get(SESSION_COOKIE_NAME, "")
        claims = parse_session_token(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="请先登录。")
        user = service.db.get_user_by_id(claims.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="登录状态已失效。")
        return user

    def optional_user(request: Request) -> dict[str, Any] | None:
        token = request.cookies.get(SESSION_COOKIE_NAME, "")
        claims = parse_session_token(token)
        if claims is None:
            return None
        return service.db.get_user_by_id(claims.user_id)

    def current_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="需要管理员权限。")
        return user

    def set_login_cookie(response: Response, user: dict[str, Any]) -> None:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            create_session_token(user["id"]),
            **cookie_kwargs(),
        )

    def set_guest_cookie(response: Response, token: str) -> None:
        response.set_cookie(GUEST_COOKIE_NAME, token, **cookie_kwargs())

    def session_owner_id(session_id: str, request: Request, user: dict[str, Any] | None) -> str | None:
        if user is not None:
            return user["id"]
        guest_token = request.cookies.get(GUEST_COOKIE_NAME, "")
        runner = service.runners.get(session_id)
        if (
            runner
            and is_guest_user_id(runner.user_id)
            and runner.guest_token
            and runner.guest_token == guest_token
        ):
            return None
        raise HTTPException(status_code=401, detail="访客会话已失效，请从新游戏重新开始。")

    def register_with_invite(payload: RegisterRequest) -> dict[str, Any]:
        username = payload.username.strip()
        if service.db.get_user_by_username(username):
            raise HTTPException(status_code=409, detail="用户名已存在。")

        invite_code = payload.invite_code.strip()
        admin_code = os.environ.get("INVITE_ADMIN_CODE", "").strip()
        is_admin = False
        if admin_code and invite_code == admin_code and not service.db.has_admin_user():
            is_admin = True
        else:
            invite = service.db.consume_invite_code(hash_invite_code(invite_code))
            if invite is None:
                raise HTTPException(status_code=400, detail="邀请码无效或已用完。")
            is_admin = str(invite.get("role") or "user").lower() == "admin"
        try:
            return service.db.create_user(username, hash_password(payload.password), is_admin=is_admin)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="注册失败，请检查输入。") from exc

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": SAFE_ERROR}, status_code=500)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Catalog endpoints (public read-only game content) ─────────────────

    @app.get("/api/catalog/talents")
    def catalog_talents() -> list[dict[str, Any]]:
        return [catalog_as_json(row) for row in service.db.list_catalog("catalog_talents")]

    @app.get("/api/catalog/family_backgrounds")
    def catalog_family_backgrounds() -> list[dict[str, Any]]:
        return [catalog_as_json(row) for row in service.db.list_catalog("catalog_family_backgrounds")]

    @app.get("/api/catalog/spirit_roots")
    def catalog_spirit_roots() -> list[dict[str, Any]]:
        return [catalog_as_json(row) for row in service.db.list_catalog("catalog_spirit_roots")]

    @app.get("/api/catalog/difficulties")
    def catalog_difficulties() -> list[dict[str, Any]]:
        return [catalog_as_json(row) for row in service.db.list_catalog("catalog_difficulties")]

    @app.get("/api/catalog/story_seeds")
    def catalog_story_seeds() -> list[dict[str, Any]]:
        return [catalog_as_json(row) for row in service.db.list_catalog("catalog_story_seeds")]

    @app.get("/api/catalog/rarities")
    def catalog_rarities(request: Request) -> dict[str, Any]:
        """Return the 6 rarity tiers and the player's unlocked set (spec §11).

        Guests and new accounts start with 白/绿/蓝 only; 紫/橙/红 unlock as the
        player completes runs and ascends. The UI uses this to grey out locked
        rarities during manual selection.
        """
        from agens_novel.game.constants import (
            CATALOG_RARITY_TIERS,
            rarity_unlocked_for,
        )
        user = current_user(request)
        progress = service.db.get_player_progress(user["id"])
        unlocked = rarity_unlocked_for(
            progress["runs_completed"], progress["ascension_count"]
        )
        return {
            "tiers": [
                {
                    "key": t["key"],
                    "label": t["label"],
                    "weight": t["weight"],
                    "select_requires_runs": t["select_requires_runs"],
                    "select_requires_ascensions": t["select_requires_ascensions"],
                    "random_requires_runs": t["random_requires_runs"],
                    "unlocked": t["key"] in unlocked,
                }
                for t in CATALOG_RARITY_TIERS
            ],
            "runs_completed": progress["runs_completed"],
            "ascension_count": progress["ascension_count"],
            "unlocked": unlocked,
        }

    @app.post("/api/auth/register")
    def register(payload: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
        rate_limit(request, "register", limit=5, window_seconds=300)
        user = register_with_invite(payload)
        set_login_cookie(response, user)
        return public_auth_response(user)

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        rate_limit(request, "login", limit=10, window_seconds=300)
        user = service.db.get_user_by_username(payload.username.strip())
        if user is None or not verify_password(user.get("password_hash"), payload.password):
            raise HTTPException(status_code=401, detail="用户名或密码错误。")
        set_login_cookie(response, user)
        return public_auth_response(user)

    @app.get("/api/auth/me")
    def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        return public_auth_response(user)

    @app.post("/api/auth/logout")
    def logout(response: Response) -> dict[str, str]:
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(GUEST_COOKIE_NAME, path="/")
        return {"status": "ok"}

    @app.post("/api/invites")
    def create_invite(
        payload: InviteCreateRequest,
        admin: dict[str, Any] = Depends(current_admin),
    ) -> dict[str, Any]:
        raw_code = payload.code.strip()
        invite = service.db.create_invite_code(
            hash_invite_code(raw_code),
            role=payload.role,
            max_uses=payload.max_uses,
            created_by=admin["id"],
        )
        return {
            "id": invite["id"],
            "role": invite["role"],
            "max_uses": invite["max_uses"],
            "uses": invite["uses"],
            "created_at": invite["created_at"],
        }

    @app.post("/api/sessions")
    def create_session(
        payload: CreateSessionRequest,
        response: Response,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        if user is not None:
            return service.create_session(user_id=user["id"], title=payload.title)
        guest_token = create_guest_token()
        set_guest_cookie(response, guest_token)
        return service.create_session(
            user_id=f"{GUEST_USER_PREFIX}{uuid.uuid4()}",
            title=payload.title,
            guest_token=guest_token,
        )

    @app.get("/api/sessions/{session_id}")
    def get_session(
        session_id: str,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return service_call(
            lambda: service.get_session(session_id, user_id=session_owner_id(session_id, request, user))
        )

    @app.post("/api/sessions/{session_id}/start")
    def start_session(
        session_id: str,
        payload: StartRequest,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        rate_limit(request, "turn", limit=30, window_seconds=60)
        owner_id = session_owner_id(session_id, request, user)
        if owner_id is None:
            rate_limit(request, "guest_turn", limit=10, window_seconds=60)
        return service_call(
            lambda: service.start_session(
                session_id,
                payload.model_dump(),
                user_id=owner_id,
            )
        )

    @app.post("/api/sessions/{session_id}/choice")
    def choose(
        session_id: str,
        payload: ChoiceRequest,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        rate_limit(request, "turn", limit=30, window_seconds=60)
        owner_id = session_owner_id(session_id, request, user)
        if owner_id is None:
            rate_limit(request, "guest_turn", limit=10, window_seconds=60)
        return service_call(
            lambda: service.choose(
                session_id,
                payload.model_dump(),
                user_id=owner_id,
            )
        )

    @app.post("/api/sessions/{session_id}/action")
    def act(
        session_id: str,
        payload: ActionRequest,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        rate_limit(request, "turn", limit=30, window_seconds=60)
        owner_id = session_owner_id(session_id, request, user)
        if owner_id is None:
            rate_limit(request, "guest_turn", limit=10, window_seconds=60)
        return service_call(
            lambda: service.act(
                session_id,
                payload.action,
                user_id=owner_id,
            )
        )

    @app.post("/api/sessions/{session_id}/save")
    def save(
        session_id: str,
        payload: SaveRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        return service_call(lambda: service.save(session_id, payload.name, user_id=user["id"]))

    @app.post("/api/sessions/{session_id}/load")
    def load(
        session_id: str,
        payload: SaveRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        return service_call(lambda: service.load(session_id, payload.name, user_id=user["id"]))

    @app.post("/api/sessions/{session_id}/end")
    def end_session(
        session_id: str,
        payload: EndSessionRequest,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return service_call(
            lambda: service.end_session(
                session_id,
                payload.reason,
                user_id=session_owner_id(session_id, request, user),
            )
        )

    @app.get("/api/saves")
    def saves(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return service.list_saves(user["id"])

    @app.get("/api/sessions/{session_id}/death_summary")
    def death_summary(
        session_id: str,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        return service_call(
            lambda: service.death_summary(
                session_id,
                user_id=session_owner_id(session_id, request, user),
            )
        )

    @app.get("/api/users/me/legacy_bonuses")
    def legacy_bonuses(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return service.legacy_bonuses(user["id"])

    @app.get("/api/settings/model")
    def get_model_settings(_admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
        return service.model_settings()

    @app.post("/api/settings/model")
    def post_model_settings(
        payload: ModelSettingsRequest,
        _admin: dict[str, Any] = Depends(current_admin),
    ) -> dict[str, Any]:
        return service.update_model_settings(payload.model_dump())

    frontend_dir = FRONTEND_REACT_DIST if FRONTEND_REACT_DIST.exists() else None
    if frontend_dir is not None and frontend_dir.exists():
        assets_dir = frontend_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    return app


def __getattr__(name: str):
    # uvicorn entrypoint (``web.backend.app:app``), constructed on first access so
    # that importing this module (e.g. ``from web.backend.app import create_app``
    # in tests) does not require DATABASE_URL or open a database connection.
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
