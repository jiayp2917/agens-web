"""Slash-command parser for the interactive REPL.

Each input line is classified into one of:
  - ``SlashCommand``: a ``/foo args...`` directive
  - ``EmptyCommand``: blank or whitespace
  - ``ExitCommand``: ``/exit``, ``/quit``, ``:q``, EOF
  - ``WriteCommand``: free-form text (dispatched to Chat Agent)

The parser is intentionally pure: no I/O, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: str


@dataclass(frozen=True)
class WriteCommand:
    text: str


@dataclass(frozen=True)
class EmptyCommand:
    pass


@dataclass(frozen=True)
class ExitCommand:
    pass


ParsedCommand = Union[SlashCommand, WriteCommand, EmptyCommand, ExitCommand]


# ─────────────────────────────────────────────────────────────────────────────
# Slash commands -- single source of truth for help text and dispatch.
# ─────────────────────────────────────────────────────────────────────────────
SLASH_COMMANDS: dict[str, str] = {
    "help":   "Show available slash commands.",
    "exit":   "Exit the REPL.",
    "quit":   "Alias for /exit.",
    "status": "Show the most recent run summary.",
    "clear":  "Clear the screen.",
    "config": "Show current configuration (api_key masked).",
    "history":"Show commands issued in this session.",
    "agents": "List the four agents in the pipeline.",
    "plan":   "Plan stage -- run Planner, print outline, store in session.",
    "write":  "Write stage -- run Writer using session outline.",
    "review": "Review stage -- run Reviewer on session draft.",
    "edit":   "Edit stage -- run Editor on session draft + feedback.",
    "run":    "Run full pipeline automatically (no confirmations).",
    "step":   "Show current pipeline session state and next stage.",
    "reset":  "Reset the pipeline session, clearing all stage outputs.",
}

# Keywords that suggest the user wants to write fiction (not just chat).
_WRITE_INTENT_KEYWORDS = (
    "写一段", "写一篇", "写个", "写作", "帮我写", "生成",
    "小说", "故事", "开头", "结尾", "续写", "片段",
    "write a", "write me", "generate", "story", "novel",
)

# Phrases that contain a write keyword but are NOT actually a writing request.
_WRITE_INTENT_NEGATIVE = (
    "read me a", "tell me a", "what is", "how to", "read me a story",
)


def has_write_intent(text: str) -> bool:
    """Heuristic: does the input look like a writing request?"""
    lower = text.lower()
    if any(neg in lower for neg in _WRITE_INTENT_NEGATIVE):
        return False
    return any(kw in lower for kw in _WRITE_INTENT_KEYWORDS)


def parse_command(line: str) -> ParsedCommand:
    """Classify a single REPL input line."""
    stripped = line.strip()
    if not stripped:
        return EmptyCommand()

    lower = stripped.lower()
    if lower in {"/exit", "/quit", ":q", ":quit"}:
        return ExitCommand()

    if stripped.startswith("/"):
        body = stripped[1:]
        if not body:
            return EmptyCommand()
        parts = body.split(maxsplit=1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return SlashCommand(name=name, args=args)

    return WriteCommand(text=stripped)


def format_help() -> str:
    """Return a formatted help string for the ``/help`` command."""
    lines = ["Available commands:"]
    for name, desc in SLASH_COMMANDS.items():
        lines.append(f"  /{name:<8} {desc}")
    lines.append("")
    lines.append("Anything else is sent to the Chat Agent for free-form conversation.")
    lines.append("Writing requests are detected and a confirmation prompt is shown.")
    return "\n".join(lines)
