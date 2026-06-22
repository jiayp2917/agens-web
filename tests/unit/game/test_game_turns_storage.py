"""Game-mode v5 Layer 8: game_runs / game_turns storage + rarity unlock gates.

Spec §8.3 (game_turns JSONB table) and §11 (rarity unlock gates driven by
runs_completed / ascension_count).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is importable when running from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agens_novel.game.constants import rarity_unlocked_for  # noqa: E402


class TestRarityUnlockGates:
    """Spec §11: 紫/橙/红 gate on completed runs and ascensions."""

    def test_new_player_unlocks_only_white_green_blue(self) -> None:
        assert rarity_unlocked_for(runs_completed=0, ascension_count=0) == ["白", "绿", "蓝"]

    def test_one_run_unlocks_purple(self) -> None:
        unlocked = rarity_unlocked_for(runs_completed=1, ascension_count=0)
        assert "紫" in unlocked
        assert "橙" not in unlocked
        assert "红" not in unlocked

    def test_one_ascension_unlocks_orange(self) -> None:
        unlocked = rarity_unlocked_for(runs_completed=1, ascension_count=1)
        assert "橙" in unlocked
        assert "红" not in unlocked

    def test_two_ascensions_plus_run_unlocks_red_for_random(self) -> None:
        unlocked_random = rarity_unlocked_for(
            runs_completed=1, ascension_count=2, for_random=True
        )
        assert "红" in unlocked_random
        # Select pool for 红 still needs 2 ascensions (no extra run gate).
        unlocked_select = rarity_unlocked_for(
            runs_completed=0, ascension_count=2, for_random=False
        )
        assert "红" in unlocked_select

    def test_red_requires_two_ascensions(self) -> None:
        unlocked = rarity_unlocked_for(runs_completed=5, ascension_count=1)
        assert "红" not in unlocked  # only 1 ascension


@pytest.fixture()
def sqlite_db(tmp_path, monkeypatch):
    """A fresh SQLiteWebDatabase on a temp path."""
    from web.backend.database_sqlite import SQLiteWebDatabase

    db_path = tmp_path / "test_game_turns.db"
    return SQLiteWebDatabase(path=db_path)


class TestGameRunAndTurnStorage:
    """Spec §8.3: game_runs + game_turns + player_progress tables."""

    def test_record_run_increments_progress(self, sqlite_db) -> None:
        user = sqlite_db.upsert_user("tester")
        uid = user["id"]

        # First run, no ascension.
        run1 = sqlite_db.record_game_run(uid, char_name="甲", realm="练气",
                                         death_cause="寿元耗尽", ascended=False,
                                         turn_count=12)
        assert run1
        progress = sqlite_db.get_player_progress(uid)
        assert progress == {"runs_completed": 1, "ascension_count": 0}

        # Second run, ascension.
        sqlite_db.record_game_run(uid, char_name="乙", realm="飞升",
                                  death_cause="飞升成仙", ascended=True,
                                  turn_count=50)
        progress = sqlite_db.get_player_progress(uid)
        assert progress == {"runs_completed": 2, "ascension_count": 1}

    def test_new_player_progress_is_zero(self, sqlite_db) -> None:
        user = sqlite_db.upsert_user("newbie")
        assert sqlite_db.get_player_progress(user["id"]) == {
            "runs_completed": 0, "ascension_count": 0,
        }

    def test_record_turn_logs_settled_turn(self, sqlite_db) -> None:
        user = sqlite_db.upsert_user("logger")
        uid = user["id"]
        run_id = sqlite_db.record_game_run(uid, char_name="丙", realm="筑基")

        turn_id = sqlite_db.record_game_turn(
            run_id, turn_no=1,
            start_age=18, elapsed_years=3, end_age=21,
            lifespan=120, remaining_lifespan=99,
            choice_taken="A 稳妥：闭关吐纳",
            choices=["A 闭关吐纳", "B 外出寻机", "C 入险地", "D 听天命"],
            state_delta={"character": {"experience": "+15"}},
            state_after={"character": {"realm": "筑基", "age": 21}},
            calendar_summary="筑基三年，灵气渐浓。",
            narrative="你盘膝吐纳，灵气如潮。",
            event_kind="cultivation",
        )
        assert turn_id
        # The turn is retrievable and round-trips JSON.
        with sqlite_db.connect() as conn:
            row = conn.execute(
                "SELECT turn_no, end_age, choice_taken, choices_json, event_kind "
                "FROM game_turns WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        assert row["turn_no"] == 1
        assert row["end_age"] == 21
        assert row["choice_taken"] == "A 稳妥：闭关吐纳"
        assert row["event_kind"] == "cultivation"
        assert "闭关吐纳" in row["choices_json"]

    def test_turn_no_unique_per_run(self, sqlite_db) -> None:
        user = sqlite_db.upsert_user("dup")
        uid = user["id"]
        run_id = sqlite_db.record_game_run(uid, char_name="丁", realm="金丹")
        sqlite_db.record_game_turn(
            run_id, turn_no=1, start_age=20, elapsed_years=1, end_age=21,
            lifespan=200, remaining_lifespan=179, choice_taken=None,
            choices=[], state_delta={}, state_after={}, calendar_summary="",
            narrative="", event_kind="event",
        )
        # Duplicate turn_no for the same run should be rejected by the UNIQUE constraint.
        with pytest.raises(Exception):
            sqlite_db.record_game_turn(
                run_id, turn_no=1, start_age=21, elapsed_years=1, end_age=22,
                lifespan=200, remaining_lifespan=178, choice_taken=None,
                choices=[], state_delta={}, state_after={}, calendar_summary="",
                narrative="", event_kind="event",
            )
