"""Narrator response parsing and player-visible contract diagnostics."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...engine.choices import clean_visible_text
from ...engine.history import render_history_entry
from ..common import normalize_choices

log = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<state_update>(.*?)</state_update>", re.DOTALL)
_CHOICES_RE = re.compile(r"<choices>(.*?)</choices>", re.DOTALL)
_FENCED_JSON_RE = re.compile(r"```(?:json|JSON)?\s*(?P<body>.*?)```", re.DOTALL)
_ABC_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:选项\s*)?(?:[ABCD]|[1-4])[\.、:：]\s*(?P<text>.+?)\s*$"
)
_VISIBLE_STRUCTURED_RE = re.compile(r"(<state_update|</state_update>|<choices|</choices>|```|\{|\}|\[[\"'])", re.IGNORECASE)
_VISIBLE_ENGLISH_RE = re.compile(r"[A-Za-z]{2,}")


def _parse_narrator_output(text: str) -> tuple[str, dict | None, list[str]]:
    """Extract (narrative, state_delta, choices) from the narrator LLM output.

    The narrative is everything before the first structured tag.
    The delta is parsed as JSON from within ``<state_update>``.
    Choices can be emitted as ``<choices>["...", "...", "..."]</choices>``
    or as ``meta.choices`` inside the state update.
    """
    text = _strip_markdown_json_fences(text)
    narrative = text
    state_delta: dict | None = None
    choices: list[str] = []
    json_span: tuple[int, int] | None = None
    json_narrative = ""

    m = _TAG_RE.search(text)
    if m:
        raw_json = m.group(1).strip()
        data = _parse_state_update_json(raw_json)
        if isinstance(data, dict):
            state_delta = data
            choices = normalize_choices(data.get("meta", {}).get("choices"))
        else:
            state_delta = None
            log.warning("[narrator] state_update JSON parse failed: %s", raw_json[:200])
    else:
        json_match = _find_embedded_json_object(text)
        if json_match:
            start, end, data = json_match
            state_delta = _state_delta_from_payload(data)
            choices = _choices_from_payload(data)
            json_narrative = str(data.get("narrative") or data.get("text") or "").strip()
            json_span = (start, end)

    choices_match = _CHOICES_RE.search(text)
    if choices_match:
        choices = normalize_choices(_parse_choices_payload(choices_match.group(1).strip())) or choices
    if not choices:
        choices = _parse_inline_abc_choices(text)

    tag_starts = [match.start() for match in (m, choices_match) if match]
    if tag_starts:
        narrative = text[: min(tag_starts)].strip()
    elif json_span:
        narrative = (text[:json_span[0]] + text[json_span[1]:]).strip() or json_narrative
    if choices:
        narrative = _strip_inline_choice_lines(narrative)

    return clean_visible_text(narrative, allow_structured=False), state_delta, choices


def _unwrap_narrator_envelope(text: str) -> str | None:
    try:
        payload = json.loads(str(text or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    required = {"narrative", "choices"}
    if not isinstance(payload, dict) or set(payload) != required:
        return None
    narrative = payload.get("narrative")
    choices = payload.get("choices")
    if not isinstance(narrative, str) or not narrative.strip():
        return None
    normalized_choices = normalize_choices(choices)
    if len(normalized_choices) != 4:
        return None
    return (
        f"{narrative.strip()}\n"
        f"<choices>{json.dumps(normalized_choices, ensure_ascii=False)}</choices>"
    )


def _schema_safe_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove legacy tag examples before sending history to schema-mode models."""
    cleaned: list[dict[str, Any]] = []
    for entry in history:
        role = str(entry.get("role") or "user")
        content = render_history_entry(entry)
        if role == "assistant":
            narrative, _delta, _choices = _parse_narrator_output(content)
            content = narrative or clean_visible_text(content, allow_structured=False)
        if content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _contract_diagnostics(
    raw_text: str,
    narrative: str,
    state_delta: Any,
    choices: list[str],
) -> dict[str, Any]:
    """Return non-secret narrator contract facts for logs and evidence."""
    narrative_english_residue = bool(_VISIBLE_ENGLISH_RE.search(str(narrative or "")))
    choice_english_indices = [
        index
        for index, choice in enumerate(choices)
        if _VISIBLE_ENGLISH_RE.search(str(choice or ""))
    ]
    visible_text = "\n".join([str(narrative or ""), *[str(choice or "") for choice in choices]])
    return {
        "missing_narrative": not bool(str(narrative or "").strip()),
        "missing_state_update": not isinstance(state_delta, dict),
        "choices_count": len(choices),
        "choices_count_ok": len(choices) == 4,
        "raw_has_state_update_tag": bool(_TAG_RE.search(str(raw_text or ""))),
        "raw_has_choices_tag": bool(_CHOICES_RE.search(str(raw_text or ""))),
        "structured_residue": bool(_VISIBLE_STRUCTURED_RE.search(visible_text)),
        "english_residue": narrative_english_residue or bool(choice_english_indices),
        "narrative_english_residue": narrative_english_residue,
        "choice_english_indices": choice_english_indices,
    }


def _parse_choices_payload(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        try:
            import ast
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError, TypeError):
            pass
        lines = [
            re.sub(r"^\s*[-0123456789.ABCabc、.：:]+\s*", "", line).strip()
            for line in raw.splitlines()
        ]
        return [line for line in lines if line]


def _parse_state_update_json(raw: str) -> dict[str, Any] | None:
    """Parse a state_update object, tolerating only extra trailing right braces."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = _parse_json_object_with_trailing_braces(raw)
    return data if isinstance(data, dict) else None


def _parse_json_object_with_trailing_braces(raw: str) -> dict[str, Any] | None:
    """Recover provider drift like ``{...}}`` without accepting arbitrary junk."""
    text = str(raw or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data, end = json.JSONDecoder().raw_decode(text)
    except (json.JSONDecodeError, ValueError):
        return None
    trailing = text[end:].strip()
    if not trailing or set(trailing) > {"}"} or not isinstance(data, dict):
        return None
    log.info("[narrator] repaired extra trailing state_update braces")
    return data


def _parse_inline_abc_choices(text: str) -> list[str]:
    """Parse explicit bare A/B/C lines without inventing choices from prose."""
    found: list[str] = []
    for match in _ABC_LINE_RE.finditer(text):
        choice = match.group("text").strip()
        if choice:
            found.append(choice)
        if len(found) == 4:
            break
    return normalize_choices(found) if len(found) >= 3 else []


def _strip_markdown_json_fences(text: str) -> str:
    """Remove Markdown fence wrappers while keeping their inner content parseable."""
    return _FENCED_JSON_RE.sub(lambda match: match.group("body").strip(), str(text or "")).strip()


def _find_embedded_json_object(text: str) -> tuple[int, int, dict[str, Any]] | None:
    """Find the first balanced JSON object that matches the narrator contract."""
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            data, length = json.JSONDecoder().raw_decode(text[start:])
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and _is_structured_payload(data):
            return start, start + length, data
    return None


def _is_structured_payload(data: dict[str, Any]) -> bool:
    """Return whether a bare JSON object is likely the narrator contract."""
    if isinstance(data.get("state_delta"), dict) or isinstance(data.get("state_update"), dict):
        return True
    return isinstance(data.get("character"), dict) or isinstance(data.get("world"), dict)


def _state_delta_from_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Accept either a raw state_delta or a wrapper object from fenced JSON."""
    if isinstance(data.get("state_delta"), dict):
        return data["state_delta"]
    if isinstance(data.get("state_update"), dict):
        return data["state_update"]
    allowed = {key: data.get(key) for key in ("character", "world", "meta") if isinstance(data.get(key), dict)}
    return allowed


def _choices_from_payload(data: dict[str, Any]) -> list[str]:
    raw = data.get("choices")
    if isinstance(raw, dict):
        ordered = [raw.get(key) for key in ("A", "B", "C", "D", "1", "2", "3", "4")]
        raw = [item for item in ordered if item]
    if not raw and isinstance(data.get("meta"), dict):
        raw = data["meta"].get("choices")
    return normalize_choices(raw)


def _strip_inline_choice_lines(text: str) -> str:
    """Remove parsed A/B/C/D option lines from the visible narrative."""
    lines = [
        line for line in str(text or "").splitlines()
        if not _ABC_LINE_RE.match(line)
    ]
    return "\n".join(lines).strip()


def _has_recoverable_state_delta(state_delta: Any) -> bool:
    """Return whether a JSON-only model output has enough structure to repair."""
    if not isinstance(state_delta, dict) or not state_delta:
        return False
    for value in state_delta.values():
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
        if value not in (None, "", False):
            return True
    return False
