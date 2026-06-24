from __future__ import annotations

from web.backend.database_common import (
    catalog_seed_sources,
    decode_json_fields,
    player_progress_summary,
    prepare_catalog_row,
)


def test_player_progress_summary_normalizes_missing_and_row_values() -> None:
    assert player_progress_summary(None) == {
        "runs_completed": 0,
        "ascension_count": 0,
    }
    assert player_progress_summary({"runs_completed": "2", "ascension_count": "1"}) == {
        "runs_completed": 2,
        "ascension_count": 1,
    }


def test_prepare_catalog_row_encodes_json_and_preserves_input() -> None:
    row = {
        "id": "talent-1",
        "name": "测试天赋",
        "attribute_mods": {"luck": 3},
        "tags": ["test"],
    }

    prepared = prepare_catalog_row(row, created_at=123.0)

    assert row["attribute_mods"] == {"luck": 3}
    assert prepared["created_at"] == 123.0
    assert prepared["attribute_mods"] == '{"luck":3}'
    assert prepared["tags"] == '["test"]'
    assert decode_json_fields(prepared)["attribute_mods"] == {"luck": 3}


def test_catalog_seed_sources_cover_all_catalog_tables() -> None:
    tables = [table for table, rows in catalog_seed_sources()]

    assert tables == [
        "catalog_talents",
        "catalog_family_backgrounds",
        "catalog_spirit_roots",
        "catalog_difficulties",
        "catalog_story_seeds",
    ]
    assert all(rows for _, rows in catalog_seed_sources())
