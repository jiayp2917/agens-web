"""Static guardrails that keep pure unit tests independent from PostgreSQL."""

from __future__ import annotations

from pathlib import Path

_UNIT_ROOT = Path(__file__).resolve().parent
_FORBIDDEN_REFERENCES = (
    "PostgresWebDatabase",
    "web.backend.database_postgres",
    "sqlalchemy import create_engine",
)


def test_unit_tests_do_not_depend_on_postgres() -> None:
    offenders: list[str] = []
    for path in _UNIT_ROOT.rglob("test_*.py"):
        if path == Path(__file__):
            continue
        source = path.read_text(encoding="utf-8")
        matches = [reference for reference in _FORBIDDEN_REFERENCES if reference in source]
        if matches:
            offenders.append(f"{path.relative_to(_UNIT_ROOT)}: {', '.join(matches)}")
    assert not offenders, "PostgreSQL tests belong in tests/integration or tests/web: " + "; ".join(offenders)
