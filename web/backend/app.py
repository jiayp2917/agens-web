"""FastAPI application for agens-web."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import WebDatabase
from .service import WebGameService

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class LoginRequest(BaseModel):
    username: str = "local"


class CreateSessionRequest(BaseModel):
    user_id: str = ""
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
    provider: str = "Agens"
    base_url: str = "https://apihub.agnes-ai.com/v1"
    model: str = "agnes-2.0-flash"
    api_key: str = ""


def create_app(db_path: Path | None = None) -> FastAPI:
    service = WebGameService(WebDatabase(db_path))
    app = FastAPI(title="agens-web", version="0.1.0")
    app.state.service = service

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/users/login")
    def login(payload: LoginRequest) -> dict[str, Any]:
        return service.login(payload.username)

    @app.post("/api/sessions")
    def create_session(payload: CreateSessionRequest) -> dict[str, Any]:
        return service.create_session(user_id=payload.user_id, title=payload.title)

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            return service.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/start")
    def start_session(session_id: str, payload: StartRequest) -> dict[str, Any]:
        try:
            return service.start_session(session_id, payload.model_dump())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/choice")
    def choose(session_id: str, payload: ChoiceRequest) -> dict[str, Any]:
        try:
            return service.choose(session_id, payload.model_dump())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/action")
    def act(session_id: str, payload: ActionRequest) -> dict[str, Any]:
        try:
            return service.act(session_id, payload.action)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/save")
    def save(session_id: str, payload: SaveRequest) -> dict[str, Any]:
        try:
            return service.save(session_id, payload.name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/load")
    def load(session_id: str, payload: SaveRequest) -> dict[str, Any]:
        try:
            return service.load(session_id, payload.name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/sessions/{session_id}/end")
    def end_session(session_id: str, payload: EndSessionRequest) -> dict[str, Any]:
        try:
            return service.end_session(session_id, payload.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/saves")
    def saves(user_id: str = "") -> list[dict[str, Any]]:
        return service.list_saves(user_id)

    @app.get("/api/settings/model")
    def get_model_settings() -> dict[str, Any]:
        return service.model_settings()

    @app.post("/api/settings/model")
    def post_model_settings(payload: ModelSettingsRequest) -> dict[str, Any]:
        return service.update_model_settings(payload.model_dump())

    if FRONTEND_DIR.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
