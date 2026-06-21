"""Export agens-web SQLite data to a JSON file."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/web/agens_web.sqlite3")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    db_path = Path(args.db)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        data = {}
        for table in ("users", "sessions", "saves", "model_config"):
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                rows = []
            data[table] = [dict(row) for row in rows]

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
