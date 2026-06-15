"""Compact combat status widget for typed-input gameplay."""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp

from theme import (
    add_paper_background,
    current_theme,
)


class CombatBar(BoxLayout):
    """Combat state shown during battle.

    The player still acts through the text input. This widget only summarizes
    enemy HP and recent combat narration so battle state is visible without
    replacing typed gameplay with buttons.
    """

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(46),
            **kwargs,
        )
        add_paper_background(self, color=(1.0, 0.973, 0.941, 0.84))

        # Enemy info row.
        self.lbl_enemy = Label(
            text="",
            font_size=dp(12),
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
            color=theme.combat_indicator,
        )
        self.lbl_enemy.bind(width=lambda *a: self.lbl_enemy.setter("text_size")(self.lbl_enemy, (self.lbl_enemy.width, None)))
        self.add_widget(self.lbl_enemy)

        # Combat log row.
        self.lbl_log = Label(
            text="",
            font_size=dp(11),
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
            color=theme.text_secondary,
        )
        self.lbl_log.bind(width=lambda *a: self.lbl_log.setter("text_size")(self.lbl_log, (self.lbl_log.width, None)))
        self.add_widget(self.lbl_log)

    def update_combat(self, combat_state: dict | None) -> None:
        """Update display from combat state."""
        if combat_state is None:
            self.lbl_enemy.text = ""
            self.lbl_log.text = ""
            return

        enemy = combat_state.get("enemy", {})
        name = enemy.get("name", "敌人")
        hp = enemy.get("hp", 0)
        hp_max = enemy.get("hp_max", 1)
        realm = enemy.get("realm", "")
        self.lbl_enemy.text = f"战斗中：{name} [{realm}] HP {hp}/{hp_max}"

        narrative = combat_state.get("narrative", "")
        if narrative:
            self.lbl_log.text = narrative[:48] + ("..." if len(narrative) > 48 else "")
        else:
            self.lbl_log.text = "输入攻击、防御、逃跑、施展功法或使用丹药。"
