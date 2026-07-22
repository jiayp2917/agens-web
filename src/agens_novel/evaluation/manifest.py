"""Reproducible, non-secret manifests for local model evaluation."""

from __future__ import annotations

import hashlib
import subprocess
from typing import TYPE_CHECKING, Any

from .. import paths
from ..artifacts import sink, store
from ..utils.timing import utcnow_iso
from .scenarios import canonical_scenario_hash, canonical_scenario_payload

if TYPE_CHECKING:
    from .model_config import EvaluationModelConfig
    from .scenarios import CanonicalScenarioV1

_MANIFEST_VERSION = "evaluation-manifest-v1"
_CONTRACT_VERSIONS = {
    "narrator": "NarratorEnvelopeV1",
    "world_opening": "WorldOpeningEnvelopeV1",
    "judge": "JudgeDecisionV1",
}
_HASH_GROUPS = {
    "dependencies": ("pyproject.toml", "uv.lock"),
    "prompts": (
        "src/agens_novel/agents/narrator/nodes.py",
        "src/agens_novel/agents/world_builder/nodes.py",
        "src/agens_novel/agents/judge/nodes.py",
    ),
    "rules": (
        "src/agens_novel/engine/rule_contracts.py",
        "src/agens_novel/engine/turn_rules.py",
        "src/agens_novel/rule_rng.py",
    ),
    "content": ("src/agens_novel/engine/story_catalog.py",),
}


def build_manifest(
    config: EvaluationModelConfig,
    *,
    mode: str,
    story_version: int | None = None,
    scenarios: tuple[CanonicalScenarioV1, ...] = (),
) -> dict[str, Any]:
    """Build safe metadata sufficient to reproduce an evaluation run.

    Hashes prove the code and prompts used without persisting their text. Model
    URLs and all credential-bearing runtime fields are deliberately absent.
    """
    return {
        "manifest_version": _MANIFEST_VERSION,
        "created_at": utcnow_iso(),
        "mode": _safe_mode(mode),
        "commit": _git_commit(),
        "hashes": {name: _hash_group(items) for name, items in _HASH_GROUPS.items()},
        "contracts": dict(_CONTRACT_VERSIONS),
        "provider": config.provider,
        "model": config.model,
        "story_version": story_version,
        "scenarios": [_scenario_metadata(item, story_version) for item in scenarios],
    }


def write_manifest(
    config: EvaluationModelConfig,
    *,
    mode: str,
    story_version: int | None = None,
    scenarios: tuple[CanonicalScenarioV1, ...] = (),
) -> dict[str, Any]:
    """Persist a redacted manifest and an inventory with file hashes."""
    manifest = build_manifest(
        config,
        mode=mode,
        story_version=story_version,
        scenarios=scenarios,
    )
    run_id = store.new_run_id()
    store.write_audit("evaluation_manifest", run_id, manifest)
    write_inventory_manifest(run_id)
    return manifest


def write_inventory_manifest(run_id: str | None = None) -> dict[str, Any]:
    """Write an external-root file inventory after an evaluation stage ends."""
    inventory = sink.external_inventory()
    sink.write_json(
        "evaluation_manifest",
        run_id or store.new_run_id(),
        "inventory.json",
        {"inventory": inventory},
    )
    return inventory


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=paths.PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _hash_group(relative_paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative_path in relative_paths:
        path = paths.PROJECT_ROOT / relative_path
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"[missing]")
        digest.update(b"\0")
    return digest.hexdigest()


def _scenario_metadata(
    scenario: CanonicalScenarioV1,
    story_version: int | None,
) -> dict[str, Any]:
    if story_version is None:
        return {
            "key": scenario.key,
            "world_key": scenario.world_key,
            "run_seed": scenario.run_seed,
            "slot_strategy": _slot_strategy(scenario.slots),
        }
    authority_input = canonical_scenario_payload(scenario, story_version=story_version)
    return {
        "key": scenario.key,
        "world_key": scenario.world_key,
        "run_seed": scenario.run_seed,
        "slot_strategy": _slot_strategy(scenario.slots),
        "authority_hash": canonical_scenario_hash(scenario, story_version=story_version),
        "authority_input": authority_input,
    }


def _slot_strategy(slots: tuple[str, ...]) -> str:
    unique = set(slots)
    if len(unique) == 1:
        return str(next(iter(unique)))
    return "fixed_mixed"


def _safe_mode(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 64:
        raise ValueError("evaluation mode must be a short non-empty identifier")
    return normalized
