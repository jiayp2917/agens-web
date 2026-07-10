from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response

from .auth import (
    GUEST_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    cookie_kwargs,
    create_session_token,
    parse_session_token,
)
from .security import client_key
from .service import WebGameService
from .service_errors import SessionVersionConflict


def get_service(request: Request) -> WebGameService:
    return request.app.state.service


Service = Annotated[WebGameService, Depends(get_service)]


def current_user(request: Request, service: Service) -> dict[str, Any]:
    claims = parse_session_token(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if claims is None:
        raise HTTPException(status_code=401, detail="请先登录。")
    user = service.db.get_user_by_id(claims.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="登录状态已失效。")
    return user


def optional_user(request: Request, service: Service) -> dict[str, Any] | None:
    claims = parse_session_token(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if claims is None:
        return None
    return service.db.get_user_by_id(claims.user_id)


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
OptionalUser = Annotated[dict[str, Any] | None, Depends(optional_user)]


def current_admin(user: CurrentUser) -> dict[str, Any]:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限。")
    return user


CurrentAdmin = Annotated[dict[str, Any], Depends(current_admin)]


def service_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except SessionVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def rate_limit(
    request: Request,
    action: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    request.app.state.rate_limiter.check(
        client_key(request, action),
        limit=limit,
        window_seconds=window_seconds,
    )


def session_owner_id(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None,
    service: WebGameService,
) -> str | None:
    if user is not None:
        return str(user["id"])
    guest_token = request.cookies.get(GUEST_COOKIE_NAME, "")
    if service.authorize_guest_session(session_id, guest_token):
        return None
    raise HTTPException(status_code=401, detail="访客会话已失效，请从新游戏重新开始。")


def set_login_cookie(response: Response, user: dict[str, Any]) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(str(user["id"])),
        **cookie_kwargs(),
    )


def set_guest_cookie(response: Response, token: str) -> None:
    response.set_cookie(GUEST_COOKIE_NAME, token, **cookie_kwargs())


def discard_guest_session(
    request: Request,
    response: Response,
    service: WebGameService,
) -> None:
    guest_token = request.cookies.get(GUEST_COOKIE_NAME, "")
    if guest_token:
        service.delete_guest_session(guest_token)
    response.delete_cookie(GUEST_COOKIE_NAME, path="/")
