"""Slash-command parser for the interactive REPL.

Each input line is classified into one of:
  - ``SlashCommand``: a ``/foo args...`` directive
  - ``EmptyCommand``: blank or whitespace
  - ``ExitCommand``: ``/exit``, ``/quit``, ``:q``, EOF
  - ``WriteCommand``: a free-form writing request

The parser is intentionally pure: no I/O, no side effects. The REPL loop in
``repl.loop`` consumes ``ParsedCommand`` values and dispatches them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


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
# Slash commands — single source of truth for help text and dispatch.
# ─────────────────────────────────────────────────────────────────────────────
SLASH_COMMANDS: dict[str, str] = {
    "help": "Show available slash commands.",
    "exit": "Exit the REPL.",
    "quit": "Alias for /exit.",
    "status": "Show the most recent run summary.",
    "clear": "Clear the screen.",
    "config": "Show current configuration (api_key masked).",
    "history": "Show commands issued in this session.",
    "agents": "List the four agents in the pipeline.",
    "plan": "Plan only — run the Planner, print outline, do not write.",
}


def parse_command(line: str) -> ParsedCommand:
    """Classify a single REPL input line.

    Public so the test suite can exercise it without driving a real REPL.
    """
    stripped = line.strip()
    if not stripped:
        return EmptyCommand()

    # Exit aliases
    lower = stripped.lower()
    if lower in {"/exit", "/quit", ":q", ":quit", "exit", "quit"}:
        return ExitCommand()

    # Slash command
    if stripped.startswith("/"):
        body = stripped[1:]
        if not body:
            return EmptyCommand()
        parts = body.split(maxsplit=1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return SlashCommand(name=name, args=args)

    # Anything else is treated as a free-form writing request.
    return WriteCommand(text=stripped)


def format_help() -> str:
    """Return a formatted help string for the ``/help`` command."""
    lines = ["Available commands:"]
    for name, desc in SLASH_COMMANDS.items():
        lines.append(f"  /{name:<8} {desc}")
    lines.append("")
    lines.append("Anything else is treated as a writing request and dispatched to the multi-agent pipeline.")
    return "\n".join(lines)
