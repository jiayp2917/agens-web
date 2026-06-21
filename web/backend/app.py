"""FastAPI application for agens-web."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
from .security import BodySizeLimitMiddleware, RateLimiter, client_key, enforce_same_origin
from .service import GUEST_USER_PREFIX, WebGameService, is_guest_user_id

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
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
    game_name: str = ""
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


def validate_runtime_config() -> None:
    backend = os.environ.get("DATABASE_BACKEND", "sqlite").strip().lower()
    env = os.environ.get("AGENS_ENV", "").strip().lower()
    production = env in ("prod", "production") or backend in ("postgres", "postgresql", "pg")
    if not production:
        return

    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret or session_secret == DEV_SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET must be set to a non-default value in production.")
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required in production.")
    if not os.environ.get("INVITE_ADMIN_CODE", "").strip():
        raise RuntimeError("INVITE_ADMIN_CODE is required in production.")


def create_app(db_path: Path | None = None) -> FastAPI:
    validate_runtime_config()
    service = WebGameService(create_database(db_path))
    app = FastAPI(title="agens-web", version="0.1.0", dependencies=[Depends(enforce_same_origin)])
    app.state.service = service
    app.state.rate_limiter = RateLimiter()
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
        payload: dict[str, Any],
        admin: dict[str, Any] = Depends(current_admin),
    ) -> dict[str, Any]:
        raw_code = str(payload.get("code") or "").strip()
        if len(raw_code) < 8:
            raise HTTPException(status_code=422, detail="邀请码至少 8 个字符。")
        role = str(payload.get("role") or "user").strip().lower()
        if role not in ("user", "admin"):
            raise HTTPException(status_code=422, detail="邀请码角色无效。")
        max_uses = int(payload.get("max_uses") or 1)
        if max_uses < 1 or max_uses > 100:
            raise HTTPException(status_code=422, detail="邀请码可用次数无效。")
        invite = service.db.create_invite_code(
            hash_invite_code(raw_code),
            role=role,
            max_uses=max_uses,
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
        try:
            return service.get_session(session_id, user_id=session_owner_id(session_id, request, user))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

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
        try:
            return service.start_session(
                session_id,
                payload.model_dump(),
                user_id=owner_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

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
        try:
            return service.choose(
                session_id,
                payload.model_dump(),
                user_id=owner_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

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
        try:
            return service.act(
                session_id,
                payload.action,
                user_id=owner_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/save")
    def save(
        session_id: str,
        payload: SaveRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return service.save(session_id, payload.name, user_id=user["id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/load")
    def load(
        session_id: str,
        payload: SaveRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return service.load(session_id, payload.name, user_id=user["id"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/end")
    def end_session(
        session_id: str,
        payload: EndSessionRequest,
        request: Request,
        user: dict[str, Any] | None = Depends(optional_user),
    ) -> dict[str, Any]:
        try:
            return service.end_session(
                session_id,
                payload.reason,
                user_id=session_owner_id(session_id, request, user),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get("/api/saves")
    def saves(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return service.list_saves(user["id"])

    @app.get("/api/settings/model")
    def get_model_settings(_admin: dict[str, Any] = Depends(current_admin)) -> dict[str, Any]:
        return service.model_settings()

    @app.post("/api/settings/model")
    def post_model_settings(
        payload: ModelSettingsRequest,
        _admin: dict[str, Any] = Depends(current_admin),
    ) -> dict[str, Any]:
        return service.update_model_settings(payload.model_dump())

    frontend_dir = FRONTEND_REACT_DIST if FRONTEND_REACT_DIST.exists() else FRONTEND_DIR
    if frontend_dir.exists():
        legacy_assets_dir = FRONTEND_DIR / "assets"
        assets_dir = legacy_assets_dir if legacy_assets_dir.exists() else frontend_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    return app


app = create_app()
