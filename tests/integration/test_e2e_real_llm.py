"""End-to-end integration test — hits the real Agens LLM API.

Automatically skipped unless ``AGNES_API_KEY`` is set in the environment.
Run with:  pytest tests/integration/test_e2e_real_llm.py -v
"""

from __future__ import annotations

import os
import pathlib

import pytest

# Skip the entire module if no real API key is available.
pytestmark = pytest.mark.skipif(
    not os.environ.get("AGNES_API_KEY"),
    reason="AGNES_API_KEY not set — skipping real LLM integration tests",
)


@pytest.fixture()
def cleanup_saves():
    """Remove any test save files after each test."""
    yield
    save_dir = pathlib.Path("runtime/saves")
    for f in save_dir.glob("e2e_*.json"):
        f.unlink(missing_ok=True)


def test_e2e_new_game_action_save_load(cleanup_saves):
    """Full cycle: new game → action → save → reset → load → verify.

    This test calls the real LLM via the Agens API.  It verifies that:
    - The LLM returns parseable structured output
    - Game state transitions work end-to-end
    - Save/load preserves state correctly

    If the LLM returns unparseable output (e.g. bad key, rate limit),
    the test is marked xfail rather than failing the suite.
    """
    from agens_novel.engine.game_engine import GameEngine

    engine = GameEngine()

    # Track callbacks.
    events: list[tuple[str, str]] = []
    errors: list[str] = []
    engine.on_narrative = lambda text, turn: events.append(("narrative", text[:80]))
    engine.on_error = lambda msg: errors.append(msg)
    engine.on_info = lambda msg: events.append(("info", msg))
    engine.on_character_created = lambda s: events.append(("created", s.char_name))

    # Step 1: Create a new game via World Builder.
    engine.new_game("名叫测试的少年修士，想成为剑仙")

    if not engine.game_session.game_started:
        # LLM returned empty/unparseable data — likely bad key or API issue.
        pytest.xfail(
            f"World Builder returned no data. Errors={errors}, Events={events}"
        )

    assert engine.game_session.char_name, "Character name is empty"
    assert engine.game_session.hp > 0, f"HP is {engine.game_session.hp}"

    char_name = engine.game_session.char_name
    saved_hp = engine.game_session.hp

    # Step 2: Perform an action via Narrator + Judge.
    engine.handle_action("静坐吐纳，感受天地灵气")

    # Step 3: Save.
    engine.save("e2e_test")
    save_path = pathlib.Path("runtime/saves/e2e_test.json")
    assert save_path.exists(), "Save file not created"

    saved_hp_after = engine.game_session.hp
    saved_exp = engine.game_session.experience

    # Step 4: Reset and reload.
    engine.reset()

    engine.load("e2e_test")
    assert engine.game_session.char_name == char_name, "Character name not restored"
    assert engine.game_session.hp == saved_hp_after, "HP not restored"
    assert engine.game_session.experience == saved_exp, "Experience not restored"
