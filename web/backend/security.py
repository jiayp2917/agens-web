"""Request protection helpers for the FastAPI app."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int = 64 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        header_error = _content_length_error(scope, self.max_bytes)
        if header_error is not None:
            await header_error(scope, receive, send)
            return
        body, valid_request = await _read_limited_body(receive, self.max_bytes)
        if not valid_request:
            await self.app(scope, receive, send)
            return
        if body is None:
            response = JSONResponse({"detail": "请求内容过大。"}, status_code=413)
            await response(scope, receive, send)
            return

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


def _content_length_error(scope, max_bytes: int) -> JSONResponse | None:
    headers = {key.lower(): value for key, value in scope.get("headers") or []}
    content_length = headers.get(b"content-length")
    if not content_length:
        return None
    try:
        too_large = int(content_length.decode("ascii")) > max_bytes
    except (UnicodeDecodeError, ValueError):
        return JSONResponse({"detail": "请求头无效。"}, status_code=400)
    return JSONResponse({"detail": "请求内容过大。"}, status_code=413) if too_large else None


async def _read_limited_body(receive, max_bytes: int) -> tuple[bytes | None, bool]:
    body = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            return bytes(body), False
        body.extend(message.get("body", b""))
        if len(body) > max_bytes:
            return None, True
        if not message.get("more_body", False):
            return bytes(body), True


class RateLimiter:
    """Small in-process sliding-window limiter for alpha deployment."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.time()
        bucket = self._buckets[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试。")
        bucket.append(now)


def client_key(request: Request, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    if os.environ.get("TRUST_PROXY_HEADERS", "").strip().lower() in ("1", "true", "yes"):
        forwarded = request.headers.get("x-forwarded-for", "")
        host = forwarded.split(",", 1)[0].strip() or host
    return f"{action}:{host}"


def enforce_same_origin(request: Request) -> None:
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return

    allowed = _allowed_origins(request)
    if not allowed:
        return

    origin = request.headers.get("origin", "").strip()
    if origin:
        if _normalize_origin(origin) not in allowed:
            raise HTTPException(status_code=403, detail="请求来源不被允许。")
        return

    referer = request.headers.get("referer", "").strip()
    if referer and _normalize_origin(referer) in allowed:
        return
    raise HTTPException(status_code=403, detail="请求来源不被允许。")


def _allowed_origins(request: Request) -> set[str]:
    configured = {
        _normalize_origin(item)
        for item in os.environ.get("AGENS_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    }
    if configured:
        return configured
    if is_production_mode():
        host = request.headers.get("host", "").strip()
        if host:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0]
            return {_normalize_origin(f"{scheme}://{host}")}
    return set()


def is_production_mode() -> bool:
    # After the Option C consolidation PostgreSQL is the only backend, so the
    # ``DATABASE_BACKEND`` env var is no longer a production signal — it was
    # always "postgresql" in every environment. Production is now indicated
    # solely by ``AGENS_ENV`` (set to ``production`` in deploy/production.env).
    env = os.environ.get("AGENS_ENV", "").strip().lower()
    return env in ("prod", "production")


def _normalize_origin(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip().rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
