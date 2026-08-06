"""PostgreSQL coverage for game-run and game-turn persistence."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from agens_novel.game.constants import rarity_unlocked_for

pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgres,
    pytest.mark.xdist_group("pg_test_db"),
]


class TestRarityUnlockGates:
    """Spec 11: purple/orange/red gates depend on completed runs and ascensions."""

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
        unlocked_select = rarity_unlocked_for(
            runs_completed=0, ascension_count=2, for_random=False
        )
        assert "红" in unlocked_select

    def test_red_requires_two_ascensions(self) -> None:
        unlocked = rarity_unlocked_for(runs_completed=5, ascension_count=1)
        assert "红" not in unlocked


@pytest.fixture()
def pg_db(_pg_url: str, monkeypatch: pytest.MonkeyPatch):
    """A fresh PostgresWebDatabase against the local test database."""
    from web.backend.database_postgres import PostgresWebDatabase

    engine = create_engine(_pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE game_runs, game_turns, player_progress, users RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()
    monkeypatch.setenv("DATABASE_URL", _pg_url)
    database = PostgresWebDatabase(_pg_url)
    yield database
    database.engine.dispose()


class TestGameRunAndTurnStorage:
    """Spec 8.3: game_runs and game_turns persist a settled rule result."""

    def test_record_run_increments_progress(self, pg_db) -> None:
        user = pg_db.upsert_user("tester")
        uid = user["id"]
        run1 = pg_db.record_game_run(
            uid, char_name="甲", realm="练气", death_cause="寿元耗尽", ascended=False, turn_count=12
        )
        assert run1
        assert pg_db.get_player_progress(uid) == {"runs_completed": 1, "ascension_count": 0}
        pg_db.record_game_run(
            uid, char_name="乙", realm="飞升", death_cause="飞升成仙", ascended=True, turn_count=50
        )
        assert pg_db.get_player_progress(uid) == {"runs_completed": 2, "ascension_count": 1}

    def test_new_player_progress_is_zero(self, pg_db) -> None:
        user = pg_db.upsert_user("newbie")
        assert pg_db.get_player_progress(user["id"]) == {"runs_completed": 0, "ascension_count": 0}

    def test_record_turn_logs_settled_turn(self, pg_db) -> None:
        user = pg_db.upsert_user("logger")
        run_id = pg_db.record_game_run(user["id"], char_name="丙", realm="筑基")
        turn_id = pg_db.record_game_turn(
            run_id,
            turn_no=1,
            start_age=18,
            elapsed_years=3,
            end_age=21,
            lifespan=120,
            remaining_lifespan=99,
            choice_taken="A 稳妥：闭关吐纳",
            choices=["A 闭关吐纳", "B 外出寻机", "C 入险地", "D 听天命"],
            state_delta={"character": {"attributes": {"willpower": 1}}},
            state_after={"character": {"realm": "筑基", "age": 21}},
            calendar_summary="筑基三年，灵气渐浓。",
            narrative="你盘膝吐纳，灵气如潮。",
            event_kind="cultivation",
        )
        assert turn_id
        with pg_db.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT turn_no, end_age, choice_taken, choices, event_kind "
                    "FROM game_turns WHERE run_id = :rid"
                ),
                {"rid": run_id},
            ).fetchone()
        mapping = row._mapping
        assert mapping["turn_no"] == 1
        assert mapping["end_age"] == 21
        assert mapping["choice_taken"] == "A 稳妥：闭关吐纳"
        assert mapping["event_kind"] == "cultivation"
        assert any("闭关吐纳" in str(choice) for choice in mapping["choices"])

    def test_turn_no_unique_per_run(self, pg_db) -> None:
        user = pg_db.upsert_user("dup")
        run_id = pg_db.record_game_run(user["id"], char_name="丁", realm="金丹")
        pg_db.record_game_turn(
            run_id,
            turn_no=1,
            start_age=20,
            elapsed_years=1,
            end_age=21,
            lifespan=200,
            remaining_lifespan=179,
            choice_taken=None,
            choices=[],
            state_delta={},
            state_after={},
            calendar_summary="",
            narrative="",
            event_kind="event",
        )
        with pytest.raises(IntegrityError):
            pg_db.record_game_turn(
                run_id,
                turn_no=1,
                start_age=21,
                elapsed_years=1,
                end_age=22,
                lifespan=200,
                remaining_lifespan=178,
                choice_taken=None,
                choices=[],
                state_delta={},
                state_after={},
                calendar_summary="",
                narrative="",
                event_kind="event",
            )
