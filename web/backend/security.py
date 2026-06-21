"""Request protection helpers for the FastAPI app."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import Response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = 64 * 1024) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse({"detail": "请求内容过大。"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "请求头无效。"}, status_code=400)
        return await call_next(request)


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
    forwarded = request.headers.get("x-forwarded-for", "")
    host = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
    return f"{action}:{host}"
