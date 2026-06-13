"""Main game screen — classic game panel layout with combat + streaming support.

Layout:
  ┌─────────────────────────────┐
  │ Status Bar (HP/MP/Realm)    │
  ├─────────────────────────────┤
  │ Realm Card (optional)       │
  ├─────────────────────────────┤
  │                             │
  │ Scrollable Narrative Area   │
  │                             │
  ├─────────────────────────────┤
  │ Combat Status (during combat)│
  ├─────────────────────────────┤
  │ Utility Row + Text Input    │
  └─────────────────────────────┘
  + Loading Overlay (on top)
"""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from service.engine_adapter import EngineAdapter
from theme import add_background, current_theme, themed_button, themed_popup
from widgets.action_bar import GameActionBar
from widgets.combat_bar import CombatBar
from widgets.loading_overlay import LoadingOverlay
from widgets.narrative_view import NarrativeView
from widgets.status_bar import StatusBar


class GameScreen(Screen):
    """Main game screen with panel layout, combat, and streaming support."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        theme = current_theme()
        add_background(self, color=theme.bg)

        self.adapter = EngineAdapter()

        # Register UI callbacks from the adapter.
        self.adapter.on_narrative = self._on_narrative
        self.adapter.on_status_bar = self._on_status_bar
        self.adapter.on_error = self._on_error
        self.adapter.on_info = self._on_info
        self.adapter.on_game_over = self._on_game_over
        self.adapter.on_character_created = self._on_character_created
        self.adapter.on_loading = self._on_loading
        self.adapter.on_stream_chunk = self._on_stream_chunk
        self.adapter.on_combat_update = self._on_combat_update
        self.adapter.on_finale = self._on_finale
        self._save_popup = None
        self._load_popup = None

        # Build layout.
        self.root = FloatLayout()
        self.layout = BoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
        )

        # Top: status bar (includes breakthrough button — merged RealmCard)
        self.status_bar = StatusBar()
        self.status_bar.on_breakthrough = self._on_breakthrough
        self.layout.add_widget(self.status_bar)

        # Middle: narrative view
        self.narrative_view = NarrativeView()
        self.narrative_view.on_choice = self._on_choice
        self.layout.add_widget(self.narrative_view)

        # Combat bar (hidden by default).
        self.combat_bar = CombatBar()
        self.combat_bar.height = 0
        self.combat_bar.size_hint_y = None
        self.combat_bar.opacity = 0
        self.combat_bar.disabled = True
        self.layout.add_widget(self.combat_bar)

        # Bottom: action bar
        self.action_bar = GameActionBar()
        self.action_bar.on_action = self._on_user_action
        self.action_bar.on_command = self._on_user_command
        self.layout.add_widget(self.action_bar)

        self.root.add_widget(self.layout)

        # Loading overlay. It must be the last child so it covers the whole screen.
        self.loading_overlay = LoadingOverlay()
        self.loading_overlay.hide()
        self.root.add_widget(self.loading_overlay)
        self.add_widget(self.root)

    def on_enter(self, *args):
        """Called when this screen becomes active."""
        self._refresh_choices_ui()
        self.status_bar.update(self.adapter.game_session)

    # ─── Adapter callbacks (called on Kivy main thread) ────────────────

    def _on_narrative(self, text: str, turn: int) -> None:
        self.loading_overlay.hide()
        self.narrative_view.finalize_stream()
        self.narrative_view.add_narrative(text, turn)
        self._refresh_choices_ui()
        self.status_bar.update(self.adapter.game_session)

    def _on_status_bar(self, text: str) -> None:
        self.status_bar.update(self.adapter.game_session)

    def _on_error(self, msg: str) -> None:
        self.loading_overlay.hide()
        self.narrative_view.add_info(f"[错误] {msg}")

    def _on_info(self, msg: str) -> None:
        self.loading_overlay.hide()
        self.narrative_view.add_info(msg)
        self.status_bar.update(self.adapter.game_session)

    def _on_game_over(self, reason: str) -> None:
        self.loading_overlay.hide()
        self._hide_combat_bar()
        self.action_bar.set_combat_mode(False)
        if self.manager:
            death = self.manager.get_screen("death")
            death.set_reason(reason)
            self.manager.current = "death"
        self.status_bar.update(self.adapter.game_session)

    def _on_character_created(self, session) -> None:
        self.loading_overlay.hide()
        self.narrative_view.add_info("角色创建成功！输入行动开始游戏。")
        self.status_bar.update(session)
        self._refresh_choices_ui()

    def _on_loading(self, msg: str) -> None:
        self.loading_overlay.show(msg)

    def _on_stream_chunk(self, text: str) -> None:
        """Receive streaming text chunk from LLM."""
        self.narrative_view.append_chunk(text)

    def _on_combat_update(self, combat_state: dict | None) -> None:
        """Handle combat state changes."""
        if combat_state is None:
            self._hide_combat_bar()
            self.action_bar.set_combat_mode(False)
        else:
            self._show_combat_bar()
            self.combat_bar.update_combat(combat_state)
            self.action_bar.set_combat_mode(True)
            self.status_bar.update(self.adapter.game_session)

    # ─── Combat bar management ────────────────────────────────────────

    def _show_combat_bar(self) -> None:
        """Show the combat bar."""
        self.combat_bar.height = dp(46)
        self.combat_bar.size_hint_y = None
        self.combat_bar.opacity = 1
        self.combat_bar.disabled = False

    def _hide_combat_bar(self) -> None:
        """Hide the combat bar."""
        self.combat_bar.height = 0
        self.combat_bar.size_hint_y = None
        self.combat_bar.opacity = 0
        self.combat_bar.disabled = True
        self.combat_bar.update_combat(None)

    # ─── User input handlers ───────────────────────────────────────────

    def _on_user_action(self, text: str) -> None:
        """User submitted free-text action.

        Supports slash-command recognition: if the input starts with '/',
        it is treated as a command rather than a game action.
        """
        stripped = text.strip()

        # Slash-command routing.
        if stripped.startswith("/"):
            cmd = self._parse_slash_command(stripped)
            if cmd is not None:
                return
        if not stripped:
            return

        # Normal free-text action.
        self.narrative_view.clear_choices()
        self.narrative_view.add_info(f"> {stripped}")
        self.adapter.handle_action(stripped)

    def _on_choice(self, choice: str) -> None:
        """Submit a suggested choice as the player's action."""
        self._on_user_action(choice)

    # ─── Slash command parser ────────────────────────────────────────────

    _SLASH_COMMANDS: dict[str, str] = {
        "/new": "new", "/新游戏": "new",
        "/save": "save", "/存档": "save",
        "/load": "load", "/读档": "load",
        "/status": "status", "/状态": "status",
        "/inv": "inv", "/背包": "inv",
        "/skills": "skills", "/功法": "skills",
        "/map": "map", "/地图": "map",
        "/quest": "quest", "/任务": "quest",
        "/breakthrough": "breakthrough", "/突破": "breakthrough",
        "/equipment": "equipment", "/装备": "equipment",
        "/settings": "_nav_settings", "/设置": "_nav_settings",
        "/home": "_nav_home", "/主页": "_nav_home",
        "/saves": "_nav_saves", "/存档管理": "_nav_saves",
        "/attack": "_combat_attack", "/攻击": "_combat_attack",
        "/defend": "_combat_defend", "/防御": "_combat_defend",
        "/flee": "_combat_flee", "/逃跑": "_combat_flee",
        "/technique": "_combat_technique", "/功法攻击": "_combat_technique",
        "/item": "_combat_item", "/使用丹药": "_combat_item",
    }

    def _parse_slash_command(self, text: str) -> str | None:
        """Parse a slash command and dispatch it. Returns the cmd name or None."""
        parts = text.split(None, 1)
        key = parts[0].lower()

        cmd = self._SLASH_COMMANDS.get(key)
        if cmd is None:
            # Unknown command — let the caller submit it once as normal text.
            return None

        if cmd.startswith("_combat_"):
            action = cmd.removeprefix("_combat_")
            target = parts[1].strip() if len(parts) > 1 else ""
            self.adapter.handle_combat_action(action, target)
            return cmd

        # Navigation commands.
        if cmd == "_nav_settings":
            if self.manager:
                self.manager.current = "home"
                self.manager.get_screen("home")._show_settings_popup()
            return cmd
        if cmd == "_nav_home":
            if self.manager:
                self.manager.current = "home"
            return cmd
        if cmd == "_nav_saves":
            if self.manager:
                self.manager.current = "home"
                self.manager.get_screen("home")._show_load_popup()
            return cmd

        # Delegate to the existing command handler.
        self._on_user_command(cmd)
        return cmd

    def _on_user_command(self, cmd: str) -> None:
        """User tapped a quick-action button."""
        if cmd == "new":
            if self.manager:
                self.manager.current = "character_create"
        elif cmd == "restart":
            if self.manager:
                self.manager.current = "character_create"
        elif cmd == "settings":
            if self.manager:
                self.manager.current = "home"
                self.manager.get_screen("home")._show_settings_popup()
        elif cmd == "status":
            text = f"{self.adapter.get_status()}\n\n【功法】\n{self.adapter.get_skills()}"
            self._show_text_popup("角色状态", text)
        elif cmd == "inv":
            self._show_text_popup("背包", self.adapter.get_inventory())
        elif cmd == "skills":
            self._show_text_popup("功法", self.adapter.get_skills())
        elif cmd == "map":
            self._show_text_popup("地图", self.adapter.get_map())
        elif cmd == "quest":
            self._show_text_popup("任务", self.adapter.get_quests())
        elif cmd == "save":
            self._show_save_slot_dialog()
        elif cmd == "load":
            self._show_load_slot_dialog()
        elif cmd == "breakthrough":
            self._on_breakthrough()
        elif cmd == "equipment":
            self._show_text_popup("装备", self.adapter.get_equipment_info())
        elif cmd == "home":
            if self.manager:
                self.manager.current = "home"

    def _refresh_choices_ui(self) -> None:
        """Render the single A/B/C choices mode."""
        session = self.adapter.game_session
        self.action_bar.apply_choices_mode()
        self.narrative_view.render_choices(getattr(session, "last_choices", []) or [])

    def _on_finale(self, reason: str) -> None:
        """Handle ascension finale (飞升) — different from death."""
        self.loading_overlay.hide()
        self._hide_combat_bar()
        self.action_bar.set_combat_mode(False)
        if self.manager:
            death = self.manager.get_screen("death")
            death.set_reason(reason)
            death.is_finale = True
            self.manager.current = "death"

    def _on_breakthrough(self) -> None:
        """User tapped breakthrough button."""
        self.adapter.attempt_breakthrough()

    def _show_text_popup(self, title: str, text: str) -> None:
        """Show a scrollable text popup."""
        theme = current_theme()
        scroll = ScrollView()
        lbl = Label(
            text=text,
            font_size=dp(13),
            halign="left",
            valign="top",
            size_hint_y=None,
            color=theme.text,
        )
        lbl.bind(width=lambda *a: lbl.setter("text_size")(lbl, (lbl.width, None)))
        lbl.bind(texture_size=lbl.setter("size"))
        scroll.add_widget(lbl)

        close_btn = themed_button("关闭", font_size=dp(13), size_hint_y=None, height=dp(36))
        box = BoxLayout(orientation="vertical")
        box.add_widget(scroll)
        box.add_widget(close_btn)
        popup = themed_popup(title, box, size_hint=(0.85, 0.6))
        close_btn.bind(on_release=lambda _: popup.dismiss())
        popup.open()

    # ─── Save/Load slot selection popups ────────────────────────────────

    def _show_save_slot_dialog(self) -> None:
        """Show a popup for choosing which slot to save into."""
        if self._save_popup:
            self._save_popup.dismiss()
        content = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        from agens_novel.repl.save_manager import get_manual_save_slots
        slots = get_manual_save_slots()

        for slot_info in slots:
            slot_name = slot_info["name"]
            if slot_info["occupied"]:
                label = f"档位{slot_info['slot']}: {slot_info['char_name']} ({slot_info['realm']}) T{slot_info['turn_count']}"
            else:
                label = f"档位{slot_info['slot']}: 空"

            btn = themed_button(label, font_size=dp(12), size_hint_y=None, height=dp(36))
            btn.bind(on_release=lambda instance, sn=slot_name: self._do_save_slot(sn))
            content.add_widget(btn)

        # Quick save to "manual" slot.
        quick_btn = themed_button("快速存档 (覆盖上次)", font_size=dp(12), size_hint_y=None, height=dp(36))
        quick_btn.bind(on_release=lambda _: self._do_save_slot("manual"))
        content.add_widget(quick_btn)

        cancel_btn = themed_button("取消", font_size=dp(12), size_hint_y=None, height=dp(36))
        popup = themed_popup("选择存档位置", content, size_hint=(0.85, 0.65), auto_dismiss=False)
        cancel_btn.bind(on_release=lambda _: popup.dismiss())
        content.add_widget(cancel_btn)
        self._save_popup = popup
        popup.bind(on_dismiss=lambda *_: setattr(self, "_save_popup", None))
        popup.open()

    def _do_save_slot(self, slot_name: str) -> None:
        """Execute save to the given slot and close parent popup."""
        self.adapter.save(slot_name)
        if self._save_popup:
            self._save_popup.dismiss()

    def _show_load_slot_dialog(self) -> None:
        """Show a popup for choosing which slot to load from."""
        if self._load_popup:
            self._load_popup.dismiss()
        theme = current_theme()
        content = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        from agens_novel.repl.save_manager import AUTOSAVE_NAME, get_manual_save_slots, list_saves

        # Auto-save entry.
        saves = list_saves()
        autosave = next((s for s in saves if s["name"] == AUTOSAVE_NAME and not s.get("error")), None)
        if autosave:
            label = f"自动存档: {autosave['char_name']} ({autosave['realm']}) T{autosave['turn_count']}"
            btn = themed_button(label, font_size=dp(12), size_hint_y=None, height=dp(36))
            btn.bind(on_release=lambda instance: self._do_load_slot(AUTOSAVE_NAME))
            content.add_widget(btn)

        # Manual slots.
        slots = get_manual_save_slots()
        for slot_info in slots:
            if slot_info["occupied"]:
                label = f"档位{slot_info['slot']}: {slot_info['char_name']} ({slot_info['realm']}) T{slot_info['turn_count']}"
                btn = themed_button(label, font_size=dp(12), size_hint_y=None, height=dp(36))
                btn.bind(on_release=lambda instance, sn=slot_info["name"]: self._do_load_slot(sn))
                content.add_widget(btn)

        # Quick load.
        quick_btn = themed_button("快速读档 (上次存档)", font_size=dp(12), size_hint_y=None, height=dp(36))
        quick_btn.bind(on_release=lambda _: self._do_load_slot("manual"))
        content.add_widget(quick_btn)

        if not autosave and not any(s["occupied"] for s in slots):
            content.add_widget(Label(text="没有可用的存档", font_size=dp(13), color=theme.text_secondary))

        cancel_btn = themed_button("取消", font_size=dp(12), size_hint_y=None, height=dp(36))
        popup = themed_popup("选择读档", content, size_hint=(0.85, 0.65), auto_dismiss=False)
        cancel_btn.bind(on_release=lambda _: popup.dismiss())
        content.add_widget(cancel_btn)
        self._load_popup = popup
        popup.bind(on_dismiss=lambda *_: setattr(self, "_load_popup", None))
        popup.open()

    def _do_load_slot(self, slot_name: str) -> None:
        """Execute load from the given slot and close parent popup."""
        if not self._save_exists(slot_name):
            self.adapter.load(slot_name)
            return
        self.narrative_view.clear()
        self._hide_combat_bar()
        self.action_bar.set_combat_mode(False)
        self.adapter.load(slot_name)
        self.status_bar.update(self.adapter.game_session)
        if self._load_popup:
            self._load_popup.dismiss()

    def _save_exists(self, slot_name: str) -> bool:
        """Return True when a concrete save slot exists."""
        from agens_novel.repl.save_manager import list_saves

        return any(
            item.get("name") == slot_name and not item.get("error")
            for item in list_saves()
        )
