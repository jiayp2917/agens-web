"""Realm info card widget — displays current realm and breakthrough info."""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp

from theme import ThemedProgressBar, add_card_background, current_theme, themed_button


class RealmCard(BoxLayout):
    """Compact card showing realm, experience, spirit root, and breakthrough button.

    Events:
        on_breakthrough() — user tapped the breakthrough button
    """

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(80),
            padding=[dp(8), dp(4)],
            spacing=dp(2),
            **kwargs,
        )
        add_card_background(self, color=theme.surface)

        # Row 1: Realm name + spirit root.
        row1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22))
        self.lbl_realm = Label(text="练气一层", font_size=dp(14), halign="left", size_hint_x=0.5, color=theme.text)
        self.lbl_spirit_root = Label(text="灵根: 未觉醒", font_size=dp(11), halign="left", size_hint_x=0.5, color=theme.text_secondary)
        self.lbl_realm.bind(width=lambda *a: self.lbl_realm.setter("text_size")(self.lbl_realm, (self.lbl_realm.width, None)))
        self.lbl_spirit_root.bind(width=lambda *a: self.lbl_spirit_root.setter("text_size")(self.lbl_spirit_root, (self.lbl_spirit_root.width, None)))
        row1.add_widget(self.lbl_realm)
        row1.add_widget(self.lbl_spirit_root)
        self.add_widget(row1)

        # Row 2: Experience bar.
        row2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(20))
        self.lbl_xp = Label(text="EXP", font_size=dp(10), size_hint_x=0.12, color=theme.text_secondary)
        self.xp_bar = ThemedProgressBar(bar_color=theme.xp_color, max=100, value=0, size_hint_x=0.68)
        self.lbl_xp_num = Label(text="0/100", font_size=dp(10), size_hint_x=0.2, color=theme.text_secondary)
        row2.add_widget(self.lbl_xp)
        row2.add_widget(self.xp_bar)
        row2.add_widget(self.lbl_xp_num)
        self.add_widget(row2)

        # Row 3: Breakthrough button.
        row3 = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(30))
        self.btn_breakthrough = themed_button(
            "尝试突破",
            font_size=dp(12),
            size_hint_x=0.4,
        )
        self.btn_breakthrough.disabled = True
        self.btn_breakthrough.bind(on_release=lambda _: self._on_breakthrough())
        self.lbl_breakthrough_info = Label(
            text="",
            font_size=dp(10),
            halign="left",
            size_hint_x=0.6,
            color=theme.text_hint,
        )
        self.lbl_breakthrough_info.bind(width=lambda *a: self.lbl_breakthrough_info.setter("text_size")(self.lbl_breakthrough_info, (self.lbl_breakthrough_info.width, None)))
        row3.add_widget(self.btn_breakthrough)
        row3.add_widget(self.lbl_breakthrough_info)
        self.add_widget(row3)

        # Callbacks.
        self.on_breakthrough = None

    def update(self, session) -> None:
        """Update display from GameSession."""
        # Realm display.
        _STAGE_CN = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]
        stage = session.realm_stage
        stage_str = _STAGE_CN[stage] if 1 <= stage <= 9 else f"{stage}层"
        self.lbl_realm.text = f"{session.realm}{stage_str}"

        # Spirit root.
        sr = session.spirit_root or "未觉醒"
        grade = f"({session.spirit_root_grade}级)" if session.spirit_root_grade else ""
        self.lbl_spirit_root.text = f"灵根: {sr}{grade}"

        # Experience.
        self.xp_bar.max = max(1, session.experience_to_next)
        self.xp_bar.value = max(0, min(session.experience, session.experience_to_next))
        self.lbl_xp_num.text = f"{session.experience}/{session.experience_to_next}"

        # Breakthrough eligibility check.
        from agens_novel.game.realm import RealmSystem
        rs = RealmSystem()
        can, reason = rs.can_attempt_breakthrough(session)
        self.btn_breakthrough.disabled = not can
        if can:
            rate = rs.calculate_breakthrough_rate(session)
            self.lbl_breakthrough_info.text = f"突破概率: {rate:.0%}"
        else:
            self.lbl_breakthrough_info.text = reason[:20] if reason else ""

    def _on_breakthrough(self) -> None:
        if self.on_breakthrough:
            self.on_breakthrough()
