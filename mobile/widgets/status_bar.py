"""Prototype-aligned top character information card."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from theme import add_background, current_theme

# 感悟 threshold lookup — mirrors engine.render._insight_required without
# importing the engine layer (mobile stays UI-only).
try:
    from agens_novel.game.constants import REALM_CONFIGS as _REALM_CONFIGS
except Exception:  # pragma: no cover — keep the widget import-safe in isolation
    _REALM_CONFIGS = {}

# Chinese stage labels for display: 练气三层, 筑基二层, etc.
_STAGE_CN = ["", "一层", "二层", "三层", "四层", "五层", "六层", "七层", "八层", "九层"]


def _stage_label(stage: int) -> str:
    """Convert integer stage to Chinese label (1→一层, 2→二层, etc.)."""
    if 1 <= stage <= 9:
        return _STAGE_CN[stage]
    return f"{stage}层"


class StatusBar(BoxLayout):
    """Top card: character name, turn count, and six stat cells."""

    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(112),
            padding=[dp(8), dp(6)],
            spacing=dp(4),
            **kwargs,
        )
        theme = current_theme()
        add_background(self, color=theme.surface)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        self.lbl_name = Label(
            text="文字修仙",
            font_size=dp(17),
            bold=True,
            color=theme.text,
            halign="left",
            valign="middle",
            size_hint_x=0.6,
            shorten=True,
            shorten_from="right",
        )
        self.lbl_turn = Label(
            text="",
            font_size=dp(12),
            color=theme.text_secondary,
            halign="right",
            valign="middle",
            size_hint_x=0.4,
            shorten=True,
            shorten_from="left",
        )
        for label in (self.lbl_name, self.lbl_turn):
            _bind_single_line(label)
            row.add_widget(label)
        self.add_widget(row)

        self.grid = GridLayout(cols=2, spacing=[dp(4), dp(4)], size_hint_y=None, height=dp(72))
        self._cells: dict[str, Label] = {}
        for key, caption in [
            ("age", "年龄"),
            ("realm", "境界"),
            ("spirit_root", "灵根"),
            ("talent", "天赋"),
            ("insight", "感悟"),
            ("luck", "气运"),
        ]:
            cell = Label(
                text=f"{caption}  -",
                font_size=dp(10),
                color=theme.text_secondary,
                halign="center",
                valign="middle",
                shorten=True,
                shorten_from="right",
            )
            add_background(cell, color=(1, 1, 1, 0.20))
            _bind_single_line(cell)
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
                "insight": "感悟  -",
                "luck": "气运  -",
            }
        else:
            self.lbl_name.text = session.char_name or "无名"
            self.lbl_turn.text = f"第 {session.turn_count} 回合"
            stage = getattr(session, "realm_stage", 1)
            insight = getattr(session, "insight", 0)
            insight_req = _insight_required(session.realm)
            values = {
                "age": f"年龄  {getattr(session, 'age', 16)}",
                "realm": f"境界  {session.realm}{_stage_label(stage)}",
                "spirit_root": f"灵根  {_compact(getattr(session, 'spirit_root', '') or '未觉醒', 6)}",
                "talent": f"天赋  {_compact(getattr(session, 'talent', '') or '未显', 6)}",
                "insight": f"感悟  {insight}/{insight_req}" if insight_req else f"感悟  {insight}",
                "luck": f"气运  {getattr(session, 'luck', '') or '平稳'}",
            }
        self.lbl_name.color = theme.text
        self.lbl_turn.color = theme.text_secondary
        for key, text in values.items():
            cell = self._cells[key]
            cell.text = text
            cell.color = theme.text_secondary


def _bind_single_line(label: Label) -> None:
    """Keep status labels inside their cell width."""
    label.bind(width=lambda *_a, w=label: setattr(w, "text_size", (w.width, None)))
    label.max_lines = 1


def _compact(value: str, limit: int) -> str:
    """Shorten CJK-heavy status values before Kivy lays them out."""
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)] + "…"


def _insight_required(realm: str) -> int:
    """Insight needed to break out of ``realm`` (0 if unknown/terminal)."""
    cfg = _REALM_CONFIGS.get(realm) if isinstance(_REALM_CONFIGS, dict) else None
    if not isinstance(cfg, dict):
        return 0
    try:
        return int(cfg.get("insight_required", 0))
    except (TypeError, ValueError):
        return 0
