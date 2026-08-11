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
from collections.abc import Callable
from typing import Any

from ...llm.client import LLMError, call_llm, call_llm_stream
from ...llm.provider_adapter import ProviderTransport, narrator_transport, response_format
from ...llm.runtime_context import runtime_api_key
from ...llm.types import Message
from ...settings import Settings
from ...utils.timing import utcnow_iso
from ..common import load_agent_settings
from ..contracts import NarratorEnvelopeV1
from .parsing import (
    _contract_diagnostics,
    _parse_narrator_output,
    _unwrap_narrator_envelope,
)
from .prompting import (
    _HISTORY_PROMPT_SOFT_CAP as _HISTORY_PROMPT_SOFT_CAP,
)
from .prompting import (
    _RECENT_HISTORY_MESSAGES as _RECENT_HISTORY_MESSAGES,
)
from .prompting import (
    _compact_history_for_prompt as _compact_history_for_prompt,
)
from .prompting import (
    build_prompt as build_prompt,
)

log = logging.getLogger(__name__)

AGENT_NAME = "narrator"
_NO_ASCII_LETTERS_PATTERN = r"^[^A-Za-z]*$"
_NARRATOR_MIN_MAX_TOKENS = 8192
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
            "response_diagnostics": dict(resp.get("response_diagnostics") or {}),
        }
    except LLMError as e:
        log.error("[narrator.call_agnes_llm] failed: %s", e)
        return {
            "output_text": "",
            "llm_error": str(e),
            "llm_error_code": str(getattr(e, "error_code", "llm_error") or "llm_error"),
            "elapsed_ms": int(getattr(e, "elapsed_ms", 0) or 0),
            "usage": dict(getattr(e, "usage", {}) or {}),
            "response_diagnostics": dict(getattr(e, "response_diagnostics", {}) or {}),
        }


async def _primary_narrator_call(
    state: dict[str, Any],
    messages: list[Message],
    stream_callback: Callable[[str], None] | None,
) -> tuple[dict[str, Any], str, ProviderTransport, bool]:
    transport = narrator_transport(state)
    max_tokens = _narrator_max_tokens()
    if transport != ProviderTransport.LEGACY_TAGS:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=runtime_api_key(),
            temperature=0.0,
            max_tokens=max_tokens,
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
            max_tokens=max_tokens,
            on_chunk=stream_callback,
        )
    else:
        resp = await call_llm(
            messages,
            model=state.get("model"),
            base_url=state.get("base_url"),
            api_key=runtime_api_key(),
            temperature=0.0,
            max_tokens=max_tokens,
            stream=False,
        )
    output_text = str(resp.get("text") or "")
    if transport == ProviderTransport.LEGACY_TAGS:
        return dict(resp), output_text, transport, False
    unwrapped = _unwrap_narrator_envelope(output_text)
    return dict(resp), unwrapped or output_text, transport, unwrapped is not None


def _narrator_max_tokens() -> int:
    """Reserve enough completion budget for visible structured narration."""
    return max(_NARRATOR_MIN_MAX_TOKENS, Settings().max_tokens)


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
    """Parse a transport-neutral Narrator envelope without persisting provider output."""
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
        "provider_transport": str(state.get("provider_transport") or "json_object"),
        "provider_json_envelope_ok": bool(state.get("provider_json_envelope_ok")),
        "output_path": "",
        "audit_path": "",
        "finished_at": utcnow_iso(),
        "llm_error_code": str(state.get("llm_error_code") or ""),
        "response_diagnostics": dict(state.get("response_diagnostics") or {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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
