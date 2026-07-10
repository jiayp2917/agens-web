from __future__ import annotations

import socket

import pytest

from agens_novel.llm.url_security import (
    UnsafeModelBaseUrl,
    validate_model_base_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com/v1",
        "https://user:pass@api.deepseek.com/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://api.deepseek.com/v1?target=internal",
        "https://api.deepseek.com/v1#fragment",
        "https://unapproved.example/v1",
    ],
)
def test_model_base_url_rejects_unsafe_authorities(url: str) -> None:
    with pytest.raises(UnsafeModelBaseUrl):
        validate_model_base_url(url)


def test_model_base_url_accepts_official_and_configured_hosts(monkeypatch) -> None:
    monkeypatch.setenv(
        "AGENS_MODEL_BASE_URL_ALLOWLIST",
        "models.example.com,custom.example.com:8443",
    )

    assert validate_model_base_url("https://api.deepseek.com/v1/") == (
        "https://api.deepseek.com/v1"
    )
    assert validate_model_base_url("https://models.example.com/openai/v1") == (
        "https://models.example.com/openai/v1"
    )
    assert validate_model_base_url("https://custom.example.com:8443/v1") == (
        "https://custom.example.com:8443/v1"
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_model_base_url_rejects_non_public_dns(monkeypatch, address: str) -> None:
    monkeypatch.setenv("AGENS_MODEL_BASE_URL_ALLOWLIST", "models.example.com")
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_STREAM, 6, "", (address, 443))],
    )

    with pytest.raises(UnsafeModelBaseUrl, match="非公网"):
        validate_model_base_url("https://models.example.com/v1", resolve_dns=True)


def test_model_base_url_accepts_only_when_all_dns_answers_are_public(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_MODEL_BASE_URL_ALLOWLIST", "models.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443)),
        ],
    )

    with pytest.raises(UnsafeModelBaseUrl, match="非公网"):
        validate_model_base_url("https://models.example.com/v1", resolve_dns=True)


def test_model_base_url_accepts_public_dns(monkeypatch) -> None:
    monkeypatch.setenv("AGENS_MODEL_BASE_URL_ALLOWLIST", "models.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 443, 0, 0)),
        ],
    )

    assert validate_model_base_url(
        "https://models.example.com/v1",
        resolve_dns=True,
    ) == "https://models.example.com/v1"
