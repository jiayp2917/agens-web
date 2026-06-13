"""Combat action bar widget — attack/technique/item/defend/flee buttons."""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.metrics import dp

from theme import (
    add_background,
    current_theme,
    themed_button,
    themed_popup,
)


class CombatBar(BoxLayout):
    """Combat action buttons shown during battle.

    Events:
        on_combat_action(action: str, target: str) — user tapped a combat button
    """

    # (label, action_name)
    ACTION_BUTTONS = [
        ("普攻", "attack"),
        ("功法", "technique"),
        ("丹药", "item"),
        ("防御", "defend"),
        ("逃跑", "flee"),
    ]

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(80),
            **kwargs,
        )
        add_background(self, color=theme.surface)

        # Enemy info row.
        self.lbl_enemy = Label(
            text="",
            font_size=dp(12),
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
            color=theme.combat_indicator,
        )
        self.lbl_enemy.bind(width=lambda *a: self.lbl_enemy.setter("text_size")(self.lbl_enemy, (self.lbl_enemy.width, None)))
        self.add_widget(self.lbl_enemy)

        # Action buttons row.
        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            spacing=dp(4),
            padding=[dp(4), 0],
        )
        for label, action in self.ACTION_BUTTONS:
            btn = themed_button(label, font_size=dp(13))
            btn.bind(on_release=lambda instance, a=action: self._on_action(a))
            btn_row.add_widget(btn)

        self.add_widget(btn_row)

        # Combat log row.
        self.lbl_log = Label(
            text="",
            font_size=dp(11),
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
            color=theme.text_secondary,
        )
        self.lbl_log.bind(width=lambda *a: self.lbl_log.setter("text_size")(self.lbl_log, (self.lbl_log.width, None)))
        self.add_widget(self.lbl_log)

        # Callback.
        self.on_combat_action = None
        self._available_techniques: list[dict] = []
        self._available_consumables: list[dict] = []

    def update_combat(self, combat_state: dict | None) -> None:
        """Update display from combat state."""
        if combat_state is None:
            self.lbl_enemy.text = ""
            self.lbl_log.text = ""
            self._available_techniques = []
            self._available_consumables = []
            return

        enemy = combat_state.get("enemy", {})
        name = enemy.get("name", "敌人")
        hp = enemy.get("hp", 0)
        hp_max = enemy.get("hp_max", 1)
        realm = enemy.get("realm", "")
        self.lbl_enemy.text = f"⚔ {name} [{realm}] HP: {hp}/{hp_max}"

        narrative = combat_state.get("narrative", "")
        if narrative:
            self.lbl_log.text = narrative[:60] + ("..." if len(narrative) > 60 else "")
        else:
            self.lbl_log.text = ""

        # Cache available techniques and consumables from player.
        player = combat_state.get("player", {})
        self._available_techniques = [
            t for t in player.get("techniques", [])
            if isinstance(t, dict)
        ]
        self._available_consumables = [
            c for c in player.get("consumables", [])
            if isinstance(c, dict)
        ]

    def _on_action(self, action: str) -> None:
        """Handle a combat action button press."""
        if action == "technique" and self._available_techniques:
            self._show_technique_picker()
            return

        if action == "item" and self._available_consumables:
            self._show_item_picker()
            return

        if self.on_combat_action:
            self.on_combat_action(action, "")

    def _show_technique_picker(self) -> None:
        """Popup to pick a technique."""
        theme = current_theme()
        scroll = ScrollView(size_hint_y=0.8)
        layout = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8), size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))

        for tech in self._available_techniques:
            name = tech.get("name", "?")
            mp_cost = tech.get("mp_cost", 0)
            element = tech.get("element", "")
            btn = themed_button(
                f"{name} (MP:{mp_cost} {element})",
                font_size=dp(12),
                size_hint_y=None,
                height=dp(36),
            )
            btn.bind(on_release=lambda instance, n=name: self._pick_technique(n))
            layout.add_widget(btn)

        scroll.add_widget(layout)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(scroll)
        cancel_btn = themed_button("取消", font_size=dp(12), size_hint_y=None, height=dp(36))
        outer.add_widget(cancel_btn)

        popup = themed_popup(
            "选择功法",
            outer,
            size_hint=(0.8, 0.5),
            auto_dismiss=False,
        )
        cancel_btn.bind(on_release=lambda _: popup.dismiss())
        popup.open()
        self._technique_popup = popup

    def _pick_technique(self, name: str) -> None:
        if hasattr(self, '_technique_popup'):
            self._technique_popup.dismiss()
        if self.on_combat_action:
            self.on_combat_action("technique", name)

    def _show_item_picker(self) -> None:
        """Popup to pick a consumable item."""
        scroll = ScrollView(size_hint_y=0.8)
        layout = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(8), size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))

        for item in self._available_consumables:
            name = item.get("name", "?")
            btn = themed_button(name, font_size=dp(12), size_hint_y=None, height=dp(36))
            btn.bind(on_release=lambda instance, n=name: self._pick_item(n))
            layout.add_widget(btn)

        scroll.add_widget(layout)

        outer = BoxLayout(orientation="vertical")
        outer.add_widget(scroll)
        cancel_btn = themed_button("取消", font_size=dp(12), size_hint_y=None, height=dp(36))
        outer.add_widget(cancel_btn)

        popup = themed_popup(
            "选择丹药",
            outer,
            size_hint=(0.8, 0.4),
            auto_dismiss=False,
        )
        cancel_btn.bind(on_release=lambda _: popup.dismiss())
        popup.open()
        self._item_popup = popup

    def _pick_item(self, name: str) -> None:
        if hasattr(self, '_item_popup'):
            self._item_popup.dismiss()
        if self.on_combat_action:
            self.on_combat_action("item", name)
