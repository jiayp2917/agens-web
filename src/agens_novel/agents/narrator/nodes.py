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
from collections.abc import Callable
from typing import Any

from ... import paths
from ...artifacts import store
from ...engine.choices import clean_visible_text
from ...engine.history import render_history_entry
from ...llm.client import LLMError, call_llm, call_llm_stream
from ...llm.provider_adapter import ProviderTransport, narrator_transport, response_format
from ...llm.runtime_context import runtime_api_key
from ...llm.types import Message
from ...utils.timing import utcnow_iso
from ..common import load_agent_settings, normalize_choices
from ..common import prompt_metrics as _prompt_metrics
from ..contracts import NarratorEnvelopeV1

log = logging.getLogger(__name__)

AGENT_NAME = "narrator"
_RECENT_HISTORY_MESSAGES = 6
# Prompt soft cap: compress to opening + summary stub + recent window once
# chat_history exceeds this. Deliberately below the storage cap (20, set in
# record_turn) so the narrator prompt stays bounded as the conversation grows —
# without it, the compression branch never fires and all 20 stored entries are
# sent verbatim, which correlates with rising repair rates at high history counts.
_HISTORY_PROMPT_SOFT_CAP = _RECENT_HISTORY_MESSAGES + 1
_NO_ASCII_LETTERS_PATTERN = r"^[^A-Za-z]*$"
_NARRATOR_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "narrator_envelope",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "narrative": {"type": "string", "pattern": _NO_ASCII_LETTERS_PATTERN},
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": _NO_ASCII_LETTERS_PATTERN,
                    },
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
            "required": ["narrative", "choices"],
            "additionalProperties": False,
        },
    },
}


def load_settings(state: dict[str, Any]) -> dict[str, Any]:
    return load_agent_settings(AGENT_NAME, state)


def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
    transport = narrator_transport(state)
    provider_json_schema = transport == ProviderTransport.JSON_SCHEMA
    provider_json_object = transport == ProviderTransport.JSON_OBJECT
    prompt_name = "narrator_schema" if provider_json_schema else "narrator"
    system_path = paths.system_prompt_path(prompt_name)
    if not system_path.exists():
        raise FileNotFoundError(f"System prompt not found: {system_path}")
    system_message = system_path.read_text(encoding="utf-8").strip()

    user_input = state.get("user_input", "").strip()
    if not user_input:
        raise ValueError("user_input is required.")

    game_state_json = state.get("game_state_json", "{}")

    # Build messages: system + compact chat history + current turn.
    history: list[dict] = list(state.get("chat_history") or [])
    prompt_history = _compact_history_for_prompt(history)
    if provider_json_schema:
        prompt_history = _schema_safe_history(prompt_history)

    if provider_json_schema or provider_json_object:
        output_contract = (
            "必须返回 narrative 和 choices 两个字段；"
            "narrative 必须是 80-140 个中文字符的第三人称编年史，"
            "choices 必须恰好四项、非空且互不重复，并依次对应稳妥、机遇、风险、气运。"
            "narrative 和 choices 只能使用中文，不得含任何英文字母、英文缩写或拉丁字母。"
            "发现英文时必须在输出前改写为中文或省略该句。"
            "任何字段都不得包含标签、Markdown 或额外包装。"
        )
    else:
        output_contract = (
            "响应必须以 80-140 个中文字符的第三人称编年史正文开头，第一个字符不得是 <、{、[；随后输出恰好四项的 "
            "<choices>[\"...\", \"...\", \"...\", \"...\"]</choices>；"
            "choices 标签不得省略。叙事正文和四个选项只能使用中文，"
            "不得含任何英文字母、英文缩写或拉丁字母；发现英文时必须改写为中文或省略。"
        )
    user_content = (
        f"<当前状态>\n{game_state_json}\n</当前状态>\n\n"
        f"<玩家行动>\n{user_input}\n</玩家行动>\n\n"
        f"<本回合输出契约>\n{output_contract}\n</本回合输出契约>"
    )

    messages: list[Message] = [Message(role="system", content=system_message)]
    for entry in prompt_history:
        messages.append(Message(
            role=entry.get("role", "user"),
            content=render_history_entry(entry),
        ))
    messages.append(Message(role="user", content=user_content))

    prompt_metrics = _prompt_metrics(
        messages,
        game_state_json=game_state_json,
        history_count=len(history),
        user_input=user_input,
    )

    log.info(
        "[narrator.build_prompt] history=%d user=%d prompt_chars=%d",
        len(history),
        len(user_input),
        prompt_metrics["prompt_chars"],
    )
    return {
        "system_message": system_message,
        "user_message": user_content,
        "messages": messages,
        "prompt_metrics": prompt_metrics,
        "provider_json_schema": provider_json_schema,
        "provider_json_object": provider_json_object,
        "provider_transport": transport.value,
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
        resp, output_text, transport, provider_json_envelope_ok = (
            await _primary_narrator_call(state, messages, stream_callback)
        )
        output_text, repaired_output, repair_elapsed_ms, repair_usage = (
            await _maybe_repair_narrator_output(state, output_text)
        )
        return {
            "output_text": output_text,
            "usage": dict(resp.get("usage") or {}),
            "elapsed_ms": int(resp.get("elapsed_ms", 0)),
            "llm_error": "",
            "repaired_output": repaired_output,
            "repair_elapsed_ms": repair_elapsed_ms,
            "repair_usage": repair_usage,
            "prompt_metrics": state.get("prompt_metrics") or {},
            "provider_json_schema": transport == ProviderTransport.JSON_SCHEMA,
            "provider_json_object": transport == ProviderTransport.JSON_OBJECT,
            "provider_transport": transport.value,
            "provider_json_envelope_ok": provider_json_envelope_ok,
        }
    except LLMError as e:
        log.error("[narrator.call_agnes_llm] failed: %s", e)
        return {"output_text": "", "llm_error": str(e), "elapsed_ms": 0, "usage": {}}


async def _primary_narrator_call(
    state: dict[str, Any],
    messages: list[Message],
    stream_callback: Callable[[str], None] | None,
) -> tuple[dict[str, Any], str, ProviderTransport, bool]:
    transport = narrator_transport(state)
    if transport != ProviderTransport.LEGACY_TAGS:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=runtime_api_key(),
            temperature=0.0,
            max_tokens=1536,
            stream=False,
            response_format=response_format(transport, _NARRATOR_RESPONSE_FORMAT),
        )
    elif stream_callback is not None:
        resp = await call_llm_stream(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=runtime_api_key(),
            temperature=0.0,
            max_tokens=1536,
            on_chunk=stream_callback,
        )
    else:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=runtime_api_key(),
            temperature=0.0,
            max_tokens=1536,
            stream=False,
        )
    output_text = str(resp.get("text") or "")
    if transport == ProviderTransport.LEGACY_TAGS:
        return dict(resp), output_text, transport, False
    unwrapped = _unwrap_narrator_envelope(output_text)
    return dict(resp), unwrapped or output_text, transport, unwrapped is not None


async def _maybe_repair_narrator_output(
    state: dict[str, Any],
    output_text: str,
) -> tuple[str, bool, int, dict[str, Any]]:
    if not state.get("repair_incomplete_output"):
        return output_text, False, 0, {}
    narrative, state_delta, choices = _parse_narrator_output(output_text)
    if not str(output_text or "").strip() or (narrative and len(choices) == 4):
        return output_text, False, 0, {}
    repaired_text, repair_result = await _repair_incomplete_output(
        state, output_text, narrative, state_delta or {}
    )
    repair_elapsed_ms = int(repair_result.get("elapsed_ms") or 0)
    repair_usage = dict(repair_result.get("usage") or {})
    if not repaired_text:
        return output_text, False, repair_elapsed_ms, repair_usage
    repaired_narrative, _repaired_delta, repaired_choices = _parse_narrator_output(repaired_text)
    if repaired_narrative and len(repaired_choices) == 4:
        return repaired_text, True, repair_elapsed_ms, repair_usage
    return output_text, False, repair_elapsed_ms, repair_usage


def save_artifact(state: dict[str, Any]) -> dict[str, Any]:
    """Parse a transport-neutral Narrator envelope and persist safe evidence."""
    run_id = state.get("run_id") or store.new_run_id()
    text = state.get("output_text", "")
    llm_error = state.get("llm_error", "")

    if llm_error:
        narrative: str = ""
        state_delta: dict[str, Any] | None = {}
        choices: list[str] = []
    else:
        narrative, state_delta, choices = _parse_narrator_output(text)
    envelope = NarratorEnvelopeV1.from_values(narrative, choices)
    if envelope is not None:
        narrative = envelope.narrative
        choices = list(envelope.choices)
    contract_diagnostics = _contract_diagnostics(text, narrative, state_delta, choices)

    out_path = store.write_output(AGENT_NAME, run_id, text)
    audit = {
        "run_id": run_id, "agent": AGENT_NAME,
        "started_at": state.get("started_at"), "finished_at": utcnow_iso(),
        "model": state.get("model"), "usage": state.get("usage", {}),
        "elapsed_ms": state.get("elapsed_ms", 0), "llm_error": llm_error,
        "output_path": str(out_path),
        "narrative_chars": len(narrative),
        "prompt_metrics": state.get("prompt_metrics") or {},
        "repaired_output": bool(state.get("repaired_output")),
        "repair_elapsed_ms": int(state.get("repair_elapsed_ms") or 0),
        "contract_diagnostics": contract_diagnostics,
        "provider_json_schema": bool(state.get("provider_json_schema")),
        "provider_json_object": bool(state.get("provider_json_object")),
        "provider_transport": str(state.get("provider_transport") or "legacy_tags"),
        "provider_json_envelope_ok": bool(state.get("provider_json_envelope_ok")),
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
        "repair_elapsed_ms": int(state.get("repair_elapsed_ms") or 0),
        "repair_usage": dict(state.get("repair_usage") or {}),
        "prompt_metrics": state.get("prompt_metrics") or {},
        "contract_diagnostics": contract_diagnostics,
        "provider_json_schema": bool(state.get("provider_json_schema")),
        "provider_json_object": bool(state.get("provider_json_object")),
        "provider_transport": str(state.get("provider_transport") or "legacy_tags"),
        "provider_json_envelope_ok": bool(state.get("provider_json_envelope_ok")),
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


def _compact_history_for_prompt(history: list[dict]) -> list[dict]:
    """Bound the narrator prompt: opening + summary stub + recent turns.

    Storage (``record_turn``) keeps up to 20 entries; the prompt compresses once
    ``chat_history`` exceeds the soft cap so narrator output quality does not
    degrade as the conversation grows. The opening entry (world setup from
    ``record_opening_context``) is preserved, the recent window is kept verbatim
    for continuity, and the collapsed middle is signalled by a stub.
    """
    if len(history) <= _HISTORY_PROMPT_SOFT_CAP:
        return history

    first = history[0]
    recent = history[-_RECENT_HISTORY_MESSAGES:]
    omitted = max(0, len(history) - len(recent) - 1)
    compacted = [
        {
            "role": "assistant",
            "content": (
                "前情摘要：本局开场和角色设定仍以当前状态 JSON 为准；"
                f"中间已有 {omitted} 条历史对话省略。"
            ),
        }
    ]
    if isinstance(first, dict) and first.get("content"):
        compacted.insert(0, {
            "role": first.get("role", "assistant"),
            "content": str(first.get("content", ""))[:1200],
        })
    compacted.extend(recent)
    return compacted


async def _repair_incomplete_output(
    state: dict[str, Any],
    original_text: str,
    narrative: str,
    state_delta: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    """Ask the same model once to reformat partial output into the contract."""
    if not state.get("api_key_set"):
        return None, {}
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
        return None, {}
    repaired_text = str(resp.get("text") or "").strip()
    if not repaired_text:
        return None, dict(resp)
    log.info("[narrator.repair] repaired incomplete output")
    return repaired_text, dict(resp)
