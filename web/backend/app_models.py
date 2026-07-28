"""FastAPI request models for agens-web."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$")
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class CreateSessionRequest(BaseModel):
    title: str = "新局"


class MutationRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    expected_version: int = Field(ge=0)


class StartRequest(MutationRequest):
    char_name: str = ""
    talent: str = ""
    spirit_root: str = ""
    family_background: str = ""
    difficulty: str = "普通"
    attributes: dict[str, int] = Field(default_factory=dict)
    randomize_attributes: bool = False


class ChoiceRequest(MutationRequest):
    choice: str = ""
    choice_index: int | None = None


class ActionRequest(MutationRequest):
    action: str


class SaveRequest(MutationRequest):
    name: str = "slot_1"


class EndSessionRequest(MutationRequest):
    reason: str = "玩家结束本局。"


class ModelSettingsRequest(BaseModel):
    provider: str = Field(default="Agens", max_length=64)
    base_url: str = Field(default="https://apihub.agnes-ai.com/v1", max_length=512)
    model: str = Field(default="agnes-2.0-flash", max_length=128)
    response_mode: str = Field(default="json_object", pattern=r"^(json_schema|json_object)$")
    stream: bool = False
    api_key: str = Field(default="", max_length=512)


class InviteCreateRequest(BaseModel):
    code: str = Field(min_length=8, max_length=256)
    role: str = Field(default="user", pattern=r"^(user|admin)$")
    max_uses: int = Field(default=1, ge=1, le=100)
