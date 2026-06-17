"""Save/load manager for game sessions.

Supports multi-slot saves: 5 manual slots + 1 auto-save.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .. import paths
from ..session.game_session import GameSession

log = logging.getLogger(__name__)

# Module-level override for save directory (used by mobile apps).
_custom_save_dir: Path | None = None

# Reserved slot names.
AUTOSAVE_NAME = "autosave"
MAX_MANUAL_SAVES = 5


def set_save_dir(save_dir: Path) -> None:
    """Override the save directory (e.g. for Android internal storage)."""
    global _custom_save_dir
    _custom_save_dir = save_dir


def _get_save_dir() -> Path:
    d = _custom_save_dir or paths.SAVE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_path(name: str) -> Path:
    """Build save file path using the active save directory."""
    save_dir = _get_save_dir()
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "default"
    return save_dir / f"{safe_name}.json"


def save_game(session: GameSession, name: str = "autosave") -> str:
    """Save a GameSession to disk. Returns the save file path."""
    path = _save_path(name)
    data = session.to_save_dict()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Game saved to %s", path)
    return str(path)


def load_game(name: str = "autosave") -> GameSession | None:
    """Load a GameSession from disk.

    Raises FileNotFoundError if missing. Returns None when the save file is
    present but corrupt.
    """
    path = _save_path(name)
    if not path.exists():
        raise FileNotFoundError(f"存档不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        session = GameSession.from_save_dict(data)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("Corrupt save ignored: %s (%s)", path, exc)
        return None
    session.save_file = str(path)
    log.info("Game loaded from %s", path)
    return session


def list_saves() -> list[dict[str, Any]]:
    """Return a list of available saves with metadata."""
    saves_dir = _get_save_dir()
    if not saves_dir.exists():
        return []
    result = []
    for p in sorted(saves_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            char = data.get("character", {})
            result.append({
                "name": p.stem,
                "char_name": char.get("name", "?"),
                "realm": char.get("realm", "?"),
                "turn_count": data.get("turn_count", 0),
                "is_autosave": p.stem == AUTOSAVE_NAME,
                "path": str(p),
            })
        except (json.JSONDecodeError, ValueError):
            result.append({"name": p.stem, "error": "corrupt", "path": str(p)})
    return result


def delete_save(name: str) -> None:
    """Delete a save file by name."""
    path = _save_path(name)
    if path.exists():
        path.unlink()
        log.info("Save deleted: %s", path)
    else:
        raise FileNotFoundError(f"存档不存在: {path}")


def rename_save(old_name: str, new_name: str) -> None:
    """Rename a save file."""
    old_path = _save_path(old_name)
    new_path = _save_path(new_name)
    if not old_path.exists():
        raise FileNotFoundError(f"存档不存在: {old_path}")
    old_path.rename(new_path)
    log.info("Save renamed: %s -> %s", old_path, new_path)


def get_manual_save_slots() -> list[dict[str, Any]]:
    """Return info about the 5 manual save slots (occupied or empty)."""
    saves = {s["name"]: s for s in list_saves() if not s.get("error")}
    slots = []
    for i in range(1, MAX_MANUAL_SAVES + 1):
        slot_name = f"slot_{i}"
        if slot_name in saves:
            info = saves[slot_name]
            slots.append({
                "slot": i,
                "name": slot_name,
                "occupied": True,
                "char_name": info.get("char_name", "?"),
                "realm": info.get("realm", "?"),
                "turn_count": info.get("turn_count", 0),
            })
        else:
            slots.append({
                "slot": i,
                "name": slot_name,
                "occupied": False,
            })
    return slots

