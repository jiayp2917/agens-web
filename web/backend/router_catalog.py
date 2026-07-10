from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from agens_novel.game.constants import CATALOG_RARITY_TIERS, rarity_unlocked_for

from .app_dependencies import CurrentUser, Service
from .catalog_seed import catalog_as_json

router = APIRouter()


def _catalog(service: Service, table: str) -> list[dict[str, Any]]:
    return [catalog_as_json(row) for row in service.db.list_catalog(table)]


@router.get("/api/catalog/talents")
def talents(service: Service) -> list[dict[str, Any]]:
    return _catalog(service, "catalog_talents")


@router.get("/api/catalog/family_backgrounds")
def family_backgrounds(service: Service) -> list[dict[str, Any]]:
    return _catalog(service, "catalog_family_backgrounds")


@router.get("/api/catalog/spirit_roots")
def spirit_roots(service: Service) -> list[dict[str, Any]]:
    return _catalog(service, "catalog_spirit_roots")


@router.get("/api/catalog/difficulties")
def difficulties(service: Service) -> list[dict[str, Any]]:
    return _catalog(service, "catalog_difficulties")


@router.get("/api/catalog/story_seeds")
def story_seeds(service: Service) -> list[dict[str, Any]]:
    return _catalog(service, "catalog_story_seeds")


@router.get("/api/catalog/rarities")
def rarities(user: CurrentUser, service: Service) -> dict[str, Any]:
    progress = service.db.get_player_progress(user["id"])
    unlocked = rarity_unlocked_for(
        progress["runs_completed"],
        progress["ascension_count"],
    )
    return {
        "tiers": [
            {
                "key": tier["key"],
                "label": tier["label"],
                "weight": tier["weight"],
                "select_requires_runs": tier["select_requires_runs"],
                "select_requires_ascensions": tier["select_requires_ascensions"],
                "random_requires_runs": tier["random_requires_runs"],
                "unlocked": tier["key"] in unlocked,
            }
            for tier in CATALOG_RARITY_TIERS
        ],
        "runs_completed": progress["runs_completed"],
        "ascension_count": progress["ascension_count"],
        "unlocked": unlocked,
    }
