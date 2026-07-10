from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .app_dependencies import CurrentAdmin, CurrentUser, Service, service_call
from .app_models import ModelSettingsRequest

router = APIRouter()


@router.get("/api/settings/model")
def get_model_settings(user: CurrentUser, service: Service) -> dict[str, Any]:
    return service.model_settings(user["id"])


@router.post("/api/settings/model")
def post_model_settings(
    payload: ModelSettingsRequest,
    user: CurrentUser,
    service: Service,
) -> dict[str, Any]:
    return service_call(
        lambda: service.update_model_settings(user["id"], payload.model_dump())
    )


@router.delete("/api/settings/model")
def delete_model_settings(user: CurrentUser, service: Service) -> dict[str, Any]:
    return service_call(lambda: service.clear_model_settings(user["id"]))


@router.get("/api/admin/settings/model")
def get_admin_model_settings(_admin: CurrentAdmin, service: Service) -> dict[str, Any]:
    return service.admin_model_settings()


@router.post("/api/admin/settings/model")
def post_admin_model_settings(
    payload: ModelSettingsRequest,
    _admin: CurrentAdmin,
    service: Service,
) -> dict[str, Any]:
    return service_call(lambda: service.update_admin_model_settings(payload.model_dump()))
