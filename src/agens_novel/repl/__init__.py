"""Interactive REPL -- slash commands, history, and game loop."""

from .commands import (
    EmptyCommand,
    ExitCommand,
    ParsedCommand,
    SlashCommand,
    WriteCommand,
    format_help,
    parse_command,
)

# Lazy import: ``loop`` pulls in ``rich`` (terminal-only) at top-level.
# On Android / Kivy the ``rich`` package is not bundled, so importing it
# eagerly would crash the app.  ``__getattr__`` ensures ``from
# agens_novel.repl import Repl`` still works on desktop while keeping the
# import chain safe for mobile.
def __getattr__(name: str):
    if name == "Repl":
        from .loop import Repl
        return Repl
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Repl",
    "parse_command",
    "format_help",
    "ParsedCommand",
    "SlashCommand",
    "WriteCommand",
    "EmptyCommand",
    "ExitCommand",
]
