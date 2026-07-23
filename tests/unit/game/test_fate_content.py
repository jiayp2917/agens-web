from __future__ import annotations

from agens_novel.game.fate_content import FATE_ENTRIES, catalog_rows, entries_for, spirit_root_rules
from web.backend.catalog_seed import _seed_table


def test_v3_fate_entries_are_complete_and_unique() -> None:
    assert len(entries_for("talent")) == 8
    assert len(entries_for("family")) == 8
    assert len(entries_for("root")) == 6
    assert len({entry.key for entry in FATE_ENTRIES}) == len(FATE_ENTRIES)
    assert len({entry.name for entry in FATE_ENTRIES}) == len(FATE_ENTRIES)
    assert all(entry.worlds and entry.tags for entry in FATE_ENTRIES)
    assert all(entry.early_hook and entry.middle_pressure and entry.late_outcome for entry in FATE_ENTRIES)


def test_v3_catalog_rows_and_spirit_root_rules_share_names() -> None:
    root_rows = catalog_rows("root")
    assert {row["name"] for row in root_rows} == {row["name"] for row in spirit_root_rules()}
    assert all(row["id"] for row in catalog_rows("talent"))


def test_seed_table_only_appends_missing_names() -> None:
    class FakeCatalog:
        def __init__(self) -> None:
            self.rows = [{"name": "已有词条"}]
            self.inserted: list[dict] = []

        def list_catalog(self, _table: str) -> list[dict]:
            return list(self.rows)

        def insert_catalog(self, _table: str, row: dict) -> None:
            self.inserted.append(row)

    fake = FakeCatalog()
    rows = [{"name": "已有词条"}, {"name": "新增词条"}]
    assert _seed_table(fake, "catalog_talents", rows) == 1
    assert fake.inserted == [{"name": "新增词条"}]


def test_seed_table_only_supplements_empty_spirit_root_metadata() -> None:
    class FakeCatalog:
        def __init__(self) -> None:
            self.rows = [{"name": "阴阳灵根", "element": "", "event_tags": []}]
            self.supplemented: list[tuple[str, str, dict]] = []

        def list_catalog(self, _table: str) -> list[dict]:
            return list(self.rows)

        def insert_catalog(self, _table: str, _row: dict) -> None:
            raise AssertionError("existing catalog rows must not be replaced")

        def supplement_catalog_metadata(self, table: str, name: str, metadata: dict) -> None:
            self.supplemented.append((table, name, metadata))

    fake = FakeCatalog()
    row = {
        "name": "阴阳灵根",
        "element": "阴阳",
        "grade": "天",
        "cultivation_bonus": 1.8,
        "breakthrough_bonus": 0.12,
        "event_tags": ["阴阳"],
    }

    assert _seed_table(fake, "catalog_spirit_roots", [row], supplement_metadata=True) == 0
    assert fake.supplemented == [
        (
            "catalog_spirit_roots",
            "阴阳灵根",
            {
                "element": "阴阳",
                "grade": "天",
                "cultivation_bonus": 1.8,
                "breakthrough_bonus": 0.12,
                "event_tags": ["阴阳"],
            },
        )
    ]
