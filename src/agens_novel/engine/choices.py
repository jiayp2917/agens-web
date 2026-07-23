"""Choice normalization and local fallback policy."""

from __future__ import annotations

import ast
import json
import re
from typing import TYPE_CHECKING, Any

from ..utils.strings import dedupe_strings

if TYPE_CHECKING:
    from ..session.game_session import GameSession

CHOICE_LABELS = ("A", "B", "C", "D")
CHOICE_SEMANTICS = ("稳妥", "机遇", "风险", "气运")
CHOICE_FALLBACK_NOTICE = "模型暂不可用，已切换本地故事，请直接选择下方选项继续。"
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
_QUOTED_CHOICE_FRAGMENT_RE = re.compile(
    r'(?:[\[\n]\s*)?(?:\\?["“][^"“”\n]{4,160}\\?["”]\s*[,，]\s*){3}\\?["“][^"“”\n]{4,160}\\?["”]\s*(?:\]|$)'
)
_VISIBLE_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]{2,}")
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
        cleaned = _QUOTED_CHOICE_FRAGMENT_RE.sub("", cleaned)
    for source, target in _ENGLISH_VISIBLE_REPLACEMENTS.items():
        cleaned = re.sub(rf"\b{re.escape(source)}\b", target, cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" \t\r\n\"'[]")


def has_visible_english(text: str) -> bool:
    """Return whether player-visible prose still contains an English word."""
    return bool(_VISIBLE_ENGLISH_WORD_RE.search(str(text or "")))


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


def choice_with_semantic(index: int, text: str) -> str:
    """Preserve the route category when a UI submits a choice by index or letter."""
    body = clean_choice_text(text)
    if 0 <= index < len(CHOICE_LABELS):
        return f"{CHOICE_LABELS[index]}【{CHOICE_SEMANTICS[index]}】{body}"
    return body


def fallback_choices(session: GameSession) -> list[str]:
    """Generate 4 grounded fallback choices (A/B/C/D semantics)."""
    raw_location = str(session.location or "").strip()
    location = raw_location if raw_location and not has_visible_english(raw_location) else "当前地点"
    story_choices = _story_grounded_choices(session, location)
    if story_choices:
        return story_choices
    phase = max(0, int(getattr(session, "turn_count", 0) or 0)) // 4
    options = (
        (
            f"【稳妥】在{location}稳住气息，观察灵气与地势变化",
            "【机遇】寻找附近修士交谈，打听当前机缘与风险",
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


def _story_grounded_choices(session: GameSession, location: str) -> list[str]:
    state = getattr(session, "story_state", None)
    if not isinstance(state, dict) or state.get("status") != "active":
        return []
    goal = str(state.get("stage_goal") or "").strip()
    threads = state.get("unresolved_threads")
    thread = ""
    if isinstance(threads, list):
        thread = next((str(item).strip() for item in threads if str(item).strip()), "")
    if not goal and not thread:
        return []
    subject = thread or goal
    return [
        f"【稳妥】留在{location}核对旧档，稳步推进“{goal or subject}”",
        f"【机遇】拜访知情者，追问“{subject}”的新线索",
        f"【风险】亲赴相关地点验证“{subject}”，承担暴露与受伤风险",
        f"【气运】暂留最后一手，观察“{subject}”是否出现新的命数回响",
    ]


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
    quote = ""
    escaped = False
    for index in range(start, len(text)):
        depth, quote, escaped = _advance_object_scan(text[index], depth, quote, escaped)
        if depth == 0:
            return index + 1
        if depth < 0:
            return -1
    return -1


def _advance_object_scan(
    current: str,
    depth: int,
    quote: str,
    escaped: bool,
) -> tuple[int, str, bool]:
    if quote:
        if escaped:
            return depth, quote, False
        if current == "\\":
            return depth, quote, True
        if current == quote:
            return depth, "", False
        return depth, quote, False
    if current in {"'", '"'}:
        return depth, current, False
    if current == "{":
        return depth + 1, quote, False
    if current == "}":
        return depth - 1, quote, False
    return depth, quote, False
