"""Model fallback policy helpers for GameEngine."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .choices import CHOICE_FALLBACK_NOTICE

MODEL_FAILURE_PROMPT = "天道紊乱，是否以因果残影继续推演？"
MODEL_FAILURE_CONTINUE = "fallback"
MODEL_FAILURE_END = "end"

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
        reason = (reason or "").strip()
        if "不完整" in reason or "未返回" in reason or "格式" in reason:
            return reason
        return CHOICE_FALLBACK_NOTICE
