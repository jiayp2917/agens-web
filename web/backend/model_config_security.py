"""Encryption helpers for stored model API keys.

The database stores only Fernet tokens and masked metadata. The raw key is
available only inside the current request/runtime path after decryption.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "fernet:"


class ModelConfigSecretError(RuntimeError):
    """Raised when stored model secrets cannot be safely decrypted."""


def mask_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return "<unset>"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _fernet_from_secret(secret: str | None = None) -> Fernet:
    raw_secret = (secret if secret is not None else os.environ.get("MODEL_CONFIG_SECRET", "")).strip()
    if not raw_secret:
        raise ModelConfigSecretError("MODEL_CONFIG_SECRET is required for stored model keys.")
    digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""
    token = _fernet_from_secret().encrypt(key.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_api_key(encrypted: str) -> str:
    value = (encrypted or "").strip()
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        raise ModelConfigSecretError("Stored model key is not encrypted.")
    token = value[len(_PREFIX):].encode("ascii")
    try:
        return _fernet_from_secret().decrypt(token).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise ModelConfigSecretError("Stored model key could not be decrypted.") from exc