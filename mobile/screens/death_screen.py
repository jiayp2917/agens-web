"""Full-screen death/restart state."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from service.engine_adapter import EngineAdapter
from theme import add_background, current_theme, themed_button


class DeathScreen(Screen):
    """Game-over screen with restart/load/home actions."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        self.reason = "修行路无常，仍可从此处重开一世。"
        theme = current_theme()
        add_background(self, color=theme.bg)

        outer = BoxLayout(orientation="vertical", padding=[dp(36), dp(150)], spacing=dp(18))
        outer.add_widget(Label(
            text="[b]道途已断[/b]",
            markup=True,
            font_size=dp(32),
            color=theme.error_color,
            size_hint_y=None,
            height=dp(58),
        ))
        self.copy = Label(
            text=self._copy_text(),
            font_size=dp(15),
            color=theme.text_secondary,
            halign="center",
            valign="middle",
        )
        self.copy.bind(width=lambda *a: self.copy.setter("text_size")(self.copy, (self.copy.width, None)))
        outer.add_widget(self.copy)

        actions = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(170), spacing=dp(12))
        restart_btn = themed_button("重新开始", font_size=dp(15), size_hint_y=None, height=dp(46))
        load_btn = themed_button("读取存档", font_size=dp(15), size_hint_y=None, height=dp(46))
        home_btn = themed_button("返回主页", font_size=dp(15), size_hint_y=None, height=dp(46))
        restart_btn.bind(on_release=lambda _: self._restart())
        load_btn.bind(on_release=lambda _: self._load())
        home_btn.bind(on_release=lambda _: self._home())
        actions.add_widget(restart_btn)
        actions.add_widget(load_btn)
        actions.add_widget(home_btn)
        outer.add_widget(actions)
        self.add_widget(outer)

    def set_reason(self, reason: str) -> None:
        self.reason = reason or self.reason
        if hasattr(self, "copy"):
            self.copy.text = self._copy_text()

    def _copy_text(self) -> str:
        return (
            f"{self.reason}\n\n"
            "你的气息散入山风，最后一缕神识停在未走完的石阶前。"
        )

    def _restart(self) -> None:
        if self.adapter:
            self.adapter.reset()
        if self.manager:
            self.manager.current = "character_create"

    def _load(self) -> None:
        if self.manager:
            self.manager.current = "home"
            self.manager.get_screen("home")._show_load_popup()

    def _home(self) -> None:
        if self.manager:
            self.manager.current = "home"
