"""Drive the REPL through 7 Chat Agent journeys and report what happens.

Uses StringIO + Console + stubbed run_chat_agent to avoid real LLM calls.
"""

from __future__ import annotations

import io
import os
import sys

# Ensure src is on the path.
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

# Patch the chat agent module before the REPL imports it.
from agens_novel.agents.chat import nodes as chat_nodes  # noqa: E402

# Counter for canned responses.
_canned_responses: list[dict] = []
_canned_idx = {"i": 0}


def _stub_run_chat_agent(user_input: str, chat_history=None) -> dict:
    """Return the next canned response, or a default if exhausted."""
    if _canned_idx["i"] < len(_canned_responses):
        resp = _canned_responses[_canned_idx["i"]]
        _canned_idx["i"] += 1
    else:
        resp = {"output_text": f"[stub] echo: {user_input}", "llm_error": ""}
    return resp


chat_nodes.run_chat_agent = _stub_run_chat_agent

# Also patch the import location used by Repl._handle_chat.
import agens_novel.agents.chat.nodes as _nodes_mod  # noqa: E402
_nodes_mod.run_chat_agent = _stub_run_chat_agent

# Now import the REPL.
from io import StringIO  # noqa: E402

from rich.console import Console  # noqa: E402

from agens_novel.repl import Repl  # noqa: E402


def make_repl(inputs: list[str], *, api_key: str | None = "sk-test-1234567890") -> tuple[Repl, StringIO]:
    """Build a Repl with a StringIO-backed Console and queued inputs."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, legacy_windows=False, soft_wrap=True, width=120)
    it = iter(inputs)

    def input_fn(_prompt: str) -> str:
        return next(it)

    if api_key is not None:
        os.environ["AGNES_API_KEY"] = api_key
    elif "AGNES_API_KEY" in os.environ:
        del os.environ["AGNES_API_KEY"]

    repl = Repl(console=console, input_fn=input_fn)
    return repl, buf


def run_journey(name: str, inputs: list[str], *, api_key: str | None = "sk-test-1234567890",
                canned: list[dict] | None = None) -> dict:
    """Run one REPL journey and return observations."""
    global _canned_responses, _canned_idx
    _canned_responses = list(canned or [])
    _canned_idx = {"i": 0}

    repl, buf = make_repl(inputs, api_key=api_key)
    rc = repl.run()
    out = buf.getvalue()
    return {
        "name": name,
        "rc": rc,
        "output": out,
        "chat_history": list(repl.chat_history),
        "history": list(repl.history),
        "canned_used": _canned_idx["i"],
    }


def find_user_seeing(out: str, expected_substrings: list[str]) -> list[str]:
    """Return list of expected substrings NOT found in output."""
    return [s for s in expected_substrings if s not in out]


def main() -> int:
    results: list[dict] = []

    # ─── Journey 1: "hello" (no write intent) ─────────────────────────────
    r1 = run_journey(
        "J1: 'hello' -> chat",
        inputs=["hello", "/exit"],
        canned=[{"output_text": "Hi there! How can I help?", "llm_error": ""}],
    )
    results.append(r1)

    # ─── Journey 2: "你好" (greeting) ─────────────────────────────────────
    r2 = run_journey(
        "J2: '你好' -> chat",
        inputs=["你好", "/exit"],
        canned=[{"output_text": "你好！有什么我可以帮忙的？", "llm_error": ""}],
    )
    results.append(r2)

    # ─── Journey 3: "what is langgraph?" ──────────────────────────────────
    r3 = run_journey(
        "J3: 'what is langgraph?' -> chat",
        inputs=["what is langgraph?", "/exit"],
        canned=[{"output_text": "LangGraph is a library for building stateful, multi-actor LLM apps.", "llm_error": ""}],
    )
    results.append(r3)

    # ─── Journey 4: several chat turns, history grows ─────────────────────
    r4_inputs = [f"turn-{i}" for i in range(1, 6)]
    r4_inputs.append("/exit")
    r4_canned = [{"output_text": f"reply to {i}", "llm_error": ""} for i in range(1, 6)]
    r4 = run_journey(
        "J4: 5 chat turns -> history grows",
        inputs=r4_inputs,
        canned=r4_canned,
    )
    results.append(r4)

    # ─── Journey 5: 15 turns -> capped at 20 messages (10 turns) ──────────
    r5_inputs = [f"m{i}" for i in range(1, 16)]
    r5_inputs.append("/exit")
    r5_canned = [{"output_text": f"r{i}", "llm_error": ""} for i in range(1, 16)]
    r5 = run_journey(
        "J5: 15 chat turns -> history capped at 20",
        inputs=r5_inputs,
        canned=r5_canned,
    )
    results.append(r5)

    # ─── Journey 6: write intent -> confirm -> cancel ─────────────────────
    # The confirm dialog lists 3 options: "Step-by-step", "Run full", "Cancel, just chat".
    # Choosing option 3 ("3") should fall through to chat mode.
    r6_inputs = ["写一段都市修仙", "3", "/exit"]
    r6 = run_journey(
        "J6: write intent -> confirm -> cancel (option 3) -> chat",
        inputs=r6_inputs,
        canned=[{"output_text": "Sure, let's just chat about it.", "llm_error": ""}],
    )
    results.append(r6)

    # ─── Journey 7: no API key -> error, no crash ─────────────────────────
    r7 = run_journey(
        "J7: chat with no API key -> error, no crash",
        inputs=["hello", "/exit"],
        api_key=None,
        canned=[],  # should never be called
    )
    results.append(r7)

    # ── Print report ──────────────────────────────────────────────────────
    print("=" * 78)
    print("REPL CHAT AGENT JOURNEY REPORT")
    print("=" * 78)

    for r in results:
        print(f"\n--- {r['name']} ---")
        print(f"rc={r['rc']}  canned_used={r['canned_used']}  history_lines={len(r['history'])}  chat_history_msgs={len(r['chat_history'])}")
        print("OUTPUT (last 1500 chars):")
        snippet = r["output"][-1500:] if len(r["output"]) > 1500 else r["output"]
        print(snippet)
        if r["chat_history"]:
            print(f"chat_history roles: {[m.get('role') for m in r['chat_history'][:6]]}{'...' if len(r['chat_history']) > 6 else ''}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
