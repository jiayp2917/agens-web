"""Request body limit and ASGI body replay coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from web.backend.app import create_app

pytestmark = pytest.mark.xdist_group("pg_test_db")


def test_body_size_limit_rejects_actual_large_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    monkeypatch.setenv("AGENS_MAX_REQUEST_BYTES", "128")
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/auth/login",
        content=b'{"username":"' + (b"x" * 256) + b'","password":"password-123"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413

@pytest.mark.anyio("asyncio")
async def test_body_size_limit_rejects_chunked_body_without_content_length() -> None:
    from web.backend.security import BodySizeLimitMiddleware

    async def inner_app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodySizeLimitMiddleware(inner_app, max_bytes=8)
    scope = {"type": "http", "headers": []}
    messages = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413

@pytest.mark.anyio("asyncio")
async def test_body_size_limit_replays_allowed_chunked_body() -> None:
    from web.backend.security import BodySizeLimitMiddleware

    seen_body = b""

    async def inner_app(_scope, receive, send):
        nonlocal seen_body
        message = await receive()
        seen_body = message["body"]
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodySizeLimitMiddleware(inner_app, max_bytes=16)
    scope = {"type": "http", "headers": []}
    messages = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"678", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)

    assert seen_body == b"12345678"
    assert sent[0]["status"] == 204
