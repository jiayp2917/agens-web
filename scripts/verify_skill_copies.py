"""Check the read-only Claude compatibility copies of Codex skills."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

SKILL_NAMES = (
    "api-and-interface-design",
    "browser-testing-with-devtools",
    "context-engineering",
    "frontend-ui-engineering",
    "performance-optimization",
    "security-and-hardening",
)


def find_skill_copy_drift(
    repository_root: Path,
    *,
    skill_names: Iterable[str] = SKILL_NAMES,
) -> list[dict[str, str]]:
    drifts: list[dict[str, str]] = []
    for skill_name in skill_names:
        source = repository_root / ".codex" / "skills" / skill_name / "SKILL.md"
        copy = repository_root / ".claude" / "skills" / skill_name / "SKILL.md"
        source_hash = _sha256_or_missing(source)
        copy_hash = _sha256_or_missing(copy)
        if source_hash != copy_hash:
            drifts.append(
                {
                    "skill": skill_name,
                    "source_sha256": source_hash,
                    "copy_sha256": copy_hash,
                }
            )
    return drifts


def _sha256_or_missing(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    drifts = find_skill_copy_drift(args.repository_root)
    print(json.dumps({"drifts": drifts, "valid": not drifts}, ensure_ascii=False, sort_keys=True))
    return 0 if not drifts else 1


if __name__ == "__main__":
    raise SystemExit(main())
