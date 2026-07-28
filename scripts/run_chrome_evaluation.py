"""Run one isolated, headed canonical Web evaluation without exposing credentials."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from agens_novel.artifacts import sink
from agens_novel.evaluation.playthrough import canonical_slots
from agens_novel.evaluation.release_state import ReleaseRunStateV1
from agens_novel.evaluation.scenarios import canonical_v3_scenarios

ROOT = Path(__file__).resolve().parents[1]
_PROVIDERS = {"agens", "deepseek"}
_TRANSPORTS = {"json_schema", "json_object", "legacy_tags"}


def main() -> int:
    args = _arguments()
    scenario = _scenario(args.scenario)
    _validate_database_url(args.database_url)
    checkpoint_phase = _checkpoint_phase(args.provider, scenario.key, args.story_version)
    release_state = ReleaseRunStateV1.open(args.release_state) if args.release_state else None
    if release_state is not None and release_state.is_passed(checkpoint_phase):
        print(
            json.dumps(
                {
                    "provider": args.provider,
                    "scenario": scenario.key,
                    "story_version": args.story_version,
                    "accepted": True,
                    "skipped": True,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    label = f"{args.provider.lower()}-{scenario.key}-{args.name}"
    run_id, artifact_root = _prepare_artifact_root(args.artifact_parent, label=label)
    server_env = _server_environment(args, artifact_root, label)
    browser_env = _browser_environment(args, artifact_root, label, scenario)
    started = time.monotonic()
    server = _start_server(server_env, args.port)
    try:
        _wait_for_health(args.port, timeout_seconds=args.startup_timeout_seconds)
        result = _run_browser(browser_env, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        result = {"result": "failed_launcher", "error_category": type(exc).__name__}
    finally:
        _stop_server(server)

    accepted = _acceptance_passed(
        result,
        turns_requested=args.turns,
        story_version=args.story_version,
        scenario=scenario.key,
    )
    if not accepted and result.get("result") in {"passed", "passed_terminal"}:
        result["result"] = "failed_acceptance"
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    result["provider"] = args.provider
    result["scenario"] = scenario.key
    result["story_version"] = args.story_version
    result["turns_requested"] = args.turns
    result["run_label"] = label
    result["run_id"] = run_id
    path = sink.write_json("chrome_orchestrator", label, "summary.json", result)
    if release_state is not None:
        release_state.checkpoint(
            checkpoint_phase,
            status="passed" if accepted else "failed",
            details={
                "run_id": run_id,
                "turns_requested": args.turns,
                "turns_completed": int(result.get("turns_completed") or 0),
                "accepted": accepted,
                "p0_issues": int(result.get("p0_issues") or 0),
                "p1_issues": int(result.get("p1_issues") or 0),
                "fallback": int(result.get("fallback") or 0),
                "repair": int(result.get("repair") or 0),
                "recovery": int(result.get("recovery") or 0),
                "authority_match": result.get("authority_match"),
            },
        )
    summary = {
        "provider": args.provider,
        "scenario": scenario.key,
        "story_version": args.story_version,
        "turns_requested": args.turns,
        "result": result["result"],
        "turns_completed": result.get("turns_completed", 0),
        "p0_issues": result.get("p0_issues", 0),
        "p1_issues": result.get("p1_issues", 0),
        "strict": result.get("strict"),
        "opening_strict": result.get("opening_strict"),
        "fallback": result.get("fallback"),
        "repair": result.get("repair"),
        "recovery": result.get("recovery"),
        "authority_match": result.get("authority_match"),
        "accepted": accepted,
        "summary_path": str(path),
    }
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0 if accepted else 2


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=sorted(_PROVIDERS))
    parser.add_argument("--transport", required=True, choices=sorted(_TRANSPORTS))
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--story-version", type=int, choices=(2, 3), default=3)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-parent", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--turns", type=int, default=90)
    parser.add_argument("--save-load-turn", type=int, default=0)
    parser.add_argument("--refresh-probe", action="store_true")
    parser.add_argument("--double-click-probe", action="store_true")
    parser.add_argument("--conflict-probe", action="store_true")
    parser.add_argument("--viewport", default="1440x1000")
    parser.add_argument("--record-only", action="store_true")
    parser.add_argument("--release-state", type=Path)
    parser.add_argument("--name", default=time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--startup-timeout-seconds", type=int, default=30)
    args = parser.parse_args()
    if args.turns < 1 or args.turns > 95:
        parser.error("--turns must be between 1 and 95")
    if args.save_load_turn < 0 or args.save_load_turn > args.turns:
        parser.error("--save-load-turn must be within the requested turns")
    if not _safe_label(args.name):
        parser.error("--name must contain only letters, digits, dot, underscore, or dash")
    if not _valid_viewport(args.viewport):
        parser.error("--viewport must use WIDTHxHEIGHT")
    return args


def _scenario(key: str):
    scenario = next((item for item in canonical_v3_scenarios() if item.key == key), None)
    if scenario is None:
        raise ValueError("evaluation scenario is not registered")
    return scenario


def _prepare_artifact_root(parent: Path, *, label: str) -> tuple[str, Path]:
    return sink.create_evaluation_run_root(parent, label=label)


def _validate_database_url(raw_url: str) -> None:
    url = make_url(raw_url)
    host = str(url.host or "").lower()
    database = str(url.database or "").lower()
    if not url.drivername.startswith("postgresql") or host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Chrome evaluation requires an isolated local PostgreSQL database")
    if "eval" not in database and "chrome" not in database:
        raise ValueError("Chrome evaluation database name must identify evaluation isolation")


def _server_environment(args: argparse.Namespace, artifact_root: Path, label: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AGENS_EVALUATION_MODE": "1",
            "AGENS_ARTIFACT_ROOT": str(artifact_root),
            "AGENS_EVALUATION_PROVIDER": args.provider,
            "AGENS_EVALUATION_TRANSPORT": args.transport,
            "AGENS_EVALUATION_SCENARIO": args.scenario,
            "AGENS_EVALUATION_STORY_VERSION": str(args.story_version),
            "AGENS_EVALUATION_RECORD_ONLY": "1" if args.record_only else "0",
            "AGENS_EVALUATION_RUN_LABEL": label,
            "AGENS_START_MODEL_WORLD": "1",
            "AGENS_ENV": "development",
            "DATABASE_URL": args.database_url,
            "SESSION_COOKIE_SECURE": "0",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    if args.provider == "agens":
        environment.pop("DEEPSEEK_API_KEY", None)
    else:
        environment.pop("AGNES_API_KEY", None)
    return environment


def _browser_environment(
    args: argparse.Namespace,
    artifact_root: Path,
    label: str,
    scenario: Any,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("AGNES_API_KEY", None)
    environment.pop("DEEPSEEK_API_KEY", None)
    environment.update(
        {
            "AGENS_EVALUATION_MODE": "1",
            "AGENS_ARTIFACT_ROOT": str(artifact_root),
            "AGENS_EVALUATION_RUN_LABEL": label,
            "AGENS_PLAYTEST_URL": f"http://127.0.0.1:{args.port}/",
            "AGENS_PLAYTEST_API_BASE": f"http://127.0.0.1:{args.port}",
            "AGENS_PLAYTEST_DATABASE_LABEL": _database_label(args.database_url),
            "DATABASE_URL": args.database_url,
            "AGENS_PLAYTEST_NAME": label,
            "AGENS_PLAYTEST_TURNS": str(args.turns),
            "AGENS_PLAYTEST_TIMEOUT_MS": str(args.timeout_seconds * 1000),
            "AGENS_PLAYTEST_SLOT_SEQUENCE": "".join(
                canonical_slots(scenario, max_turns=args.turns)
            ),
            "AGENS_PLAYTEST_CANONICAL_SCENARIO": scenario.key,
            "AGENS_PLAYTEST_STORY_VERSION": str(args.story_version),
            "AGENS_PLAYTEST_VIEWPORT": args.viewport,
            "AGENS_PLAYTEST_CONTENT_AUDIT": "1",
            "AGENS_PLAYTEST_FAIL_ON_P1": "1",
            "AGENS_PLAYTEST_POST_LOAD_TURNS": "0",
            "AGENS_PLAYTEST_REQUIRE_PERSISTED_AUDIT": "1",
            "AGENS_PLAYTEST_REQUIRE_LIVE_OPENING": "1",
            "AGENS_PLAYTEST_SAVE_LOAD_TURN": str(getattr(args, "save_load_turn", 0)),
            "AGENS_PLAYTEST_REFRESH_PROBE": "1" if getattr(args, "refresh_probe", False) else "0",
            "AGENS_PLAYTEST_DOUBLE_CLICK_PROBE": "1" if getattr(args, "double_click_probe", False) else "0",
            "AGENS_PLAYTEST_CONFLICT_PROBE": "1" if getattr(args, "conflict_probe", False) else "0",
        }
    )
    return environment


def _database_label(raw_url: str) -> str:
    return str(make_url(raw_url).database or "")


def _start_server(environment: dict[str, str], port: int) -> subprocess.Popen[bytes]:
    command = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "uvicorn",
        "web.backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-access-log",
    ]
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_health(port: int, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        connection: HTTPConnection | None = None
        try:
            connection = HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/api/health")
            if connection.getresponse().status == 200:
                return
        except OSError:
            time.sleep(0.25)
        finally:
            if connection is not None:
                connection.close()
    raise TimeoutError("evaluation backend did not become healthy")


def _run_browser(environment: dict[str, str], *, timeout_seconds: int) -> dict[str, Any]:
    result = subprocess.run(
        ["node", "scripts/local_visible_playtest.cjs"],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    payload = _final_json(_decode_browser_stdout(result.stdout))
    summary_value = payload.get("summary")
    summary: dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
    persisted = summary.get("persisted_turn_audit")
    persisted_audit = persisted if isinstance(persisted, dict) else {}
    start_fallback = bool(summary.get("start_fallback"))
    return {
        "result": str(summary.get("result") or "failed_browser"),
        "turns_completed": int(summary.get("turns_completed") or 0),
        "p0_issues": int(summary.get("p0_issues") or 0),
        "p1_issues": int(summary.get("p1_issues") or 0),
        "strict": _strict_summary(summary),
        "opening_strict": bool(summary.get("start_model_ok")),
        "fallback": int(summary.get("fallback_count") or 0) + int(start_fallback),
        "repair": int(summary.get("repaired_output_count") or 0),
        "recovery": int(summary.get("contract_recovery_count") or 0),
        "authority_match": persisted_audit.get("authority_match"),
        "story_status": persisted_audit.get("story_status"),
        "story_resolution": persisted_audit.get("story_resolution"),
        "post_arc_turns": int(persisted_audit.get("post_arc_turns") or 0),
        "commitment_count": int(persisted_audit.get("commitment_count") or 0),
        "commitment_statuses": list(persisted_audit.get("commitment_statuses") or []),
        "recent_motif_count": int(persisted_audit.get("recent_motif_count") or 0),
        "recent_motifs_unique": bool(persisted_audit.get("recent_motifs_unique")),
        "consequence_count": int(persisted_audit.get("consequence_count") or 0),
        "route_consequences_have_dimensions": bool(
            persisted_audit.get("route_consequences_have_dimensions")
        ),
        "accepted_turns": _accepted_turn_evidence(
            summary.get("accepted_turns"),
            persisted_audit.get("accepted_turns"),
        ),
        "exit_code": int(result.returncode),
    }


def _strict_summary(summary: dict[str, Any]) -> bool:
    turns_completed = int(summary.get("turns_completed") or 0)
    return turns_completed > 0 and int(summary.get("accepted_live_turns") or 0) == turns_completed


def _acceptance_passed(
    result: dict[str, Any],
    *,
    turns_requested: int,
    story_version: int = 2,
    scenario: str = "",
) -> bool:
    browser_result = str(result.get("result") or "")
    turns_completed = int(result.get("turns_completed") or 0)
    expected_turns = (
        turns_completed == turns_requested
        if browser_result == "passed"
        else 0 < turns_completed <= turns_requested
    )
    accepted = (
        browser_result in {"passed", "passed_terminal"}
        and expected_turns
        and bool(result.get("strict"))
        and bool(result.get("opening_strict"))
        and int(result.get("p0_issues") or 0) == 0
        and int(result.get("p1_issues") or 0) == 0
        and int(result.get("fallback") or 0) == 0
        and int(result.get("repair") or 0) == 0
        and int(result.get("recovery") or 0) == 0
        and result.get("authority_match") is True
        and len(result.get("accepted_turns") or []) == turns_completed
        and int(result.get("exit_code") or 0) == 0
    )
    if not accepted or story_version != 3:
        return accepted
    return _v3_story_acceptance(result, scenario=scenario, turns_requested=turns_requested)


def _v3_story_acceptance(result: dict[str, Any], *, scenario: str, turns_requested: int) -> bool:
    expected_resolution = {
        "high_steady": "resolved",
        "low_risk": "failed",
        "middle_mixed": "resolved",
    }.get(scenario)
    commitment_statuses = [str(item) for item in result.get("commitment_statuses") or []]
    commitments_final = len(commitment_statuses) == 2 and all(
        item in {"fulfilled", "failed"} for item in commitment_statuses
    )
    return bool(
        expected_resolution
        and result.get("story_status") == "post_arc"
        and result.get("story_resolution") == expected_resolution
        and commitments_final
        and int(result.get("recent_motif_count") or 0) <= 5
        and bool(result.get("recent_motifs_unique"))
        and int(result.get("consequence_count") or 0) > 0
        and bool(result.get("route_consequences_have_dimensions"))
        and (turns_requested < 95 or int(result.get("post_arc_turns") or 0) >= 5)
    )


def _accepted_turn_evidence(
    browser_turns: Any,
    persisted_turns: Any,
) -> list[dict[str, Any]]:
    """Join final visible turns to rule-owned metadata without raw model output."""
    persisted_items = persisted_turns if isinstance(persisted_turns, list) else []
    persisted_by_turn = {
        int(item.get("turn") or 0): item
        for item in persisted_items
        if isinstance(item, dict)
        if int(item.get("turn") or 0) > 0
    }
    accepted: list[dict[str, Any]] = []
    for browser in browser_turns if isinstance(browser_turns, list) else []:
        if not isinstance(browser, dict):
            continue
        turn = int(browser.get("turn") or 0)
        persisted = persisted_by_turn.get(turn)
        if turn <= 0 or persisted is None:
            continue
        choices = persisted.get("choices")
        accepted.append(
            {
                "turn": turn,
                "slot": str(persisted.get("slot") or browser.get("slot") or ""),
                "intent_category": str(persisted.get("intent_category") or ""),
                "event_id": str(persisted.get("event_id") or ""),
                "motif": str(persisted.get("motif") or ""),
                "rule_outcome": str(persisted.get("rule_outcome") or ""),
                "narrative": str(persisted.get("narrative") or browser.get("narrative") or ""),
                "choices": [str(item) for item in choices]
                if isinstance(choices, list)
                else [str(item) for item in browser.get("choices") or []],
                "authority_hash": str(persisted.get("authority_hash") or ""),
                "strict": dict(browser.get("strict") or {}),
                "retry": bool(browser.get("retry")),
                "repair": bool(browser.get("repair")),
                "fallback": bool(browser.get("fallback")),
                "recovery": bool(browser.get("recovery")),
                "timing_ms": dict(browser.get("timing_ms") or {}),
            }
        )
    return sorted(accepted, key=lambda item: int(item["turn"]))


def _decode_browser_stdout(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("browser evaluator emitted non-UTF-8 output") from exc


def _final_json(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("browser evaluator did not return a safe summary") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("browser evaluator summary is invalid")
    return decoded


def _stop_server(server: subprocess.Popen[bytes]) -> None:
    if server.poll() is not None:
        return
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)


def _safe_label(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in "._-" for character in value)


def _valid_viewport(value: str) -> bool:
    try:
        width, height = (int(item) for item in str(value).lower().split("x", maxsplit=1))
    except (TypeError, ValueError):
        return False
    return 200 <= width <= 4096 and 200 <= height <= 4096


def _checkpoint_phase(provider: str, scenario: str, story_version: int) -> str:
    return f"chrome-{provider.lower()}-v{story_version}-{scenario}"


if __name__ == "__main__":
    raise SystemExit(main())
