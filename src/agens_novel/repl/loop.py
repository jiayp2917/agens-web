"""Interactive REPL loop for the xianxia cultivation simulator.

Delegates game logic to ``GameEngine`` and handles terminal I/O (Rich).

默认模式：自由输入作为游戏行动，由 Narrator + Judge 响应。
输入 /new 开始新游戏，/status 查看角色状态。
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from .. import paths
from ..engine.game_engine import GameEngine
from ..settings import Settings
from .commands import (
    EmptyCommand,
    ExitCommand,
    SlashCommand,
    WriteCommand,
    format_help,
    parse_command,
)
from .game_view import render_status_panel

log = logging.getLogger(__name__)

PROMPT = "修仙> "


class Repl:
    """Stateful REPL session for the xianxia cultivation simulator.

    Delegates all game logic to ``GameEngine``. This class only handles
    terminal I/O (Rich console, user input, rendering).
    """

    def __init__(
        self,
        console: Console | None = None,
        input_fn: Callable[[str], str] | None = None,
        runner: Callable[[str, str], dict] | None = None,
    ) -> None:
        self.console = console or Console(legacy_windows=True, soft_wrap=True)
        self.input_fn = input_fn or (lambda prompt: Prompt.ask(prompt, console=self.console))
        # runner is kept for API compatibility but not used.
        self.runner = runner
        self.history: list[str] = []

        # Game engine — owns all game logic and state.
        self.engine = GameEngine()
        self.game_session = self.engine.game_session  # convenience alias

        # Register Rich-rendering callbacks.
        self.engine.on_narrative = self._cb_narrative
        self.engine.on_status_bar = self._cb_status_bar
        self.engine.on_error = self._cb_error
        self.engine.on_info = self._cb_info
        self.engine.on_game_over = self._cb_game_over
        self.engine.on_character_created = self._cb_character_created
        self.engine.on_loading = self._cb_loading

    # ─────────────────────────────────────────────────────────────────────────
    # Engine callbacks → Rich rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _cb_narrative(self, text: str, turn: int) -> None:
        if turn > 0:
            self.console.print(Panel(text, title=f"第 {turn} 回合", border_style="cyan"))
        else:
            self.console.print(Panel(text, title="天道初开", border_style="cyan"))

    def _cb_status_bar(self, text: str) -> None:
        self.console.print(text)

    def _cb_error(self, msg: str) -> None:
        self.console.print(f"[red]{msg}[/red]")

    def _cb_info(self, msg: str) -> None:
        self.console.print(f"[dim]{msg}[/dim]")

    def _cb_game_over(self, reason: str) -> None:
        self.console.print(Panel(reason, title="[red]GAME OVER[/red]", border_style="red"))

    def _cb_character_created(self, session: object) -> None:
        self.console.print(render_status_panel(self.game_session))

    def _cb_loading(self, msg: str) -> None:
        # In the REPL, loading messages are shown via console.status() in the
        # calling methods (cmd_new, _handle_action). This callback is a no-op
        # here but used by the mobile UI.
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # 确认弹窗（编号选择）
    # ─────────────────────────────────────────────────────────────────────────
    def _confirm(self, prompt: str, options: list[str]) -> int:
        """Show a numbered choice prompt. Returns 0-based index."""
        self.console.print(f"\n  {prompt}")
        for i, opt in enumerate(options, 1):
            marker = "（推荐）" if i == 1 else ""
            self.console.print(f"    {i}. {opt}{marker}")
        while True:
            choice = self.input_fn("  select> ").strip()
            if not choice:
                return 0  # default to first option
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return idx
            except ValueError:
                pass
            self.console.print("  [yellow]无效选择，请重试。[/yellow]")

    # ─────────────────────────────────────────────────────────────────────────
    # Slash-command handlers
    # ─────────────────────────────────────────────────────────────────────────
    def cmd_help(self, _args: str) -> None:
        self.console.print(format_help())

    def cmd_config(self, _args: str) -> None:
        s = Settings()
        for k, v in s.public_summary().items():
            self.console.print(f"  {k}: {v}")

    def cmd_history(self, _args: str) -> None:
        if not self.history:
            self.console.print("[dim]（暂无历史记录）[/dim]")
            return
        for i, line in enumerate(self.history, 1):
            shown = line if len(line) <= 80 else line[:77] + "..."
            self.console.print(f"  {i:>3}  {shown}")

    def cmd_clear(self, _args: str) -> None:
        self.console.clear()

    def cmd_status(self, _args: str) -> None:
        if not self.game_session.game_started:
            self.console.print("[dim]（尚未开始游戏，输入 /new 开始。）[/dim]")
            return
        self.console.print(render_status_panel(self.game_session))

    def cmd_inv(self, _args: str) -> None:
        if not self.game_session.game_started:
            self.console.print("[dim]（尚未开始游戏。）[/dim]")
            return
        from .game_view import render_inventory_table
        self.console.print(render_inventory_table(self.game_session))

    def cmd_skills(self, _args: str) -> None:
        if not self.game_session.game_started:
            self.console.print("[dim]（尚未开始游戏。）[/dim]")
            return
        from .game_view import render_skills_table
        self.console.print(render_skills_table(self.game_session))

    def cmd_map(self, _args: str) -> None:
        if not self.game_session.game_started:
            self.console.print("[dim]（尚未开始游戏。）[/dim]")
            return
        locs = self.game_session.discovered_locations
        if not locs:
            self.console.print("[dim]（尚未探索任何地点。）[/dim]")
            return
        for loc in locs:
            current = " [cyan]<-- 当前[/cyan]" if loc == self.game_session.location else ""
            self.console.print(f"  · {loc}{current}")

    def cmd_quest(self, _args: str) -> None:
        if not self.game_session.game_started:
            self.console.print("[dim]（尚未开始游戏。）[/dim]")
            return
        quests = self.game_session.active_quests
        if not quests:
            self.console.print("[dim]（当前没有任务。）[/dim]")
            return
        for q in quests:
            status = q.get("status", "?")
            name = q.get("name", "?")
            desc = q.get("description", "")
            icon = "[green]●[/green]" if status == "active" else "[dim]○[/dim]"
            self.console.print(f"  {icon} {name}: {desc}")

    def cmd_log(self, _args: str) -> None:
        history = self.game_session.turn_history
        if not history:
            self.console.print("[dim]（暂无回合记录。）[/dim]")
            return
        for entry in history[-5:]:
            turn = entry.get("turn", "?")
            narrative = entry.get("narrative", "")
            if len(narrative) > 150:
                narrative = narrative[:147] + "..."
            self.console.print(Panel(
                narrative or "（无叙事）",
                title=f"第 {turn} 回合",
                border_style="dim",
            ))

    def cmd_reset(self, _args: str) -> None:
        self.engine.reset()

    def cmd_breakthrough(self, _args: str) -> None:
        """Attempt a realm breakthrough."""
        if not self.game_session.game_started:
            self.console.print("[yellow]请先输入 /new 开始游戏。[/yellow]")
            return
        with self.console.status("[bold green]突破中..."):
            self.engine.attempt_breakthrough()

    def cmd_combat_action(self, action: str, args: str) -> None:
        """Execute a combat action via the engine."""
        if not self.game_session.game_started:
            self.console.print("[yellow]请先输入 /new 开始游戏。[/yellow]")
            return
        if self.game_session.combat is None:
            self.console.print("[yellow]当前不在战斗中。[/yellow]")
            return
        target = args.strip()
        with self.console.status(f"[bold green]{action}..."):
            self.engine.handle_combat_action(action, target)

    def cmd_attack(self, args: str) -> None:
        self.cmd_combat_action("attack", args)

    def cmd_technique(self, args: str) -> None:
        if not args.strip():
            # Show available techniques.
            techniques = self.game_session.techniques
            if techniques:
                self.console.print("[dim]可用功法:[/dim]")
                for t in techniques:
                    name = t.get("name", "?") if isinstance(t, dict) else str(t)
                    self.console.print(f"  · {name}")
                self.console.print("[dim]用法: /technique <功法名>[/dim]")
            else:
                self.console.print("[yellow]没有已学功法。[/yellow]")
            return
        self.cmd_combat_action("technique", args)

    def cmd_item(self, args: str) -> None:
        if not args.strip():
            # Show available consumables.
            items = [
                i for i in self.game_session.inventory
                if isinstance(i, dict) and i.get("type") == "丹药"
            ]
            if items:
                self.console.print("[dim]可用丹药:[/dim]")
                for i in items:
                    name = i.get("name", "?")
                    self.console.print(f"  · {name}")
                self.console.print("[dim]用法: /item <丹药名>[/dim]")
            else:
                self.console.print("[yellow]没有可用丹药。[/yellow]")
            return
        self.cmd_combat_action("item", args)

    def cmd_defend(self, args: str) -> None:
        self.cmd_combat_action("defend", args)

    def cmd_flee(self, args: str) -> None:
        self.cmd_combat_action("flee", args)

    def cmd_new(self, args: str) -> None:
        """Start a new game via the World Builder agent."""
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY 未设置。请先运行 agens-novel init。[/red]")
            return

        # Get character concept.
        concept = args.strip()
        if not concept:
            concept = self.input_fn("  请输入角色设定（如: 我叫许满，火灵根，出身农家）> ").strip()
        if not concept:
            self.console.print("[yellow]已取消。[/yellow]")
            return

        with self.console.status("[bold green]天道初开，世界生成中..."):
            self.engine.new_game(concept)

    def cmd_save(self, args: str) -> None:
        name = args.strip() or "autosave"
        from .save_manager import save_game
        if not self.game_session.game_started:
            self.console.print("[yellow]没有进行中的游戏。[/yellow]")
            return
        try:
            save_game(self.game_session, name)
            self.console.print(f"[dim]进度已保存: {name}[/dim]")
        except Exception as e:
            self.console.print(f"[red]保存失败:[/red] {e}")

    def cmd_load(self, args: str) -> None:
        name = args.strip() or "autosave"
        from .save_manager import load_game
        try:
            loaded = load_game(name)
            self.engine.game_session = loaded
            self.game_session = self.engine.game_session
            self.console.print(f"[dim]已加载存档: {name}[/dim]")
            self.console.print(render_status_panel(self.game_session))
        except FileNotFoundError as e:
            self.console.print(f"[yellow]{e}[/yellow]")
        except Exception as e:
            self.console.print(f"[red]加载失败:[/red] {e}")

    def cmd_expand(self, args: str) -> None:
        """Request world expansion from the World Builder."""
        if not self.game_session.game_started:
            self.console.print("[yellow]请先输入 /new 开始游戏。[/yellow]")
            return
        if not _has_api_key():
            self.console.print("[red]AGNES_API_KEY 未设置。[/red]")
            return

        gen_type = args.strip() or "new_region"
        if gen_type not in ("new_region", "new_encounter", "new_technique"):
            gen_type = "new_region"

        with self.console.status("[bold green]世界扩展中..."):
            self.engine.expand(gen_type)

    def cmd_exit(self, _args: str) -> bool:
        # Auto-save before exit.
        if self.game_session.game_started:
            try:
                from .save_manager import save_game
                save_game(self.game_session, "autosave")
            except Exception:
                pass
        self.console.print("[dim]道阻且长，行则将至。再见。[/dim]")
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Game action handler
    # ─────────────────────────────────────────────────────────────────────────
    def _handle_action(self, text: str) -> None:
        """Process a player action through the engine."""
        with self.console.status("[bold green]天道运转中..."):
            self.engine.handle_action(text)

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────
    def run(self) -> int:
        self.console.print(Panel(
            "[bold]文字修仙[/bold] - AI 驱动的修仙世界模拟器\n"
            "输入行动探索世界，或用命令管理游戏。\n"
            "输入 /new 开始新游戏，/help 查看所有命令。",
            border_style="cyan",
        ))
        while True:
            try:
                raw = self.input_fn(PROMPT)
            except (EOFError, KeyboardInterrupt, StopIteration):
                self.console.print()
                return 0

            cmd = parse_command(raw)
            if isinstance(cmd, EmptyCommand):
                continue
            if isinstance(cmd, ExitCommand):
                self.cmd_exit("")
                return 0
            if isinstance(cmd, SlashCommand):
                self.history.append(f"/{cmd.name} {cmd.args}".rstrip())
                if self._dispatch_slash(cmd):
                    return 0
                continue
            if isinstance(cmd, WriteCommand):
                self.history.append(cmd.text)
                self._handle_action(cmd.text)
                continue
        return 0

    def _dispatch_slash(self, cmd: SlashCommand) -> bool:
        """Return True if REPL should exit."""
        name = cmd.name
        if name in {"exit", "quit"}:
            return self.cmd_exit(cmd.args)
        handler = {
            "help": self.cmd_help,
            "config": self.cmd_config,
            "history": self.cmd_history,
            "clear": self.cmd_clear,
            "status": self.cmd_status,
            "inv": self.cmd_inv,
            "skills": self.cmd_skills,
            "map": self.cmd_map,
            "quest": self.cmd_quest,
            "log": self.cmd_log,
            "reset": self.cmd_reset,
            "new": self.cmd_new,
            "save": self.cmd_save,
            "load": self.cmd_load,
            "expand": self.cmd_expand,
            "breakthrough": self.cmd_breakthrough,
            "attack": self.cmd_attack,
            "technique": self.cmd_technique,
            "item": self.cmd_item,
            "defend": self.cmd_defend,
            "flee": self.cmd_flee,
        }.get(name)
        if handler is None:
            self.console.print(f"[red]未知命令:[/red] /{name} （输入 /help 查看帮助）")
            return False
        handler(cmd.args)
        return False


def _has_api_key() -> bool:
    """Check if an API key is available (env var or built-in fallback)."""
    return bool(os.environ.get("AGNES_API_KEY", "")) or True  # built-in key fallback
