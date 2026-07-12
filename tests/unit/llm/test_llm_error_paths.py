"""专项验证：模型调用 408/429/5xx、整体超时与取消传播。

本模块锁定 ``src/agens_novel/llm`` 的错误分类与传播契约，对应
``docs/plan.md`` 未完成里程碑「将同一 provider/network 下的 choice 延迟与
408/429/5xx、超时和取消专项验证」。覆盖三层：

1. HTTP 状态分类（``_handle_non_stream_response`` / ``_handle_stream_response``）：
   401/403 → ``LLMAuthError``；3xx → 重定向拒绝；408/425/429/500/502/503/504 →
   交由 ``raise_for_status`` 触发可重试 ``HTTPStatusError``；其余 ≥400 → ``LLMBadRequest``。
2. ``_execute_with_retry`` 传播：整体超时 → ``LLMError("total timeout exceeded")``；
   ``RetryExhausted`` → ``LLMError("upstream transport unavailable")``；
   可重试 ``HTTPStatusError`` 重试耗尽 → ``LLMError("upstream HTTP <code>")``；
   外部 ``CancelledError`` 不被吞没，继续向上传播。
3. ``is_retryable_model_request_failure``（引擎层「是否值得再 live 重试一次」分类器）：
   暂态标志为可重试；鉴权/缺 key/空值/非 dict 为不可重试。

只新增测试，不改产品代码。如某测试揭示的是 bug 而非既有行为，应在评审中单独提出，
不在本测试批次内顺手修改。
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from agens_novel.engine.model_result import is_retryable_model_request_failure
from agens_novel.llm.client import (
    LLMAuthError,
    LLMBadRequest,
    LLMError,
    _execute_with_retry,
    _handle_non_stream_response,
    _handle_stream_response,
)
from agens_novel.llm.retry import RETRYABLE_HTTP_STATUSES

_COMPLETIONS_URL = "https://apihub.agnes-ai.com/v1/chat/completions"


def _request() -> httpx.Request:
    return httpx.Request("POST", _COMPLETIONS_URL)


def _response(status_code: int, *, text: str = "error body") -> httpx.Response:
    return httpx.Response(status_code, text=text, request=_request())


# ---------------------------------------------------------------------------
# 1. 非流式状态分类
# ---------------------------------------------------------------------------


class TestNonStreamStatusClassification:
    """``_handle_non_stream_response`` 必须按状态码分流到正确的异常/返回。"""

    @pytest.mark.parametrize("status_code", sorted(RETRYABLE_HTTP_STATUSES))
    def test_retryable_status_raises_http_status_error(self, status_code: int) -> None:
        # 408/425/429/500/502/503/504 不能被折叠成 LLMBadRequest；交给 raise_for_status
        # 触发 HTTPStatusError，供上层重试。
        with pytest.raises(httpx.HTTPStatusError):
            _handle_non_stream_response(_response(status_code), time.monotonic())

    @pytest.mark.parametrize("status_code", (401, 403))
    def test_auth_status_raises_auth_error(self, status_code: int) -> None:
        with pytest.raises(LLMAuthError, match=str(status_code)):
            _handle_non_stream_response(_response(status_code), time.monotonic())

    @pytest.mark.parametrize("status_code", (400, 404, 422))
    def test_non_retryable_4xx_raises_bad_request(self, status_code: int) -> None:
        with pytest.raises(LLMBadRequest, match=str(status_code)):
            _handle_non_stream_response(_response(status_code), time.monotonic())

    def test_redirect_refused_without_following_location(self) -> None:
        response = httpx.Response(
            307,
            headers={"location": "http://127.0.0.1/internal"},
            json={"choices": [{"message": {"content": "must not be accepted"}}]},
            request=_request(),
        )
        with pytest.raises(LLMBadRequest, match="redirect refused"):
            _handle_non_stream_response(response, time.monotonic())

    def test_ok_returns_parsed_response(self) -> None:
        response = httpx.Response(
            200,
            json={
                "model": "agnes-2.0-flash",
                "choices": [{"message": {"content": "叙事"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
            request=_request(),
        )
        parsed = _handle_non_stream_response(response, time.monotonic())
        assert parsed["text"] == "叙事"
        assert parsed["elapsed_ms"] >= 0
        assert parsed["usage"]["total_tokens"] == 5


# ---------------------------------------------------------------------------
# 2. 流式状态分类（与非流式一致的错误分流）
# ---------------------------------------------------------------------------


class TestStreamStatusClassification:
    """``_handle_stream_response`` 在消费字节前必须先按状态码分流。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", (401, 403))
    async def test_auth_status_raises_auth_error(self, status_code: int) -> None:
        with pytest.raises(LLMAuthError, match=str(status_code)):
            await _handle_stream_response(_response(status_code), "m", time.monotonic())

    @pytest.mark.asyncio
    async def test_redirect_refused(self) -> None:
        response = httpx.Response(
            307,
            headers={"location": "http://127.0.0.1/internal"},
            request=_request(),
        )
        with pytest.raises(LLMBadRequest, match="redirect refused"):
            await _handle_stream_response(response, "m", time.monotonic())

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", sorted(RETRYABLE_HTTP_STATUSES))
    async def test_retryable_status_raises_http_status_error(self, status_code: int) -> None:
        with pytest.raises(httpx.HTTPStatusError):
            await _handle_stream_response(_response(status_code), "m", time.monotonic())


# ---------------------------------------------------------------------------
# 3. _execute_with_retry 传播（超时 / 重试耗尽 / 取消）
# ---------------------------------------------------------------------------


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    response = _response(status_code)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=response.request, response=response
    )


class TestExecuteWithRetryPropagation:
    @pytest.mark.asyncio
    async def test_total_timeout_exceeds(self) -> None:
        async def never_finishes() -> httpx.Response:
            await asyncio.sleep(5)
            raise AssertionError("unreachable")

        with pytest.raises(LLMError, match="total timeout exceeded"):
            await _execute_with_retry(
                never_finishes,
                max_retries=0,
                total_timeout_seconds=0.01,
                label="test_call",
            )

    @pytest.mark.asyncio
    async def test_transport_error_exhausts_to_unavailable(self) -> None:
        async def transport_fails() -> httpx.Response:
            raise httpx.TransportError("connection reset", request=_request())

        with pytest.raises(LLMError, match="upstream transport unavailable"):
            await _execute_with_retry(
                transport_fails,
                max_retries=0,
                total_timeout_seconds=5,
                label="test_call",
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", (429, 500, 503))
    async def test_retryable_http_status_exhausts_to_upstream_http(
        self, status_code: int
    ) -> None:
        async def fails_with_status() -> httpx.Response:
            raise _status_error(status_code)

        with pytest.raises(LLMError, match=f"upstream HTTP {status_code}"):
            await _execute_with_retry(
                fails_with_status,
                max_retries=0,
                total_timeout_seconds=5,
                label="test_call",
            )

    @pytest.mark.asyncio
    async def test_external_cancellation_propagates(self) -> None:
        started = asyncio.Event()

        async def slow() -> httpx.Response:
            started.set()
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

        task = asyncio.create_task(
            _execute_with_retry(
                slow,
                max_retries=0,
                total_timeout_seconds=30,
                label="test_call",
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# 4. is_retryable_model_request_failure 分类器（此前零覆盖）
# ---------------------------------------------------------------------------


class TestIsRetryableModelRequestFailure:
    """引擎层判定「这一次 provider 失败是否值得再 live 重试一次」。"""

    @pytest.mark.parametrize(
        "error_message",
        [
            # 真实 client 产出的可重试消息
            "llm_call: total timeout exceeded",
            "llm_call: upstream HTTP 408",
            "llm_call: upstream HTTP 425",
            "llm_call: upstream HTTP 429",
            "llm_call: upstream HTTP 500",
            "llm_call: upstream HTTP 502",
            "llm_call: upstream HTTP 503",
            "llm_call: upstream HTTP 504",
            # 其他暂态特征
            "read timed out",
            "connection reset by peer",
            "service temporarily unavailable",
            "upstream_error: bad gateway",
            "notfounderror: dns",
        ],
    )
    def test_transient_is_retryable(self, error_message: str) -> None:
        assert is_retryable_model_request_failure({"llm_error": error_message}) is True

    @pytest.mark.parametrize(
        "error_message",
        [
            # 真实 client 产出的鉴权失败
            "HTTP 401: invalid api key",
            "HTTP 403: forbidden",
            "missing api_key",
            "missing key in request",
        ],
    )
    def test_auth_or_missing_key_not_retryable(self, error_message: str) -> None:
        assert is_retryable_model_request_failure({"llm_error": error_message}) is False

    def test_empty_and_non_dict_not_retryable(self) -> None:
        assert is_retryable_model_request_failure({}) is False
        assert is_retryable_model_request_failure({"llm_error": ""}) is False
        assert is_retryable_model_request_failure(None) is False  # type: ignore[arg-type]
        assert is_retryable_model_request_failure("not a dict") is False  # type: ignore[arg-type]

    def test_transport_unavailable_message_is_not_retryable(self) -> None:
        # 记录当前行为：RetryExhausted 被转成 "upstream transport unavailable"，
        # 该串不含暂态关键字，因此分类为「不再 live 重试」。这是既有行为，非本批次改动；
        # 评审可讨论是否应保留传输层细节以供上层判定，但属产品/重试策略决策。
        assert (
            is_retryable_model_request_failure(
                {"llm_error": "llm_call: upstream transport unavailable"}
            )
            is False
        )
