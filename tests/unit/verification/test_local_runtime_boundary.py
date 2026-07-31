"""Regression checks for the single local model-runtime boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_BANNED_TOKENS = (
    "AGENS_EVALUATION_",
    "AGENS_ARTIFACT_ROOT",
    "AGENS_EGRESS_PROXY_URL",
    "EvaluationModelConfig",
    "EvaluationLedger",
    "evaluation_app",
    "ModelCallObserver",
    "model_call_observer",
)


def test_product_and_tool_sources_have_no_dedicated_evaluation_runtime() -> None:
    roots = (ROOT / "src", ROOT / "web", ROOT / "scripts")
    sources = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        and "node_modules" not in path.parts
        and path.suffix in {".py", ".cjs", ".js", ".ts", ".tsx"}
    ]

    matches = {
        token: [path.relative_to(ROOT).as_posix() for path in sources if token in path.read_text("utf-8")]
        for token in _BANNED_TOKENS
    }

    assert matches == {token: [] for token in _BANNED_TOKENS}
    assert not (ROOT / "web" / "backend" / "evaluation_app.py").exists()
    assert not list((ROOT / "src" / "agens_novel" / "artifacts").glob("*.py"))
