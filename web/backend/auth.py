"""Invite-only authentication helpers for the web backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
except Exception:  # pragma: no cover - exercised only when optional dependency is absent
    PasswordHasher = None  # type: ignore[assignment]

    class VerifyMismatchError(Exception):
        pass

from .database_common import public_user

SESSION_COOKIE_NAME = "agens_session"
GUEST_COOKIE_NAME = "agens_guest"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
DEV_SESSION_SECRET = "dev-session-secret-change-me"
_PASSWORD_HASHER = PasswordHasher() if PasswordHasher is not None else None


@dataclass(frozen=True)
class SessionClaims:
    user_id: str
    issued_at: int


def hash_password(password: str) -> str:
    if _PASSWORD_HASHER is not None:
        return _PASSWORD_HASHER.hash(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _algo, salt, expected = password_hash.split("$", 2)
        except ValueError:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000)
        return hmac.compare_digest(digest.hex(), expected)
    if _PASSWORD_HASHER is None:
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_invite_code(code: str) -> str:
    normalized = code.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def create_session_token(user_id: str, secret: str | None = None) -> str:
    issued_at = str(int(time.time()))
    payload = f"{user_id}.{issued_at}"
    sig = _sign(payload, secret)
    raw = f"{payload}.{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def parse_session_token(token: str, secret: str | None = None) -> SessionClaims | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        user_id, issued_at_raw, sig = raw.rsplit(".", 2)
        payload = f"{user_id}.{issued_at_raw}"
        if not hmac.compare_digest(_sign(payload, secret), sig):
            return None
        issued_at = int(issued_at_raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if issued_at + SESSION_MAX_AGE_SECONDS < int(time.time()):
        return None
    return SessionClaims(user_id=user_id, issued_at=issued_at)


def cookie_kwargs() -> dict[str, Any]:
    secure = os.environ.get("SESSION_COOKIE_SECURE", "1").strip().lower() not in ("0", "false", "no")
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }


def create_guest_token() -> str:
    return secrets.token_urlsafe(32)


def public_auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {"user": public_user(user)}


def _sign(payload: str, secret: str | None = None) -> str:
    session_secret = secret or os.environ.get("SESSION_SECRET") or DEV_SESSION_SECRET
    return hmac.new(session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
