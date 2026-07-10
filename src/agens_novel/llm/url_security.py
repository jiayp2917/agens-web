"""Validation for server-side model endpoints.

User model settings influence outbound server requests, so the accepted URL
surface is deliberately smaller than a general-purpose HTTP client.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlsplit, urlunsplit

OFFICIAL_MODEL_HOSTS = frozenset(
    {
        "apihub.agnes-ai.com",
        "api.deepseek.com",
        "dashscope.aliyuncs.com",
        "open.bigmodel.cn",
    }
)


class UnsafeModelBaseUrl(ValueError):
    """Raised when a model endpoint is not safe for server-side access."""


def validate_model_base_url(raw_url: str, *, resolve_dns: bool = False) -> str:
    """Return a normalized, allowlisted HTTPS model base URL.

    DNS is resolved immediately before an outbound request. Saving settings
    still performs the deterministic scheme/authority/allowlist checks.
    """

    value = str(raw_url or "").strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeModelBaseUrl("模型 Base URL 格式无效。") from exc

    if parsed.scheme.lower() != "https":
        raise UnsafeModelBaseUrl("模型 Base URL 只允许 HTTPS。")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeModelBaseUrl("模型 Base URL 不允许凭据或空主机名。")
    if parsed.query or parsed.fragment:
        raise UnsafeModelBaseUrl("模型 Base URL 不允许查询参数或片段。")

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise UnsafeModelBaseUrl("模型 Base URL 不允许直接使用 IP 地址。")

    effective_port = port or 443
    if not _host_is_allowed(hostname, effective_port, explicit_port=port is not None):
        raise UnsafeModelBaseUrl("模型 Base URL 不在服务器允许列表中。")

    if resolve_dns:
        _assert_public_dns(hostname, effective_port)

    netloc = hostname if effective_port == 443 else f"{hostname}:{effective_port}"
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


async def validate_model_base_url_for_request(raw_url: str) -> str:
    """Run the network lookup off the event loop immediately before a call."""

    return await asyncio.to_thread(validate_model_base_url, raw_url, resolve_dns=True)


def _host_is_allowed(hostname: str, port: int, *, explicit_port: bool) -> bool:
    if hostname in OFFICIAL_MODEL_HOSTS and port == 443:
        return True

    allowed = _configured_hosts()
    authority = f"{hostname}:{port}"
    if authority in allowed:
        return True
    return not explicit_port and port == 443 and hostname in allowed


def _configured_hosts() -> set[str]:
    values: set[str] = set()
    for raw in os.environ.get("AGENS_MODEL_BASE_URL_ALLOWLIST", "").split(","):
        item = raw.strip().lower().rstrip(".")
        if not item:
            continue
        if "://" in item or "/" in item or "@" in item:
            continue
        values.add(item)
    return values


def _assert_public_dns(hostname: str, port: int) -> None:
    try:
        answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeModelBaseUrl("模型 Base URL 无法解析。") from exc

    addresses = {str(answer[4][0]).split("%", 1)[0] for answer in answers if answer[4]}
    if not addresses:
        raise UnsafeModelBaseUrl("模型 Base URL 无法解析。")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeModelBaseUrl("模型 Base URL 解析结果无效。") from exc
        if not parsed.is_global:
            raise UnsafeModelBaseUrl("模型 Base URL 解析到了非公网地址。")
