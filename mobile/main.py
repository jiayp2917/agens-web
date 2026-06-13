"""文字修仙 — AI-driven Xianxia Cultivation Simulator.

Kivy app entry point. Run on desktop with:
    python mobile/main.py

Build APK with Buildozer (requires Linux/WSL2):
    cd mobile && buildozer android debug
"""

from __future__ import annotations

import base64
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

# On Android (buildozer source.dir=.), all packages live flat alongside main.py:
#   screens/, widgets/, service/, agens_novel/, config/
# On desktop, mobile/main.py's parent is mobile/; the project root is one level up.
if _IS_ANDROID:
    _project_root = _app_dir          # app dir IS the project root on Android
else:
    # Desktop: project root = mobile/.. (contains src/agens_novel/)
    _project_root = _app_dir.parent if (_app_dir.parent / "src" / "agens_novel").exists() else _app_dir

_src_dir = _project_root / "src"

if _IS_ANDROID:
    os.environ["AGENS_NOVEL_ROOT"] = str(_project_root)

for _path in (_app_dir, _src_dir, _project_root):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

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


def _inject_builtin_key() -> None:
    """Inject the built-in API key into environment if no user key is set.

    This ensures the app works out-of-the-box on mobile without requiring
    the user to configure an API key first.
    """
    if not os.environ.get("AGNES_API_KEY"):
        # Decode the built-in key from client.py.
        _DEFAULT_KEY_B64 = "c2stdkN2QlNJOGdsbGtyZTJrZktSR0UyZ25KU1BmYlJmSnVNY21CTnFITldMNGhZVzVY"
        try:
            key = base64.b64decode(_DEFAULT_KEY_B64).decode("utf-8")
            os.environ["AGNES_API_KEY"] = key
        except Exception:
            pass  # If built-in key fails, user must configure manually.


class XianxiaApp(App):
    """Main Kivy application."""

    title = "文字修仙"
    icon = ""

    def build(self):
        # Inject built-in key before anything else.
        _inject_builtin_key()

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


if __name__ == "__main__":
    XianxiaApp().run()
