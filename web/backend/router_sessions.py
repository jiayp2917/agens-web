from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request, Response

from .app_dependencies import (
    CurrentUser,
    OptionalUser,
    Service,
    rate_limit,
    service_call,
    session_owner_id,
    set_guest_cookie,
)
from .app_models import (
    ActionRequest,
    ChoiceRequest,
    CreateSessionRequest,
    EndSessionRequest,
    SaveRequest,
    StartRequest,
)
from .auth import create_guest_token
from .service import GUEST_USER_PREFIX

router = APIRouter()


@router.post("/api/sessions")
def create_session(
    payload: CreateSessionRequest,
    response: Response,
    user: OptionalUser,
    service: Service,
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


@router.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = session_owner_id(session_id, request, user, service)
    return service_call(lambda: service.get_session(session_id, user_id=owner))


def _turn_owner(
    session_id: str,
    request: Request,
    user: dict[str, Any] | None,
    service: Service,
) -> str | None:
    rate_limit(request, "turn", limit=30, window_seconds=60)
    owner = session_owner_id(session_id, request, user, service)
    if owner is None:
        rate_limit(request, "guest_turn", limit=10, window_seconds=60)
    return owner


@router.post("/api/sessions/{session_id}/start")
def start_session(
    session_id: str,
    payload: StartRequest,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = _turn_owner(session_id, request, user, service)
    return service_call(
        lambda: service.start_session(session_id, payload.model_dump(), user_id=owner)
    )


@router.post("/api/sessions/{session_id}/choice")
def choose(
    session_id: str,
    payload: ChoiceRequest,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = _turn_owner(session_id, request, user, service)
    return service_call(lambda: service.choose(session_id, payload.model_dump(), user_id=owner))


@router.post("/api/sessions/{session_id}/action")
def act(
    session_id: str,
    payload: ActionRequest,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = _turn_owner(session_id, request, user, service)
    return service_call(lambda: service.act(session_id, payload.model_dump(), user_id=owner))


@router.post("/api/sessions/{session_id}/save")
def save(
    session_id: str,
    payload: SaveRequest,
    user: CurrentUser,
    service: Service,
) -> dict[str, Any]:
    return service_call(
        lambda: service.save(session_id, payload.model_dump(), user_id=user["id"])
    )


@router.post("/api/sessions/{session_id}/load")
def load(
    session_id: str,
    payload: SaveRequest,
    user: CurrentUser,
    service: Service,
) -> dict[str, Any]:
    return service_call(
        lambda: service.load(session_id, payload.model_dump(), user_id=user["id"])
    )


@router.post("/api/sessions/{session_id}/end")
def end_session(
    session_id: str,
    payload: EndSessionRequest,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = session_owner_id(session_id, request, user, service)
    return service_call(
        lambda: service.end_session(session_id, payload.model_dump(), user_id=owner)
    )


@router.get("/api/saves")
def saves(user: CurrentUser, service: Service) -> list[dict[str, Any]]:
    return service.list_saves(user["id"])


@router.get("/api/sessions/{session_id}/death_summary")
def death_summary(
    session_id: str,
    request: Request,
    user: OptionalUser,
    service: Service,
) -> dict[str, Any]:
    owner = session_owner_id(session_id, request, user, service)
    return service_call(lambda: service.death_summary(session_id, user_id=owner))


@router.get("/api/users/me/legacy_bonuses")
def legacy_bonuses(user: CurrentUser, service: Service) -> list[dict[str, Any]]:
    return service.legacy_bonuses(user["id"])
