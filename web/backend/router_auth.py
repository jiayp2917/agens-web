from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from .app_dependencies import (
    CurrentAdmin,
    CurrentUser,
    Service,
    discard_guest_session,
    rate_limit,
    set_login_cookie,
)
from .app_models import InviteCreateRequest, LoginRequest, RegisterRequest
from .auth import (
    GUEST_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    hash_invite_code,
    hash_password,
    public_auth_response,
    verify_password,
)

router = APIRouter()


@router.post("/api/auth/register")
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: Service,
) -> dict[str, Any]:
    rate_limit(request, "register", limit=5, window_seconds=300)
    invite_code = payload.invite_code.strip()
    admin_code = os.environ.get("INVITE_ADMIN_CODE", "").strip()
    try:
        user = service.db.register_user_atomic(
            payload.username.strip(),
            hash_password(payload.password),
            invite_code_hash=hash_invite_code(invite_code),
            bootstrap_admin=bool(admin_code and invite_code == admin_code),
        )
    except ValueError as exc:
        status = 409 if "用户名" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="注册失败，请检查输入。") from exc
    discard_guest_session(request, response, service)
    set_login_cookie(response, user)
    return public_auth_response(user)


@router.post("/api/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Service,
) -> dict[str, Any]:
    rate_limit(request, "login", limit=10, window_seconds=300)
    user = service.db.get_user_by_username(payload.username.strip())
    if user is None or not verify_password(user.get("password_hash"), payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    discard_guest_session(request, response, service)
    set_login_cookie(response, user)
    return public_auth_response(user)


@router.get("/api/auth/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return public_auth_response(user)


@router.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(GUEST_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.post("/api/invites")
def create_invite(
    payload: InviteCreateRequest,
    admin: CurrentAdmin,
    service: Service,
) -> dict[str, Any]:
    invite = service.db.create_invite_code(
        hash_invite_code(payload.code.strip()),
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
