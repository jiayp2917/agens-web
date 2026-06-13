"""Top status bar widget — compact 3-row layout merging old StatusBar + RealmCard.

Total height: 64dp (down from 56+80=136dp) — gives 72dp more narrative space.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp

from theme import ThemedProgressBar, add_background, current_theme, themed_button


class StatusBar(BoxLayout):
    """Compact 3-row status bar: name/realm/combat | HP+MP bars | EXP+breakthrough.

    Height: dp(64) — replaces old StatusBar(56) + RealmCard(80).
    """

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(64),
            padding=[dp(6), dp(2)],
            spacing=dp(1),
            **kwargs,
        )
        theme = current_theme()
        add_background(self, color=theme.surface)

        # Row 1: Name | Realm+Spirit Root | Turn | Combat indicator
        row1 = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(18),
            spacing=dp(4),
        )
        self.lbl_name = Label(text="修仙", font_size=dp(12), size_hint_x=0.18, halign="left", color=theme.text)
        self.lbl_realm = Label(text="", font_size=dp(11), size_hint_x=0.30, halign="left", color=theme.text_secondary)
        self.lbl_turn = Label(text="", font_size=dp(10), size_hint_x=0.17, halign="center", color=theme.text_hint)
        self.lbl_combat = Label(text="", font_size=dp(10), size_hint_x=0.15, halign="right", color=theme.combat_indicator)
        self.lbl_gold = Label(text="", font_size=dp(10), size_hint_x=0.20, halign="right", color=theme.accent)

        for w in [self.lbl_name, self.lbl_realm, self.lbl_turn, self.lbl_combat, self.lbl_gold]:
            w.bind(width=lambda *a, widget=w: widget.setter("text_size")(widget, (widget.width, None)))
            row1.add_widget(w)
        self.add_widget(row1)

        # Row 2: HP bar | MP bar
        row2 = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(22),
            spacing=dp(4),
        )
        self.lbl_hp = Label(text="HP", font_size=dp(9), size_hint_x=0.07, color=theme.text_secondary)
        self.hp_bar = ThemedProgressBar(bar_color=theme.hp_high, max=100, value=100, size_hint_x=0.38)
        self.lbl_hp_num = Label(text="", font_size=dp(9), size_hint_x=0.12, color=theme.text_secondary)

        self.lbl_mp = Label(text="MP", font_size=dp(9), size_hint_x=0.07, color=theme.mp_color)
        self.mp_bar = ThemedProgressBar(bar_color=theme.mp_color, max=50, value=50, size_hint_x=0.28)
        self.lbl_mp_num = Label(text="", font_size=dp(9), size_hint_x=0.08, color=theme.text_secondary)

        row2.add_widget(self.lbl_hp)
        row2.add_widget(self.hp_bar)
        row2.add_widget(self.lbl_hp_num)
        row2.add_widget(self.lbl_mp)
        row2.add_widget(self.mp_bar)
        row2.add_widget(self.lbl_mp_num)
        self.add_widget(row2)

        # Row 3: EXP bar + breakthrough button (replaces RealmCard)
        row3 = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(20),
            spacing=dp(4),
        )
        self.lbl_xp = Label(text="EXP", font_size=dp(9), size_hint_x=0.08, color=theme.text_secondary)
        self.xp_bar = ThemedProgressBar(bar_color=theme.xp_color, max=100, value=0, size_hint_x=0.52)
        self.lbl_xp_num = Label(text="", font_size=dp(9), size_hint_x=0.18, color=theme.text_secondary)
        self.btn_breakthrough = themed_button("突破", font_size=dp(10), size_hint_x=0.22)
        self.btn_breakthrough.disabled = True
        self.btn_breakthrough.bind(on_release=lambda _: self._on_breakthrough())

        row3.add_widget(self.lbl_xp)
        row3.add_widget(self.xp_bar)
        row3.add_widget(self.lbl_xp_num)
        row3.add_widget(self.btn_breakthrough)
        self.add_widget(row3)

        # Callbacks.
        self.on_breakthrough = None

    def _on_breakthrough(self) -> None:
        if self.on_breakthrough:
            self.on_breakthrough()

    def update(self, session) -> None:
        """Update display from GameSession."""
        if not session.game_started:
            self.lbl_name.text = "修仙"
            self.lbl_realm.text = ""
            self.lbl_turn.text = ""
            self.lbl_combat.text = ""
            self.lbl_gold.text = ""
            self.lbl_hp.text = "HP"
            self.lbl_mp.text = "MP"
            self.lbl_hp_num.text = ""
            self.lbl_mp_num.text = ""
            self.lbl_xp.text = "EXP"
            self.lbl_xp_num.text = ""
            self.hp_bar.max = 100
            self.hp_bar.value = 0
            self.mp_bar.max = 50
            self.mp_bar.value = 0
            self.xp_bar.max = 100
            self.xp_bar.value = 0
            self.btn_breakthrough.disabled = True
            return

        theme = current_theme()
        _STAGE_CN = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]

        # Name.
        self.lbl_name.text = session.char_name or "无名"

        # Realm + spirit root on one line.
        stage = session.realm_stage
        stage_str = _STAGE_CN[stage] if 1 <= stage <= 9 else f"{stage}层"
        sr = f" {session.spirit_root}" if session.spirit_root else ""
        self.lbl_realm.text = f"{session.realm}{stage_str}{sr}"

        # Turn count.
        self.lbl_turn.text = f"T{session.turn_count}"

        # Combat indicator.
        self.lbl_combat.text = "⚔战斗" if session.combat else ""

        # Gold.
        self.lbl_gold.text = f"灵石{session.gold}"

        # HP.
        self.hp_bar.max = max(1, session.hp_max)
        self.hp_bar.value = max(0, min(session.hp, session.hp_max))
        self.lbl_hp_num.text = f"{session.hp}/{session.hp_max}"
        hp_pct = session.hp / max(1, session.hp_max)
        self.hp_bar.bar_color = theme.hp_high if hp_pct > 0.3 else theme.hp_low

        # MP.
        self.mp_bar.max = max(1, session.mp_max)
        self.mp_bar.value = max(0, min(session.mp, session.mp_max))
        self.lbl_mp_num.text = f"{session.mp}/{session.mp_max}"

        # EXP.
        self.xp_bar.max = max(1, session.experience_to_next)
        self.xp_bar.value = max(0, min(session.experience, session.experience_to_next))
        self.lbl_xp_num.text = f"{session.experience}/{session.experience_to_next}"

        # Breakthrough eligibility.
        from agens_novel.game.realm import RealmSystem
        rs = RealmSystem()
        can, reason = rs.can_attempt_breakthrough(session)
        self.btn_breakthrough.disabled = not can
