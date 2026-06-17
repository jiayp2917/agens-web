"""Choice normalization and local fallback policy."""

from __future__ import annotations

from typing import Any

from ..session.game_session import GameSession

CHOICE_LABELS = ("A", "B", "C")
CHOICE_FALLBACK_NOTICE = "天道紊乱，暂以因果残影指引。"


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


def fallback_choices(session: GameSession) -> list[str]:
    """Generate grounded fallback choices when model choices are unavailable."""
    location = session.location or "当前地点"
    if session.combat:
        return ["谨慎防守并观察敌人破绽", "施展最熟悉的功法", "寻找脱身路线"]
    return [
        f"在{location}稳住气息，观察灵气与地势变化",
        "寻找附近修士交谈，打听当前机缘与风险",
        "检查随身物品、功法与破境准备",
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
    for prefix in ("A.", "B.", "C.", "A、", "B、", "C、", "A:", "B:", "C:"):
        if text.upper().startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text
