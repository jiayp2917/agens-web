"""Safety checks for destructive operations on the single local database."""

from __future__ import annotations

from sqlalchemy.engine import URL

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def require_loopback_postgres_url(url: URL) -> URL:
    """Return a PostgreSQL URL only when it explicitly targets this machine."""
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
    host = (url.host or "").strip().strip("[]").lower()
    if host not in _LOOPBACK_HOSTS:
        raise RuntimeError("destructive database operations require a loopback DATABASE_URL")
    return url
