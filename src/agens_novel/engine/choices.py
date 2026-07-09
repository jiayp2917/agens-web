"""Choice normalization and local fallback policy."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from ..session.game_session import GameSession

CHOICE_LABELS = ("A", "B", "C", "D")
CHOICE_FALLBACK_NOTICE = "天道紊乱，暂以因果残影指引。"
# D 语义: "气运" - 随缘/天命，强绑定 luck 属性。UI 固定为第 4 按钮。

_LETTER_PREFIX_RE = re.compile(
    r"^\s*(?:[（(]?\s*[A-Da-d1-4]\s*[）)]?|选项\s*[A-Da-d])"
    r"(?:\s*[\.:：、)）．。\-－—︰﹕：]|\s+(?=(?:稳妥|机遇|风险|气运)\s*[：:]))\s*"
)
_SEMANTIC_WORD_PREFIX_RE = re.compile(r"^\s*(?:稳妥|机遇|风险|气运)\s*[：:]\s*")
_FENCED_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*(?P<body>.*?)```", re.DOTALL)
_STATE_TAG_RE = re.compile(r"<state_update\b[^>]*>.*?</state_update>", re.DOTALL | re.IGNORECASE)
_CHOICES_TAG_RE = re.compile(r"<choices\b[^>]*>.*?</choices>", re.DOTALL | re.IGNORECASE)
_STRUCTURED_JSON_RE = re.compile(
    r"\{[^{}]{0,120}(?:state_delta|state_update|character|world|meta|choices)[^{}]{0,800}\}",
    re.DOTALL,
)
_ENGLISH_VISIBLE_REPLACEMENTS = {
    "prowess": "实战能力",
    "combat": "斗法",
    "inventory": "随身物",
    "technique": "功法",
    "techniques": "功法",
    "state_delta": "状态变更",
    "state_update": "状态变更",
}


def normalize_choices(raw_choices: Any) -> list[str]:
    """Return clean model-choice texts without adding system fallback choices."""
    choices: list[str] = []
    parsed_choices = _coerce_choice_list(raw_choices)
    if isinstance(parsed_choices, list):
        for item in parsed_choices:
            text = _choice_text(item)
            if text:
                choices.append(text)
            if len(choices) == len(CHOICE_LABELS):
                break
    return dedupe_strings(choices)[: len(CHOICE_LABELS)]


def clean_choice_text(text: str) -> str:
    """Strip model-provided A/B/C/D labels from a choice body.

    The UI already renders stable button letters. Keeping model prefixes creates
    duplicated labels such as ``A：A：闭关`` in headed validation.
    """
    cleaned = _unwrap_choice_literal(str(text or "").strip())
    cleaned = clean_visible_text(cleaned, allow_structured=False)
    for _ in range(3):
        next_text = _LETTER_PREFIX_RE.sub("", cleaned, count=1).strip()
        next_text = _SEMANTIC_WORD_PREFIX_RE.sub("", next_text, count=1).strip()
        if next_text == cleaned:
            break
        cleaned = next_text
    return cleaned


def clean_visible_text(text: str, *, allow_structured: bool = True) -> str:
    """Remove model contract debris from text that may be shown to players."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = _FENCED_BLOCK_RE.sub(lambda match: match.group("body").strip(), cleaned)
    cleaned = _STATE_TAG_RE.sub("", cleaned)
    cleaned = _CHOICES_TAG_RE.sub("", cleaned)
    if not allow_structured:
        cleaned = _STRUCTURED_JSON_RE.sub("", cleaned)
        cleaned = _strip_embedded_structured_objects(cleaned)
    for source, target in _ENGLISH_VISIBLE_REPLACEMENTS.items():
        cleaned = re.sub(rf"\b{re.escape(source)}\b", target, cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" \t\r\n\"'[]")


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
    phase = max(0, int(getattr(session, "turn_count", 0) or 0)) // 4
    options = (
        (
            f"【稳妥】在{location}稳住气息，观察灵气与地势变化",
            f"【机遇】寻找附近修士交谈，打听当前机缘与风险",
            "【风险】外出历练，寻找护持与关键线索",
        ),
        (
            f"【稳妥】整理在{location}的修行所得，稳固道心与根基",
            "【机遇】拜访同门或坊市，寻找下一阶段的线索",
            "【风险】接取外出委托，用历练换取下一阶段准备",
        ),
        (
            f"【稳妥】复盘近年因果，在{location}补足短板",
            "【机遇】追查传闻中的遗迹、讲法或贵人",
            "【风险】深入险地验证所学，承担伤势与失败代价",
        ),
    )
    steady, opportunity, risk = options[min(phase, len(options) - 1)]
    return [steady, opportunity, risk, "【气运】随缘而行，听天命、赌因果"]


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
    return clean_choice_text(text)


def _coerce_choice_list(value: Any) -> Any:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value
    parsed = _parse_literal(value)
    return parsed if isinstance(parsed, list) else value


def _unwrap_choice_literal(text: str) -> str:
    parsed = _parse_literal(text)
    if isinstance(parsed, list) and parsed:
        # Some providers return each option as "['actual choice']".
        if len(parsed) == 1:
            return str(parsed[0]).strip()
        return str(parsed[0]).strip()
    if isinstance(parsed, dict):
        for key in ("action", "text", "label", "choice"):
            if parsed.get(key):
                return str(parsed[key]).strip()
    return text


def _parse_literal(text: str) -> Any:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    if stripped[:1] not in {"[", "{"}:
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    try:
        return ast.literal_eval(stripped)
    except (ValueError, SyntaxError, TypeError):
        return None


def _strip_embedded_structured_objects(text: str) -> str:
    source = str(text or "")
    out: list[str] = []
    index = 0
    while index < len(source):
        if source[index] != "{":
            out.append(source[index])
            index += 1
            continue
        end = _balanced_json_object_end(source, index)
        if end <= index:
            out.append(source[index])
            index += 1
            continue
        chunk = source[index:end]
        parsed = _parse_literal(chunk)
        if isinstance(parsed, dict):
            index = end
            continue
        out.append(source[index])
        index += 1
    return "".join(out)


def _balanced_json_object_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    quote = ""
    for index in range(start, len(text)):
        current = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                in_string = False
            continue
        if current in {"'", '"'}:
            in_string = True
            quote = current
        elif current == "{":
            depth += 1
        elif current == "}":
            depth -= 1
            if depth == 0:
                return index + 1
            if depth < 0:
                return -1
    return -1
