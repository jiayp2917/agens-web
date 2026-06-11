"""SSE parser unit tests."""

from __future__ import annotations

import json

import pytest

from agens_novel.llm.sse import extract_delta_text, iter_sse_events


async def _to_async(it):
    for x in it:
        yield x


@pytest.mark.asyncio
async def test_parses_basic_event() -> None:
    payload = json.dumps({
        "choices": [{"delta": {"content": "你好"}}],
        "model": "agnes-2.0-flash",
    })
    chunks = [f"data: {payload}\n\n".encode("utf-8")]
    events = []
    async for ev in iter_sse_events(_to_async(chunks)):
        events.append(ev)
    assert len(events) == 1
    assert extract_delta_text(events[0]) == "你好"


@pytest.mark.asyncio
async def test_handles_done_sentinel() -> None:
    chunks = [b'data: [DONE]\n\n']
    events = []
    async for ev in iter_sse_events(_to_async(chunks)):
        events.append(ev)
    assert events == []


@pytest.mark.asyncio
async def test_handles_split_chunks() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "X"}}]})
    # Split a single event across two chunks.
    chunks = [b"data: ", payload.encode("utf-8")[:10], payload.encode("utf-8")[10:] + b"\n\n"]
    events = []
    async for ev in iter_sse_events(_to_async(chunks)):
        events.append(ev)
    assert len(events) == 1
    assert extract_delta_text(events[0]) == "X"


@pytest.mark.asyncio
async def test_ignores_malformed_json() -> None:
    chunks = [b"data: {not json}\n\ndata: [DONE]\n\n"]
    events = []
    async for ev in iter_sse_events(_to_async(chunks)):
        events.append(ev)
    assert events == []


@pytest.mark.asyncio
async def test_handles_crlf() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "Y"}}]})
    chunks = [f"data: {payload}\r\n\r\n".encode("utf-8")]
    events = []
    async for ev in iter_sse_events(_to_async(chunks)):
        events.append(ev)
    assert len(events) == 1
    assert extract_delta_text(events[0]) == "Y"
