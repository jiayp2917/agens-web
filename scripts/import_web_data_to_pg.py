"""Import exported agens-web JSON data into the configured PostgreSQL database."""

from __future__ import annotations

import argparse
import json
import os

from web.backend.database_postgres import PostgresWebDatabase


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    data = json.load(open(args.input, encoding="utf-8"))
    db = PostgresWebDatabase()
    for user in data.get("users", []):
        if db.get_user_by_id(user["id"]) is None:
            db.create_user(
                user.get("username") or "local",
                user.get("password_hash") or "",
                is_admin=bool(user.get("is_admin")),
                user_id=user["id"],
            )
    for session in data.get("sessions", []):
        db.save_session(
            session["id"],
            session["user_id"],
            session.get("title") or "新局",
            json.loads(session.get("snapshot_json") or "{}"),
            json.loads(session.get("events_json") or "[]"),
        )
    for save in data.get("saves", []):
        db.save_game_slot(
            save["user_id"],
            save["name"],
            json.loads(save.get("snapshot_json") or "{}"),
            json.loads(save.get("events_json") or "[]"),
        )


if __name__ == "__main__":
    main()
