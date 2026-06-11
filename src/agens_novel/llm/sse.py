"""SSE (Server-Sent Events) parser.

Mirrors the line-splitting logic in ``D:/2917/agens/test-agnes.mjs`` (the
Node.js harness that this project draws from). The contract:

  - Input: an async iterable of byte chunks.
  - Output: a single accumulated string of ``text`` content (the model's
    answer), ignoring ``[DONE]`` sentinels and non-content fields.

Only ``choices[0].delta.content`` is consumed. Other fields (role,
finish_reason) are dropped after recording the finish.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)

_DONE = "[DONE]"


def _decode(chunk: bytes | str) -> str:
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8", errors="replace")
    return chunk


async def iter_sse_events(
    chunks: AsyncIterator[bytes],
) -> AsyncIterator[dict[str, Any]]:
    """Yield each parsed JSON event from an SSE byte stream.

    Handles:
      * CRLF or LF line endings.
      * Lines starting with ``data:`` (with optional leading space).
      * ``[DONE]`` sentinels (terminates silently).
      * Blank-line event separators.
    """
    buffer = ""
    async for raw in chunks:
        buffer += _decode(raw)
        # Process line-by-line; keep partial last line in buffer.
        *lines, buffer = buffer.split("\n")
        for line in lines:
            for event in _parse_one_line(line):
                yield event

    # Flush the trailing buffer (if any) on stream end.
    for event in _parse_one_line(buffer):
        yield event


def _parse_one_line(line: str) -> list[dict[str, Any]]:
    line = line.rstrip("\r").strip()
    if not line:
        return []
    if not line.startswith("data:"):
        return []
    payload = line[len("data:"):].strip()
    if payload == _DONE:
        return []
    try:
        return [json.loads(payload)]
    except json.JSONDecodeError as e:
        log.debug("SSE parse error (ignored): %s | payload=%r", e, payload[:200])
        return []


def extract_delta_text(event: dict[str, Any]) -> str:
    """Pull text from a delta event, compatible with OpenAI / Agnes shapes."""
    try:
        first = event["choices"][0]
    except (KeyError, IndexError, TypeError):
        return ""

    # Streamed: choices[0].delta.content
    delta = first.get("delta")
    if isinstance(delta, dict) and "content" in delta:
        content = delta["content"]
        return content if isinstance(content, str) else ""

    # Non-streamed (rare in SSE): choices[0].message.content
    msg = first.get("message")
    if isinstance(msg, dict) and "content" in msg:
        content = msg["content"]
        return content if isinstance(content, str) else ""

    # Some providers: choices[0].text
    if "text" in first:
        text = first["text"]
        return text if isinstance(text, str) else ""

    return ""
