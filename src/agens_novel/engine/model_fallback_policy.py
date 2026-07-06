"""Model fallback policy helpers for GameEngine."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .choices import CHOICE_FALLBACK_NOTICE

MODEL_FAILURE_CONTINUE = "fallback"
MODEL_FAILURE_END = "end"
UPSTREAM_NOT_FOUND_NOTICE = "上游模型配置不可用（HTTP 404），请检查模型名/Base URL 或切回系统默认 Agens；本局已转入本地故事。"
UPSTREAM_AUTH_NOTICE = "上游模型鉴权失败，请检查模型 Key 或切回系统默认 Agens；本局已转入本地故事。"
UPSTREAM_TIMEOUT_NOTICE = "上游模型响应超时，本局已转入本地故事；可稍后重试或切换更稳定的模型。"
MODEL_KEY_UNAVAILABLE_NOTICE = "模型 Key 未配置或不可解密，请在设置中配置个人 Key 或使用有效系统默认；本局已转入本地故事。"

SECRET_MARKERS = (
    "sk-", "api_key", "api-key", "x-api-key", "apikey",
    "authorization", "bearer ", "database_url", "postgresql://",
)

log = logging.getLogger(__name__)


class ModelFallbackPolicy:
    """Decides whether model failure should continue with local story."""

    def __init__(
        self,
        callback_getter: Callable[[], Callable[[str, str], str] | None],
        reason_sanitizer: Callable[[str], str],
    ) -> None:
        self._callback_getter = callback_getter
        self._reason_sanitizer = reason_sanitizer

    def should_continue(self, source: str, reason: str = "") -> bool:
        callback = self._callback_getter()
        if callback is None:
            return True
        try:
            decision = callback(source, reason or "模型输出不可用。")
        except Exception:
            log.exception("model failure choice callback failed")
            return True
        log.info(
            "model failure decision: source=%s decision=%s reason=%s",
            source,
            decision,
            self._reason_sanitizer(reason),
        )
        return decision != MODEL_FAILURE_END

    @staticmethod
    def notice_for(reason: str = "") -> str:
        return public_model_failure_notice(reason)


def public_model_failure_notice(reason: str = "") -> str:
    """Return a player-facing, secret-safe model failure notice."""
    text = (reason or "").strip()
    lowered = text.lower()
    if "agnes_api_key" in lowered or "api key" in lowered or ("key" in lowered and "unavailable" in lowered):
        return MODEL_KEY_UNAVAILABLE_NOTICE
    if "timeout" in lowered or "timed out" in lowered or "超时" in text:
        return UPSTREAM_TIMEOUT_NOTICE
    if _has_http_status(lowered, 404) or "notfound" in lowered or "not found" in lowered:
        return UPSTREAM_NOT_FOUND_NOTICE
    if _has_http_status(lowered, 401) or _has_http_status(lowered, 403) or "unauthorized" in lowered or "forbidden" in lowered:
        return UPSTREAM_AUTH_NOTICE
    if _looks_secret_bearing(text):
        return CHOICE_FALLBACK_NOTICE
    if "不完整" in text or "未返回" in text or "格式" in text:
        return text
    return CHOICE_FALLBACK_NOTICE


def _has_http_status(text: str, status: int) -> bool:
    return bool(re.search(rf"(?:http\s*)?{status}\b", text))


def _looks_secret_bearing(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return True
    return bool(re.search(r"https?://\S+", text))
