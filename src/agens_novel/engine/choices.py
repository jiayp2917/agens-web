"""Choice normalization and local fallback policy."""

from __future__ import annotations

from typing import Any

from ..session.game_session import GameSession

CHOICE_LABELS = ("A", "B", "C", "D")
CHOICE_FALLBACK_NOTICE = "天道紊乱，暂以因果残影指引。"
# D 语义: "气运" - 随缘/天命，强绑定 luck 属性。UI 固定为第 4 按钮。


def normalize_choices(raw_choices: Any) -> list[str]:
    """Return clean model-choice texts without adding system fallback choices."""
    choices: list[str] = []
    if isinstance(raw_choices, list):
        for item in raw_choices:
            text = _choice_text(item)
            if text:
                choices.append(text)
            if len(choices) == len(CHOICE_LABELS):
                break
    return dedupe_strings(choices)[: len(CHOICE_LABELS)]


def complete_choices(raw_choices: Any, session: GameSession) -> list[str]:
    """Return exactly 4 choices with stable A/B/C/D semantics.

    Model output may still contain only A/B/C. Game-mode v5 keeps those
    choices when present, then fills missing slots with local semantic
    fallbacks so D is always the luck/fate path.
    """
    choices = normalize_choices(raw_choices)
    if not choices:
        return []
    if len(choices) >= len(CHOICE_LABELS):
        return choices[: len(CHOICE_LABELS)]

    fallbacks = fallback_choices(session)
    completed: list[str] = []
    for index in range(len(CHOICE_LABELS)):
        if index < len(choices) and choices[index]:
            completed.append(choices[index])
        else:
            completed.append(fallbacks[index])
    return completed[: len(CHOICE_LABELS)]


def fallback_choices(session: GameSession) -> list[str]:
    """Generate 4 grounded fallback choices (A/B/C/D semantics)."""
    location = session.location or "当前地点"
    return [
        f"【稳妥】在{location}稳住气息，观察灵气与地势变化",
        f"【机遇】寻找附近修士交谈，打听当前机缘与风险",
        "【风险】检查随身物品、功法与破境准备",
        "【气运】随缘而行，听天命、赌因果",
    ]


def dedupe_strings(values: list[Any]) -> list[str]:
    """Return unique non-empty strings while preserving order."""
    out: list[str] = []
    for value in values:
        text = value.strip() if isinstance(value, str) else ""
        if text and text not in out:
            out.append(text)
    return out


def _choice_text(item: Any) -> str:
    """Extract display/action text from a model choice object."""
    if isinstance(item, str):
        text = item
    elif isinstance(item, dict):
        value = item.get("action") or item.get("text") or item.get("label")
        text = str(value) if value is not None else ""
    else:
        text = ""
    text = text.strip()
    for prefix in ("A.", "B.", "C.", "D.", "A、", "B、", "C、", "D、", "A:", "B:", "C:", "D:"):
        if text.upper().startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text
