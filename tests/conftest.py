"""Pytest fixtures.

- ``fake_llm``        : a stub for ``agens_novel.llm.client.call_llm``.
- ``temp_project_root``: an isolated runtime/ tree under tmp_path.
- ``clean_settings``  : clear AGNES_* env vars during a test.
- ``set_api_key``     : inject a fake key (never the real one).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def temp_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate runtime/ under tmp_path while keeping the real project root for config."""
    # Don't change PROJECT_ROOT — we want config/prompts/system/writer.md to be found.
    # Instead, create a per-test runtime tree inside tmp_path and rewire the runtime
    # path constants to point at it.
    import importlib
    from agens_novel import paths as p_mod
    importlib.reload(p_mod)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(p_mod, "RUNTIME_DIR", runtime_root)
    monkeypatch.setattr(p_mod, "ARTIFACT_ROOT", runtime_root / "artifacts")
    monkeypatch.setattr(p_mod, "CHECKPOINT_DIR", runtime_root / "checkpoints")
    monkeypatch.setattr(p_mod, "LOG_DIR", runtime_root / "logs")
    p_mod.ensure_runtime_dirs()
    yield tmp_path
    importlib.reload(p_mod)


@pytest.fixture
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear all AGNES_* env vars during a test."""
    for var in list(os.environ):
        if var.startswith("AGNES_"):
            monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def set_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Inject a fake key (deterministic, never the real one)."""
    fake = "sk-test-fixture-1234567890"
    monkeypatch.setenv("AGNES_API_KEY", fake)
    monkeypatch.setenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    monkeypatch.setenv("AGNES_MODEL", "agnes-2.0-flash")
    return fake


@pytest.fixture
def fake_llm() -> AsyncMock:
    """Stub for ``call_llm`` returning a canned prose.

    The agent code imports ``call_llm`` from ``agens_novel.llm.client``, so we
    patch the symbol at the import site (``agens_novel.agents.writer.nodes``)
    to ensure the stub takes effect regardless of how the call is reached.
    """
    canned_text = "许满放下外卖箱,抬头看了看破旧筒子楼上方的天空。"
    mock = AsyncMock(return_value={
        "text": canned_text,
        "model": "agnes-2.0-flash",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "finish_reason": "stop",
        "elapsed_ms": 1200,
        "raw": {"stub": True},
    })
    with patch("agens_novel.agents.writer.nodes.call_llm", mock):
        yield mock, canned_text
