"""Slash-command parser for the interactive REPL.

Each input line is classified into one of:
  - ``SlashCommand``: a ``/foo args...`` directive
  - ``EmptyCommand``: blank or whitespace
  - ``ExitCommand``: ``/exit``, ``/quit``, ``:q``, EOF
  - ``WriteCommand``: free-form text (dispatched as a game action)

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
    "help":   "显示所有命令。",
    "exit":   "退出游戏。",
    "quit":   "同 /exit。",
    "new":    "开始新游戏 -- 创建角色，进入修仙世界。",
    "save":   "保存当前进度。（/save <名称>，默认 autosave）",
    "load":   "加载存档。（/load <名称>，默认 autosave）",
    "status": "显示角色状态（境界、HP、灵根等）。",
    "inv":    "显示背包物品。",
    "skills": "显示已学功法/术法。",
    "map":    "显示已探索的地点。",
    "quest":  "显示当前任务。",
    "log":    "显示最近的回合记录。",
    "expand": "请求世界生成 -- 新区域、新NPC、新功法。",
    "clear":  "清屏。",
    "config": "显示当前配置（api_key 已脱敏）。",
    "history":"显示本次会话的命令历史。",
    "reset":  "重置当前游戏，重新开始。",
    "breakthrough": "尝试突破到下一个境界。",
    "attack": "战斗：普通攻击。",
    "technique": "战斗：使用功法。（/technique <功法名>）",
    "item":   "战斗：使用丹药。（/item <丹药名>）",
    "defend": "战斗：防御。",
    "flee":   "战斗：逃跑。",
}


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
    lines = ["可用命令："]
    for name, desc in SLASH_COMMANDS.items():
        lines.append(f"  /{name:<8} {desc}")
    lines.append("")
    lines.append("其他输入将作为游戏行动，由天道叙述引擎响应。")
    lines.append("输入 /new 开始新游戏。")
    return "\n".join(lines)
