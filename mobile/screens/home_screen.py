"""Home / main menu screen — first screen the user sees on launch.

Layout:
  ┌─────────────────────────────┐
  │                             │
  │      Title / Splash Area    │
  │    "文字修仙" + subtitle    │
  │                             │
  ├─────────────────────────────┤
  │   [继续游戏]               │
  │   [新游戏]                 │
  │   [存档管理]               │
  │   [设置]                   │
  │   [退出]                   │
  └─────────────────────────────┘
"""

from __future__ import annotations

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.metrics import dp
from kivy.core.window import Window

from theme import add_background, current_theme, themed_button
from service.engine_adapter import EngineAdapter


class HomeScreen(Screen):
    """Main menu screen shown on app launch."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        theme = current_theme()
        add_background(self, color=theme.bg)

        self.layout = BoxLayout(
            orientation="vertical",
            padding=[dp(24), dp(16)],
            spacing=dp(8),
        )

        # ── Title area ──
        title_box = BoxLayout(
            orientation="vertical",
            size_hint_y=0.55,
            spacing=dp(4),
            padding=[dp(16), dp(16)],
        )

        # Splash image (optional — degrades gracefully if missing).
        splash_path = self._find_splash_image()
        if splash_path:
            self.splash = Image(
                source=splash_path,
                allow_stretch=True,
                keep_ratio=True,
                size_hint_y=0.7,
            )
            title_box.add_widget(self.splash)

        # Title text.
        self.lbl_title = Label(
            text="[b]文字修仙[/b]",
            markup=True,
            font_size=dp(32),
            color=theme.primary,
            size_hint_y=None,
            height=dp(48),
        )
        title_box.add_widget(self.lbl_title)

        self.lbl_subtitle = Label(
            text="AI 驱动的修仙模拟器",
            font_size=dp(14),
            color=theme.text_secondary,
            size_hint_y=None,
            height=dp(24),
        )
        title_box.add_widget(self.lbl_subtitle)

        self.layout.add_widget(title_box)

        # ── Menu buttons ──
        btn_box = BoxLayout(
            orientation="vertical",
            size_hint_y=0.45,
            spacing=dp(10),
            padding=[dp(40), dp(8)],
        )

        self.btn_continue = themed_button("继续游戏", font_size=dp(16), size_hint_y=None, height=dp(48))
        self.btn_new = themed_button("新游戏", font_size=dp(16), size_hint_y=None, height=dp(48))
        self.btn_saves = themed_button("存档管理", font_size=dp(16), size_hint_y=None, height=dp(48))
        self.btn_settings = themed_button("设置", font_size=dp(16), size_hint_y=None, height=dp(48))
        self.btn_quit = themed_button("退出", font_size=dp(14), size_hint_y=None, height=dp(40))

        self.btn_continue.bind(on_release=self._on_continue)
        self.btn_new.bind(on_release=self._on_new_game)
        self.btn_saves.bind(on_release=self._on_saves)
        self.btn_settings.bind(on_release=self._on_settings)
        self.btn_quit.bind(on_release=self._on_quit)

        btn_box.add_widget(self.btn_continue)
        btn_box.add_widget(self.btn_new)
        btn_box.add_widget(self.btn_saves)
        btn_box.add_widget(self.btn_settings)
        btn_box.add_widget(self.btn_quit)

        self.layout.add_widget(btn_box)
        self.add_widget(self.layout)

    def on_enter(self, *args):
        """Refresh button states when entering the screen."""
        if self.adapter and self.adapter.game_session.game_started:
            self.btn_continue.opacity = 1.0
            self.btn_continue.disabled = False
        else:
            self.btn_continue.opacity = 0.4
            self.btn_continue.disabled = True

    # ─── Navigation ────────────────────────────────────────────────────

    def _on_continue(self, instance):
        """Resume the current game."""
        if self.manager:
            self.manager.current = "game"

    def _on_new_game(self, instance):
        """Start a new game — switch to game screen and show dialog."""
        if self.manager:
            self.manager.current = "game"
            game_screen = self.manager.get_screen("game")
            game_screen._show_new_game_dialog()

    def _on_saves(self, instance):
        """Open save management screen."""
        if self.manager:
            self.manager.current = "save"

    def _on_settings(self, instance):
        """Open settings screen."""
        if self.manager:
            self.manager.current = "settings"

    def _on_quit(self, instance):
        """Close the app."""
        from kivy.app import App
        App.get_running_app().stop()

    # ─── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _find_splash_image() -> str | None:
        """Look for a splash image in assets/images/."""
        import os
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "images", "splash.png"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "images", "splash.jpg"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None
