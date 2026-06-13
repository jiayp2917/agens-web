"""Combat screen -- dedicated battle interface.

Can be used as an alternative to the inline combat bar on GameScreen.
Shows full combat state with enemy info, HP bars, and action buttons.
"""

from __future__ import annotations

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp

from widgets.combat_bar import CombatBar
from service.engine_adapter import EngineAdapter
from theme import ThemedProgressBar, add_background, current_theme, themed_button


class CombatScreen(Screen):
    """Full-screen combat interface."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        theme = current_theme()
        add_background(self, color=theme.bg)

        self.layout = BoxLayout(
            orientation="vertical",
            padding=[dp(8), dp(8)],
            spacing=dp(6),
        )

        # Title.
        self.layout.add_widget(Label(
            text="[b]⚔ 战斗[/b]",
            markup=True,
            font_size=dp(18),
            size_hint_y=None,
            height=dp(32),
            color=theme.text,
        ))

        # Enemy info.
        self.enemy_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(2),
        )
        self.lbl_enemy_name = Label(
            text="敌人", font_size=dp(14), size_hint_y=None, height=dp(20),
            color=theme.combat_indicator,
        )
        self.enemy_hp_bar = ThemedProgressBar(bar_color=theme.hp_low, max=100, value=100, size_hint_y=None, height=dp(16))
        self.lbl_enemy_hp = Label(text="HP: 100/100", font_size=dp(11), size_hint_y=None, height=dp(16), color=theme.text_secondary)
        self.lbl_enemy_realm = Label(text="境界: 练气", font_size=dp(11), size_hint_y=None, height=dp(16), color=theme.text_hint)
        self.enemy_box.add_widget(self.lbl_enemy_name)
        self.enemy_box.add_widget(self.enemy_hp_bar)
        self.enemy_box.add_widget(self.lbl_enemy_hp)
        self.enemy_box.add_widget(self.lbl_enemy_realm)
        self.layout.add_widget(self.enemy_box)

        # VS divider.
        self.layout.add_widget(Label(
            text="VS",
            font_size=dp(16),
            size_hint_y=None,
            height=dp(24),
            color=theme.accent,
        ))

        # Player info.
        self.player_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(72),
            spacing=dp(2),
        )
        self.lbl_player_name = Label(text="你", font_size=dp(14), size_hint_y=None, height=dp(20), color=theme.primary)
        self.player_hp_bar = ThemedProgressBar(bar_color=theme.hp_high, max=100, value=100, size_hint_y=None, height=dp(16))
        self.lbl_player_hp = Label(text="HP: 100/100", font_size=dp(11), size_hint_y=None, height=dp(16), color=theme.text_secondary)
        self.lbl_player_mp = Label(text="MP: 50/50", font_size=dp(11), size_hint_y=None, height=dp(16), color=theme.text_secondary)
        self.player_box.add_widget(self.lbl_player_name)
        self.player_box.add_widget(self.player_hp_bar)
        self.player_box.add_widget(self.lbl_player_hp)
        self.player_box.add_widget(self.lbl_player_mp)
        self.layout.add_widget(self.player_box)

        # Combat narrative area.
        self.combat_log = ScrollView(size_hint_y=0.3)
        self.lbl_narrative = Label(
            text="",
            font_size=dp(12),
            halign="left",
            valign="top",
            size_hint_y=None,
            color=theme.text,
        )
        self.lbl_narrative.bind(
            width=lambda *a: self.lbl_narrative.setter("text_size")(self.lbl_narrative, (self.lbl_narrative.width, None)),
            texture_size=self.lbl_narrative.setter("size"),
        )
        self.combat_log.add_widget(self.lbl_narrative)
        self.layout.add_widget(self.combat_log)

        # Combat action bar.
        self.combat_bar = CombatBar()
        self.combat_bar.on_combat_action = self._on_combat_action
        self.layout.add_widget(self.combat_bar)

        # Flee to game screen button.
        self.btn_back = themed_button(
            "返回游戏界面", font_size=dp(12), size_hint_y=None, height=dp(30),
        )
        self.btn_back.bind(on_release=lambda _: self._go_back())
        self.layout.add_widget(self.btn_back)

        self.add_widget(self.layout)

        # Combat state cache.
        self._combat_state: dict | None = None

    def update_combat(self, combat_state: dict | None) -> None:
        """Update display from combat state."""
        self._combat_state = combat_state
        if combat_state is None:
            self._go_back()
            return

        self.combat_bar.update_combat(combat_state)
        theme = current_theme()

        # Enemy info.
        enemy = combat_state.get("enemy", {})
        self.lbl_enemy_name.text = enemy.get("name", "敌人")
        enemy_hp_max = max(1, enemy.get("hp_max", 1))
        enemy_hp = max(0, min(enemy.get("hp", 0), enemy_hp_max))
        self.enemy_hp_bar.max = enemy_hp_max
        self.enemy_hp_bar.value = enemy_hp
        self.enemy_hp_bar.bar_color = theme.hp_high if enemy_hp / enemy_hp_max > 0.3 else theme.hp_low
        self.lbl_enemy_hp.text = f"HP: {enemy_hp}/{enemy_hp_max}"
        self.lbl_enemy_realm.text = f"境界: {enemy.get('realm', '?')}"

        # Player info.
        player = combat_state.get("player", {})
        self.lbl_player_name.text = player.get("name", "你")
        player_hp_max = max(1, player.get("hp_max", 1))
        player_hp = max(0, min(player.get("hp", 0), player_hp_max))
        self.player_hp_bar.max = player_hp_max
        self.player_hp_bar.value = player_hp
        self.player_hp_bar.bar_color = theme.hp_high if player_hp / player_hp_max > 0.3 else theme.hp_low
        self.lbl_player_hp.text = f"HP: {player_hp}/{player_hp_max}"
        player_mp_max = max(1, player.get("mp_max", 1))
        player_mp = max(0, min(player.get("mp", 0), player_mp_max))
        self.lbl_player_mp.text = f"MP: {player_mp}/{player_mp_max}"

        # Narrative.
        narrative = combat_state.get("narrative", "")
        turn = combat_state.get("turn_count", 0)
        self.lbl_narrative.text = f"第{turn}回合: {narrative}" if narrative else ""

    def _on_combat_action(self, action: str, target: str) -> None:
        if self.adapter:
            self.adapter.handle_combat_action(action, target)

    def _go_back(self) -> None:
        if self.manager:
            self.manager.current = "game"
