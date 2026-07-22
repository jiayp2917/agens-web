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
from agens_novel.evaluation.scenarios import canonical_v3_scenarios

ROOT = Path(__file__).resolve().parents[1]
_PROVIDERS = {"agens", "deepseek"}
_TRANSPORTS = {"json_schema", "json_object", "legacy_tags"}


def main() -> int:
    args = _arguments()
    scenario = _scenario(args.scenario)
    _validate_database_url(args.database_url)
    artifact_root = _prepare_artifact_root(args.artifact_root)
    label = f"{args.provider.lower()}-{scenario.key}-{args.name}"
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

    accepted = _acceptance_passed(result, turns_requested=args.turns)
    if not accepted and result.get("result") in {"passed", "passed_terminal"}:
        result["result"] = "failed_acceptance"
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    result["provider"] = args.provider
    result["scenario"] = scenario.key
    result["turns_requested"] = args.turns
    result["run_label"] = label
    path = sink.write_json("chrome_orchestrator", label, "summary.json", result)
    summary = {
        "provider": args.provider,
        "scenario": scenario.key,
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
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--turns", type=int, default=90)
    parser.add_argument("--save-load-turn", type=int, default=0)
    parser.add_argument("--refresh-probe", action="store_true")
    parser.add_argument("--double-click-probe", action="store_true")
    parser.add_argument("--conflict-probe", action="store_true")
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
    return args


def _scenario(key: str):
    scenario = next((item for item in canonical_v3_scenarios() if item.key == key), None)
    if scenario is None:
        raise ValueError("evaluation scenario is not registered")
    return scenario


def _prepare_artifact_root(raw_root: Path) -> Path:
    os.environ["AGENS_EVALUATION_MODE"] = "1"
    os.environ["AGENS_ARTIFACT_ROOT"] = str(raw_root)
    root = sink.ensure_evaluation_sink_ready()
    if root is None:
        raise RuntimeError("evaluation artifact root is unavailable")
    return root


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
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
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
        "exit_code": int(result.returncode),
    }


def _strict_summary(summary: dict[str, Any]) -> bool:
    turns_completed = int(summary.get("turns_completed") or 0)
    return turns_completed > 0 and int(summary.get("accepted_live_turns") or 0) == turns_completed


def _acceptance_passed(result: dict[str, Any], *, turns_requested: int) -> bool:
    browser_result = str(result.get("result") or "")
    turns_completed = int(result.get("turns_completed") or 0)
    expected_turns = (
        turns_completed == turns_requested
        if browser_result == "passed"
        else 0 < turns_completed <= turns_requested
    )
    return (
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
        and int(result.get("exit_code") or 0) == 0
    )


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


if __name__ == "__main__":
    raise SystemExit(main())
