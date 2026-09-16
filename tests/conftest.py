"""Pytest fixtures.

- ``fake_narrator_llm``  : stub for narrator agent's call_llm.
- ``fake_world_builder_llm``: stub for world_builder agent's call_llm.
- ``temp_project_root``  : an isolated runtime/ tree under tmp_path.
- ``clean_settings``     : clear AGNES_* env vars during a test.
- ``set_api_key``        : inject a fake key (never the real one).
"""

from __future__ import annotations

import os
from collections.abc import Generator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify the PostgreSQL-backed Web suite without duplicating markers."""
    web_root = Path(__file__).resolve().parent / "web"
    for item in items:
        path = Path(str(item.path)).resolve()
        if path.is_relative_to(web_root):
            item.add_marker(pytest.mark.postgres)


@pytest.fixture
def temp_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate runtime/ under tmp_path while keeping the real project root for config."""
    import importlib

    from agens_novel import paths as p_mod
    importlib.reload(p_mod)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(p_mod, "RUNTIME_DIR", runtime_root)
    monkeypatch.setattr(p_mod, "ARTIFACT_ROOT", runtime_root / "artifacts")
    monkeypatch.setattr(p_mod, "LOG_DIR", runtime_root / "logs")
    monkeypatch.setattr(p_mod, "SAVE_DIR", runtime_root / "saves")
    for sub in ("artifacts", "logs", "saves"):
        (runtime_root / sub).mkdir(parents=True, exist_ok=True)
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
def fake_narrator_llm() -> Generator[tuple[AsyncMock, str], None, None]:
    """Stub for narrator agent's call_llm."""
    canned = (
        "你感受到体内灵气涌动，丹田中一团温热的力量缓缓凝聚。\n"
        "周围的灵气向你汇聚，树叶微微颤动。\n"
        "<state_update>\n"
        '{"character": {"attributes": {"willpower": 1, "root_bone": 1}}, '
        '"world": {"current_scene": "修炼中的灵气感应", "day_count": 1}}\n'
        "</state_update>"
    )
    mock = AsyncMock(return_value={
        "text": canned,
        "model": "agnes-2.0-flash",
        "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
        "finish_reason": "stop",
        "elapsed_ms": 1500,
        "raw": {"stub": True},
    })
    with patch("agens_novel.agents.narrator.nodes.call_llm", mock):
        yield mock, canned


@pytest.fixture
def fake_world_builder_llm() -> Generator[tuple[AsyncMock, str], None, None]:
    """Stub for world_builder agent's call_llm."""
    canned_data = {
        "character": {
            "name": "许满", "realm": "练气", "realm_stage": 1,
            "spirit_root": "火木双灵根", "spirit_root_grade": "地",
            "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功"}],
            "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具"}],
            "status_effects": [], "lifespan": 100,
        },
        "world": {
            "current_scene": "晨雾中的青云山外门",
            "location": "青云山外门", "region": "东荒",
            "npcs_present": [{"name": "陈师兄", "relation": "同门", "realm": "练气五层"}],
            "active_quests": [{"name": "入门修行", "description": "完成基础修炼", "status": "active"}],
            "discovered_locations": ["青云山外门"],
            "lore_facts": ["青云门是东荒三宗之一"],
            "day_count": 1,
        },
        "opening_narrative": "晨曦微露，青云山外门的大殿前，一个少年盘膝而坐。",
    }
    import json
    canned = json.dumps(canned_data, ensure_ascii=False)
    mock = AsyncMock(return_value={
        "text": canned,
        "model": "agnes-2.0-flash",
        "usage": {"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500},
        "finish_reason": "stop",
        "elapsed_ms": 2000,
        "raw": {"stub": True},
    })
    with patch("agens_novel.agents.common.call_llm", mock):
        yield mock, canned
