"""Zip agens/ excluding build artifacts.

Run from inside the agens/ directory:
    python zip_agens.py [output_path]
Default output: ../agens.zip (one level up from agens/, i.e. in F:\Projects\)
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "agens.zip"

# Exclude anything matching these patterns. Dir entries are matched as a single
# path component, or as a joined relative path with `as_posix()` so
# "runtime/artifacts" matches runtime/artifacts/anything.
EXCLUDE_DIRS = {
    ".venv", ".venv311",
    ".pytest_cache",
    ".workbuddy",
    ".git",
    "node_modules",
    "mobile/.buildozer",
    "mobile/bin",
    "runtime/artifacts",
    "runtime/checkpoints",
    "runtime/logs",
    "runtime/backups",
    "runtime/saves",
    ".claude",
    ".agents",
    "__pycache__",
}
EXCLUDE_FILE_BASENAMES = {
    "buildozer-debug.log",
    "settings.local.json",
}
EXCLUDE_EXTS = {".pyc", ".tmp"}


def is_excluded(rel: Path) -> bool:
    parts = rel.parts
    posix = rel.as_posix()
    # Build joined prefixes of the relative path to allow multi-segment dir
    # matches like "runtime/artifacts".
    for i in range(len(parts)):
        joined = "/".join(parts[: i + 1])
        if joined in EXCLUDE_DIRS:
            return True
    # .venv* (any name starting with .venv, except the example file)
    for part in parts:
        if part.startswith(".venv") and part != ".venv.example":
            return True
    # File basenames we never want, even when they're at the top of the project
    if rel.name in EXCLUDE_FILE_BASENAMES:
        return True
    if Path(rel.name).suffix in EXCLUDE_EXTS:
        return True
    return False


def main() -> int:
    if not OUT.parent.exists():
        print(f"ERROR: {OUT.parent} does not exist", file=sys.stderr)
        return 1

    # Delete old zip if it exists (avoid appending into stale archive)
    if OUT.exists():
        OUT.unlink()

    count = 0
    size_total = 0
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if is_excluded(rel):
                continue
            arcname = Path("agens") / rel  # top-level folder is agens/
            zf.write(path, arcname.as_posix())
            count += 1
            size_total += path.stat().st_size

    out_size = OUT.stat().st_size
    print(f"OK: {count} files, source {size_total/1024/1024:.1f} MB, "
          f"zip {out_size/1024/1024:.1f} MB")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
