"""文字修仙 — AI-driven Xianxia Cultivation Simulator.

Kivy app entry point. Run on desktop with:
    python mobile/main.py

Build APK with Buildozer (requires Linux/WSL2):
    cd mobile && buildozer android debug
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform bootstrap – MUST run before any ``agens_novel`` import.
#
# On Android (p4a / Buildozer) the bundled files (agens_novel/, config/,
# screens/, …) live alongside main.py inside the app's private storage.
# ``paths.py`` derives CONFIG_DIR / PROMPT_DIR / RUNTIME_DIR from
# AGENS_NOVEL_ROOT, so we set it here **before** the import chain starts.
# ---------------------------------------------------------------------------

_IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ
_app_dir = Path(__file__).resolve().parent

# With source.dir=.., root main.py imports this module from <app-root>/mobile.
# On desktop, mobile/main.py's parent is also the project root.
if _IS_ANDROID:
    _project_root = _app_dir.parent
else:
    # Desktop: project root = mobile/.. (contains src/agens_novel/)
    _project_root = _app_dir.parent if (_app_dir.parent / "src" / "agens_novel").exists() else _app_dir

_src_dir = _project_root / "src"

if _IS_ANDROID:
    os.environ["AGENS_NOVEL_ROOT"] = str(_project_root)

for _path in (_app_dir, _src_dir, _project_root):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from agens_novel.logging_setup import setup_logging

setup_logging()

# Register bundled CJK font BEFORE any Kivy widget import. This overrides
# Kivy's four default font name slots (Roboto/DroidSans/DejaVuSans/FreeSans)
# with NotoSansSC, so every Label/Button/TextInput/Spinner picks it up
# automatically — no per-widget font_name= needed.
import theme as _theme
_theme.register_cjk_font()

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, SlideTransition

from audio_manager import AudioManager
from service.settings_store import load_settings, apply_settings_to_env
from service.save_manager_compat import set_mobile_save_dir
from screens.game_screen import GameScreen
from screens.home_screen import HomeScreen
from screens.character_create_screen import CharacterCreateScreen
from screens.death_screen import DeathScreen


class XianxiaApp(App):
    """Main Kivy application."""

    title = "文字修仙"
    icon = ""

    def build(self):
        # Load saved settings into env vars.
        data = load_settings()
        apply_settings_to_env(data)
        AudioManager().apply_settings(data)

        # Set save directory to app's internal storage.
        set_mobile_save_dir(self)

        # Apply active theme to window background before any widget builds.
        _theme.set_theme(data.get(_theme.THEME_KEY, "white"))
        Window.clearcolor = _theme.current_theme().bg

        # Screen manager.
        sm = ScreenManager(transition=SlideTransition())

        # Create screens.
        game = GameScreen(name="game")
        home = HomeScreen(adapter=game.adapter, name="home")
        character_create = CharacterCreateScreen(adapter=game.adapter, name="character_create")
        death = DeathScreen(adapter=game.adapter, name="death")

        # Register screens.
        sm.add_widget(home)
        sm.add_widget(game)
        sm.add_widget(character_create)
        sm.add_widget(death)

        sm.current = "home"

        return sm

    def on_stop(self, *args, **kwargs):  # noqa: D401, ANN001 — Kivy contract
        """Tear down the BGM service so SDL audio resources are released cleanly."""
        try:
            from agens_novel.bgm import shutdown_service

            shutdown_service()
        except Exception:
            pass
        return super().on_stop(*args, **kwargs)


if __name__ == "__main__":
    XianxiaApp().run()
