"""Prototype-aligned top character information card."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from theme import add_background, current_theme


class StatusBar(BoxLayout):
    """Top card: character name, turn count, and six stat cells."""

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(104),
            padding=[dp(10), dp(8)],
            spacing=dp(6),
            **kwargs,
        )
        theme = current_theme()
        add_background(self, color=theme.surface)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(26))
        self.lbl_name = Label(
            text="文字修仙",
            font_size=dp(18),
            bold=True,
            color=theme.text,
            halign="left",
            valign="middle",
            size_hint_x=0.6,
        )
        self.lbl_turn = Label(
            text="",
            font_size=dp(12),
            color=theme.text_secondary,
            halign="right",
            valign="middle",
            size_hint_x=0.4,
        )
        for label in (self.lbl_name, self.lbl_turn):
            label.bind(width=lambda *a, w=label: w.setter("text_size")(w, (w.width, None)))
            row.add_widget(label)
        self.add_widget(row)

        self.grid = GridLayout(cols=3, spacing=[dp(6), dp(5)], size_hint_y=None, height=dp(58))
        self._cells: dict[str, Label] = {}
        for key, caption in [
            ("age", "年龄"),
            ("realm", "境界"),
            ("spirit_root", "灵根"),
            ("talent", "天赋"),
            ("family_background", "家世"),
            ("luck", "气运"),
        ]:
            cell = Label(
                text=f"{caption}  -",
                font_size=dp(10),
                color=theme.text_secondary,
                halign="center",
                valign="middle",
            )
            add_background(cell, color=(1, 1, 1, 0.20))
            cell.bind(width=lambda *a, w=cell: w.setter("text_size")(w, (w.width, None)))
            self._cells[key] = cell
            self.grid.add_widget(cell)
        self.add_widget(self.grid)

        self.on_breakthrough = None

    def update(self, session) -> None:
        """Update display from GameSession."""
        theme = current_theme()
        if not session.game_started:
            self.lbl_name.text = "文字修仙"
            self.lbl_turn.text = ""
            values = {
                "age": "年龄  -",
                "realm": "境界  -",
                "spirit_root": "灵根  -",
                "talent": "天赋  -",
                "family_background": "家世  -",
                "luck": "气运  -",
            }
        else:
            self.lbl_name.text = session.char_name or "无名"
            self.lbl_turn.text = f"第 {session.turn_count} 回合"
            values = {
                "age": f"年龄  {getattr(session, 'age', 16)}",
                "realm": f"境界  {session.realm}",
                "spirit_root": f"灵根  {session.spirit_root or '未觉醒'}",
                "talent": f"天赋  {getattr(session, 'talent', '') or '未显'}",
                "family_background": f"家世  {getattr(session, 'family_background', '') or '凡俗'}",
                "luck": f"气运  {getattr(session, 'luck', '') or '平稳'}",
            }
        self.lbl_name.color = theme.text
        self.lbl_turn.color = theme.text_secondary
        for key, text in values.items():
            cell = self._cells[key]
            cell.text = text
            cell.color = theme.text_secondary
