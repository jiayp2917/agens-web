"""Narrator Agent node functions.

Takes the player's action + current game state, produces narrative text +
a structured state delta wrapped in ``<state_update>`` tags.

4-node pattern: load_settings → build_prompt → call_agnes_llm → save_artifact

Stream support: when a ``stream_callback`` is present in state, the LLM call
uses streaming and each chunk is forwarded to the callback in real-time.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from ... import paths
from ...artifacts import store
from ...llm.client import LLMError, call_llm, call_llm_stream
from ...llm.types import Message
from ...utils.timing import utcnow_iso
from ..common import load_agent_settings, normalize_choices

log = logging.getLogger(__name__)

AGENT_NAME = "narrator"
_MAX_HISTORY_TURNS = 20


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    return load_agent_settings(AGENT_NAME, state)


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    system_path = paths.system_prompt_path("narrator")
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    game_state_json = state.get("game_state_json", "{}")

    # Build messages: system + chat history + current turn.
    history: list[dict] = list(state.get("chat_history") or [])
    if len(history) > _MAX_HISTORY_TURNS:
        history = history[-_MAX_HISTORY_TURNS:]

    user_content = (
        f"<当前状态>\n{game_state_json}\n</当前状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>"
    )

    messages: list[Message] = [Message(role="system", content=system_message)]
    for entry in history:
        messages.append(Message(
            role=entry.get("role", "user"),
            content=entry.get("content", ""),
        ))
    messages.append(Message(role="user", content=user_content))

    log.info("[narrator.build_prompt] history=%d user=%d", len(history), len(user_input))
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
    }


async def call_agnes_llm(state: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM with streaming support.

    If ``stream_callback`` is present in state, uses ``call_llm_stream``
    which invokes the callback for each text chunk.  Otherwise falls back
    to a normal non-streaming call.
    """
    if not state.get("api_key_set"):
        return {
            "output_text": "", "llm_error": "AGNES_API_KEY 未设置。",
            "elapsed_ms": 0, "usage": {},
        }
    messages: list[Message] = state.get("messages") or []
    if not messages:
        return {
            "output_text": "", "llm_error": "messages 为空。",
            "elapsed_ms": 0, "usage": {},
        }

    stream_callback: Callable[[str], None] | None = state.get("stream_callback")
    # Fallback: try thread-local context (avoids msgpack serialization issues).
    if stream_callback is None:
        from ...engine._stream_context import get as _get_stream_cb
        stream_callback = _get_stream_cb()

    try:
        if stream_callback is not None:
            # Streaming mode: each chunk pushed to callback.
            resp = await call_llm_stream(
                messages,
                model=state.get("model"),
                base_url=state.get("base_url"),
                api_key=state.get("api_key"),
                temperature=0.8,
                max_tokens=1536,
                on_chunk=stream_callback,
            )
        else:
            # Non-streaming fallback.
            resp = await call_llm(
                messages,
                model=state.get("model"),
                base_url=state.get("base_url"),
                api_key=state.get("api_key"),
                temperature=0.8,
                max_tokens=1536,
                stream=False,
            )
        output_text = resp.get("text", "")
        repaired_output = False
        if state.get("repair_incomplete_output"):
            narrative, state_delta, choices = _parse_narrator_output(output_text)
            recoverable_content = bool(narrative) or _has_recoverable_state_delta(state_delta)
            if recoverable_content and (state_delta is None or not narrative or not choices):
                repaired_text = await _repair_incomplete_output(state, output_text, narrative, state_delta)
                if repaired_text:
                    repaired_narrative, repaired_delta, repaired_choices = _parse_narrator_output(repaired_text)
                    if repaired_narrative and repaired_delta is not None and len(repaired_choices) == 4:
                        output_text = repaired_text
                        repaired_output = True
        return {
            "output_text": output_text,
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
            "repaired_output": repaired_output,
        }
    except LLMError as e:
        log.error("[narrator.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse narrative + <state_update> from the LLM output and persist."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        narrative, state_delta, choices = "", {}, []
    else:
        narrative, state_delta, choices = _parse_narrator_output(text)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    store.write_input_snapshot(
        AGENT_NAME, run_id,
        {"user_input": state.get("user_input"), "model": state.get("model")},
    )
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "narrative_chars": len(narrative),
    }
    audit_path = store.write_audit(AGENT_NAME, run_id, audit)
    store.append_global_log({
        "event": "narrator_run_finished", "run_id": run_id,
        "ok": not llm_error, "chars": len(narrative),
    })

    return {
        "narrative": narrative,
        "state_delta": state_delta,
        "choices": choices,
        "repaired_output": bool(state.get("repaired_output")),
        "output_path": str(out_path),
        "audit_path": str(audit_path),
        "finished_at": audit["finished_at"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<state_update>(.*?)</state_update>", re.DOTALL)
_CHOICES_RE = re.compile(r"<choices>(.*?)</choices>", re.DOTALL)
_FENCED_JSON_RE = re.compile(r"```(?:json|JSON)?\s*(?P<body>.*?)```", re.DOTALL)
_ABC_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:选项\s*)?(?:[ABCD]|[1-4])[\.、:：]\s*(?P<text>.+?)\s*$"
)


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

    return narrative, state_delta, choices


def _parse_choices_payload(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        lines = [line.strip(" \t-0123456789.ABCabc、.：:") for line in raw.splitlines()]
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
    depth = 0
    in_string = False
    escaped = False
    for index, current in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                in_string = False
            continue
        if current == '"':
            in_string = True
        elif current == "{":
            depth += 1
        elif current == "}":
            depth -= 1
            if depth == 0:
                trailing = text[index + 1:].strip()
                if trailing and set(trailing) <= {"}"}:
                    try:
                        data = json.loads(text[:index + 1])
                    except (json.JSONDecodeError, ValueError):
                        return None
                    if isinstance(data, dict):
                        log.info("[narrator] repaired extra trailing state_update braces")
                        return data
                return None
            if depth < 0:
                return None
    return None


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
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    raw_json = text[start:index + 1]
                    try:
                        data = json.loads(raw_json)
                    except (json.JSONDecodeError, ValueError):
                        log.warning("[narrator] embedded JSON parse failed: %s", raw_json[:200])
                        break
                    if isinstance(data, dict) and _is_structured_payload(data):
                        return start, index + 1, data
                    break
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


async def _repair_incomplete_output(
    state: dict[str, Any],
    original_text: str,
    narrative: str,
    state_delta: dict[str, Any],
) -> str | None:
    """Ask the same model once to reformat partial output into the contract."""
    if not state.get("api_key_set"):
        return None
    game_state_json = state.get("game_state_json", "{}")
    user_input = state.get("user_input", "")
    repair_prompt = (
        "上一轮输出缺少结构化标签，不能继续游戏。请只根据下面内容补齐格式，不要重写剧情，"
        "不要输出解释或 Markdown 围栏。\n\n"
        "必须输出：\n"
        "1. 叙事正文；如果原叙事为空，请根据当前状态、玩家行动和已解析状态更新补一段简短编年史叙事。\n"
        "2. <state_update>...</state_update>，JSON 对象；没有状态变化时用 {\"character\": {}, \"world\": {}, \"meta\": {}}。\n"
        "3. <choices>...</choices>，JSON 字符串数组，必须恰好 4 条，分别作为 A/B/C/D 行动选项。\n\n"
        "一致性硬规则：\n"
        "- 如果原叙事已经写明玩家实际获得物品或奖励，必须在 character.inventory_add 中补齐最小状态变化。\n"
        "- 如果原叙事已经写明玩家实际习得功法、法术、心法或剑诀，必须在 character.techniques_add 中补齐。\n"
        "- 如果原叙事已经写明玩家实际发现新地点、抵达新区域或开启新地图，必须在 world.discovered_add、world.location 或 world.current_scene 中补齐。\n"
        "- 如果原叙事已经写明玩家实际接取、领取或登记任务，必须在 world.active_quests_add 中补齐。\n"
        "- 如果只是介绍悬赏榜、报酬、NPC 境界或可选任务，还没有实际到账或接取，不要补奖励/任务；保持 delta 为空或只更新当前地点/场景。\n"
        "- 如果无法安全补齐状态变化，请把相关句子改成“尚未落定/尚未入册/尚未领取”，不要让叙事宣称已获得而 state_update 为空。\n\n"
        f"<当前状态>\n{game_state_json}\n</当前状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>\n\n"
        f"<原叙事>\n{narrative or original_text}\n</原叙事>\n\n"
        f"<已解析状态更新>\n{json.dumps(state_delta if isinstance(state_delta, dict) else {}, ensure_ascii=False)}\n</已解析状态更新>"
    )
    messages = [
        Message(
            role="system",
            content="你是输出格式修复器。只补齐 state_update 和 choices 标签，保持世界观和叙事连续。",
        ),
        Message(role="user", content=repair_prompt),
    ]
    try:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=state.get("api_key"),
            temperature=0.2,
            max_tokens=900,
            stream=False,
        )
    except LLMError as exc:
        log.warning("[narrator.repair] failed: %s", exc)
        return None
    repaired_text = str(resp.get("text") or "").strip()
    if not repaired_text:
        return None
    log.info("[narrator.repair] repaired incomplete output")
    return repaired_text
