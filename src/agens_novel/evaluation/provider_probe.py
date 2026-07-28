"""Safe, local-only capability probes for OpenAI-compatible providers."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from ..agents.contracts import (
    JudgeDecisionV1,
    NarratorEnvelopeV1,
    WorldOpeningEnvelopeV1,
)
from ..artifacts import store
from ..llm.client import LLMError, call_llm, call_llm_stream
from ..llm.provider_adapter import ProviderTransport, response_format
from ..llm.runtime_context import model_runtime
from ..llm.types import LLMResponse, Message
from .ledger import EvaluationLedger
from .model_config import EvaluationModelConfig

ProbeCall = Callable[..., Awaitable[LLMResponse]]
_PLAIN_JSON_TRANSPORT = "plain_json"
_STREAM_TRANSPORT = "stream"


@dataclass(frozen=True)
class ProbeResult:
    """One non-secret provider capability observation."""

    name: str
    supported: bool
    strict: bool
    transport: str
    elapsed_ms: int
    ttft_ms: int | None
    usage: dict[str, int]
    error_type: str = ""
    response: str = ""


def probe_provider_sync(config: EvaluationModelConfig) -> dict[str, Any]:
    """Run all capability probes from a dedicated local evaluation process."""
    return asyncio.run(probe_provider(config))


async def probe_provider(
    config: EvaluationModelConfig,
    *,
    request: ProbeCall = call_llm,
    stream_request: ProbeCall = call_llm_stream,
    ledger: EvaluationLedger | None = None,
) -> dict[str, Any]:
    """Probe wire features and all three canonical Agent envelopes.

    The caller must run in evaluation mode. Prompts are held only in memory;
    persisted records contain the redacted response copy and safe metrics.
    """
    runtime = config.runtime_config()
    with model_runtime(runtime):
        transport_results = [
            await _probe_plain_json(config, request, ledger),
            await _probe_json_object(config, request, ledger),
            await _probe_json_schema(config, request, ledger),
            await _probe_stream(config, stream_request, ledger),
        ]
        selected = _selected_transport(transport_results)
        agent_results = [
            await _probe_contract(config, request, "world_opening", selected, ledger),
            await _probe_contract(config, request, "narrator", selected, ledger),
            await _probe_contract(config, request, "judge", selected, ledger),
        ]

    report = {
        "provider": runtime.provider,
        "model": runtime.model,
        "recommended_transport": selected.value,
        "probes": [asdict(item) for item in (*transport_results, *agent_results)],
        "ledger": ledger.summary() if ledger is not None else None,
    }
    run_id = store.new_run_id()
    store.write_audit("provider_probe", run_id, report)
    store.append_global_log(
        {
            "event": "provider_probe",
            "run_id": run_id,
            "provider": runtime.provider,
            "model": runtime.model,
            "recommended_transport": selected.value,
            "strict_count": sum(1 for item in (*transport_results, *agent_results) if item.strict),
            "probe_count": len(transport_results) + len(agent_results),
        }
    )
    return report


async def _probe_plain_json(
    config: EvaluationModelConfig, request: ProbeCall, ledger: EvaluationLedger | None
) -> ProbeResult:
    return await _request_probe(
        name="plain_json",
        config=config,
        request=request,
        messages=[
            {
                "role": "user",
                "content": '仅返回 JSON 对象：{"ok":true,"text":"中文"}。',
            }
        ],
        transport=None,
        validator=lambda text: isinstance(_json_object(text), dict),
        ledger=ledger,
    )


async def _probe_json_object(
    config: EvaluationModelConfig, request: ProbeCall, ledger: EvaluationLedger | None
) -> ProbeResult:
    return await _request_probe(
        name="json_object",
        config=config,
        request=request,
        messages=[
            {
                "role": "user",
                "content": '只返回一个 JSON 对象，包含 ok=true 和中文 text。',
            }
        ],
        transport=ProviderTransport.JSON_OBJECT,
        validator=lambda text: isinstance(_json_object(text), dict),
        ledger=ledger,
    )


async def _probe_json_schema(
    config: EvaluationModelConfig, request: ProbeCall, ledger: EvaluationLedger | None
) -> ProbeResult:
    return await _request_probe(
        name="json_schema",
        config=config,
        request=request,
        messages=[{"role": "user", "content": "返回中文确认。"}],
        transport=ProviderTransport.JSON_SCHEMA,
        validator=lambda text: isinstance(_json_object(text), dict),
        ledger=ledger,
    )


async def _probe_stream(
    config: EvaluationModelConfig, request: ProbeCall, ledger: EvaluationLedger | None
) -> ProbeResult:
    first_chunk_at: float | None = None
    started = time.monotonic()

    def on_chunk(_chunk: str) -> None:
        nonlocal first_chunk_at
        if first_chunk_at is None:
            first_chunk_at = time.monotonic()

    request_id = ledger.reserve("provider_probe") if ledger is not None else ""
    try:
        response = await request(
            [{"role": "user", "content": "请只用一句中文回应。"}],
            model=config.model,
            base_url=config.base_url,
            api_key=config.runtime_config().api_key,
            max_tokens=64,
            max_retries=0,
            on_chunk=on_chunk,
        )
    except (LLMError, OSError, ValueError) as exc:
        result = _failure("stream", _STREAM_TRANSPORT, exc)
        _record_probe(ledger, request_id, result)
        return result
    text = str(response.get("text") or "")
    result = ProbeResult(
        name="stream",
        supported=bool(text),
        strict=bool(text),
        transport=_STREAM_TRANSPORT,
        elapsed_ms=int(response.get("elapsed_ms") or 0),
        ttft_ms=int((first_chunk_at - started) * 1000) if first_chunk_at is not None else None,
        usage=_usage(response),
        response=text,
    )
    _record_probe(ledger, request_id, result)
    return result


async def _probe_contract(
    config: EvaluationModelConfig,
    request: ProbeCall,
    name: str,
    transport: ProviderTransport,
    ledger: EvaluationLedger | None,
) -> ProbeResult:
    payload = _contract_payload(name)
    prompt, validator = _contract_prompt_and_validator(name, payload, transport)
    result = await _request_probe(
        name=name,
        config=config,
        request=request,
        messages=[{"role": "user", "content": prompt}],
        transport=transport,
        validator=validator,
        ledger=ledger,
    )
    return result


async def _request_probe(
    *,
    name: str,
    config: EvaluationModelConfig,
    request: ProbeCall,
    messages: list[Message],
    transport: ProviderTransport | None,
    validator: Callable[[str], bool],
    ledger: EvaluationLedger | None,
) -> ProbeResult:
    request_id = ledger.reserve("provider_probe") if ledger is not None else ""
    try:
        request_kwargs: dict[str, Any] = {
            "model": config.model,
            "base_url": config.base_url,
            "api_key": config.runtime_config().api_key,
            "max_tokens": 256,
            "stream": False,
            "max_retries": 0,
        }
        if transport is not None:
            request_kwargs["response_format"] = response_format(transport, _probe_schema(name))
        response = await request(messages, **request_kwargs)
    except (LLMError, OSError, ValueError) as exc:
        result = _failure(name, transport, exc)
        _record_probe(ledger, request_id, result)
        return result
    text = str(response.get("text") or "")
    strict = validator(text)
    result = ProbeResult(
        name=name,
        supported=bool(text),
        strict=strict,
        transport=_transport_label(transport),
        elapsed_ms=int(response.get("elapsed_ms") or 0),
        ttft_ms=None,
        usage=_usage(response),
        response=text,
    )
    _record_probe(ledger, request_id, result)
    return result


def _selected_transport(results: list[ProbeResult]) -> ProviderTransport:
    by_name = {result.name: result for result in results}
    if by_name["json_schema"].strict:
        return ProviderTransport.JSON_SCHEMA
    if by_name["json_object"].strict:
        return ProviderTransport.JSON_OBJECT
    # Do not issue a new tag-formatted request when both structured transports
    # fail. The JSON object result remains the explicit failed recommendation.
    return ProviderTransport.JSON_OBJECT


def _contract_payload(name: str) -> dict[str, Any]:
    if name == "world_opening":
        return {
            "opening_narrative": "十六岁时，潮声已近。",
            "chronicle_0_16": ["幼年听潮。"],
            "initial_situation_16": "渡口试炼将开。",
            "choices": ["A 稳步探查", "B 结交舟客", "C 闯入暗礁", "D 借潮而行"],
        }
    if name == "narrator":
        return {
            "narrative": "潮雾散开，前路初现。",
            "choices": ["A 稳步探查", "B 结交舟客", "C 闯入暗礁", "D 借潮而行"],
        }
    return {"approved": True, "issue_codes": [], "rewrite_required": False}


def _contract_prompt_and_validator(
    name: str,
    payload: dict[str, Any],
    transport: ProviderTransport,
) -> tuple[str, Callable[[str], bool]]:
    expected = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        f"仅返回该 JSON 对象，不添加解释：{expected}",
        lambda text: _validate_contract(name, _json_object(text)),
    )


def _validate_contract(name: str, payload: Any) -> bool:
    if name == "world_opening":
        return WorldOpeningEnvelopeV1.from_payload(payload) is not None
    if name == "narrator":
        data = payload if isinstance(payload, dict) else {}
        return NarratorEnvelopeV1.from_values(data.get("narrative"), data.get("choices")) is not None
    decision = JudgeDecisionV1.from_payload(payload)
    return decision.approved and not decision.rewrite_required


def _probe_schema(name: str) -> dict[str, Any]:
    schemas = {
        "plain_json": {"type": "object", "additionalProperties": True},
        "json_object": {"type": "object", "additionalProperties": True},
        "json_schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}, "text": {"type": "string"}},
            "required": ["ok", "text"],
            "additionalProperties": False,
        },
        "world_opening": {
            "type": "object",
            "properties": {
                "opening_narrative": {"type": "string"},
                "chronicle_0_16": {"type": "array", "items": {"type": "string"}},
                "initial_situation_16": {"type": "string"},
                "choices": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["opening_narrative", "chronicle_0_16", "initial_situation_16", "choices"],
            "additionalProperties": False,
        },
        "narrator": {
            "type": "object",
            "properties": {
                "narrative": {"type": "string"},
                "choices": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["narrative", "choices"],
            "additionalProperties": False,
        },
        "judge": {
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "issue_codes": {"type": "array", "items": {"type": "string"}},
                "rewrite_required": {"type": "boolean"},
            },
            "required": ["approved", "issue_codes", "rewrite_required"],
            "additionalProperties": False,
        },
    }
    return {"type": "json_schema", "json_schema": {"name": f"probe_{name}", "strict": True, "schema": schemas[name]}}


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _transport_label(transport: ProviderTransport | None) -> str:
    return transport.value if transport is not None else _PLAIN_JSON_TRANSPORT


def _usage(response: LLMResponse) -> dict[str, int]:
    usage = response.get("usage") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _failure(name: str, transport: ProviderTransport | str | None, error: Exception) -> ProbeResult:
    return ProbeResult(
        name=name,
        supported=False,
        strict=False,
        transport=transport if isinstance(transport, str) else _transport_label(transport),
        elapsed_ms=0,
        ttft_ms=None,
        usage={},
        error_type=type(error).__name__,
    )


def _record_probe(
    ledger: EvaluationLedger | None,
    request_id: str,
    result: ProbeResult,
) -> None:
    if ledger is None:
        return
    ledger.record(
        request_id=request_id,
        agent="provider_probe",
        transport=result.transport,
        elapsed_ms=result.elapsed_ms,
        ttft_ms=result.ttft_ms,
        usage=result.usage,
        strict=result.strict,
        success=result.supported,
    )
