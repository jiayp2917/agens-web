"""Model fallback policy helpers for GameEngine."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .choices import CHOICE_FALLBACK_NOTICE

MODEL_FAILURE_CONTINUE = "fallback"
MODEL_FAILURE_END = "end"
UPSTREAM_NOT_FOUND_NOTICE = "叙事服务配置暂未接通，请检查个人设置或切回系统默认后重试。"
UPSTREAM_AUTH_NOTICE = "叙事服务鉴权未通过，请检查个人设置或切回系统默认后重试。"
UPSTREAM_TIMEOUT_NOTICE = "叙事服务响应过久，请稍后重试或切换更稳定的设置。"
MODEL_KEY_UNAVAILABLE_NOTICE = "叙事服务密钥未配置或不可用，请检查个人设置或使用系统默认。"
MODEL_CONTRACT_UNAVAILABLE_NOTICE = (
    "模型暂不可用，本回合记录暂未续上，已切换本地故事，请直接选择下方选项继续。"
)
MODEL_CONTRACT_MARKERS = (
    "模型已返回",
    "模型输出",
    "状态更新格式不完整",
    "缺少叙事正文",
    "未返回可用",
    "未返回恰好",
    "不完整",
    "未返回",
    "格式",
)

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
    if any(marker in text for marker in MODEL_CONTRACT_MARKERS):
        return MODEL_CONTRACT_UNAVAILABLE_NOTICE
    if _looks_secret_bearing(text):
        return CHOICE_FALLBACK_NOTICE
    return CHOICE_FALLBACK_NOTICE


def _has_http_status(text: str, status: int) -> bool:
    return bool(re.search(rf"(?:http\s*)?{status}\b", text))


def _looks_secret_bearing(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in SECRET_MARKERS):
        return True
    return bool(re.search(r"https?://\S+", text))
