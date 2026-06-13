"""Smoke test: simulate user clicking through Settings screen to find crash."""
import sys
sys.path.insert(0, "mobile")
sys.path.insert(0, "src")

import theme
theme.register_cjk_font()

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from kivy.clock import Clock
from screens.game_screen import GameScreen
from screens.settings_screen import SettingsScreen


class SmokeApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(GameScreen(name="game"))
        sm.add_widget(SettingsScreen(name="settings"))

        def step1(dt):
            sm.current = "settings"
            print("STEP 1: entered settings OK")

        def step2(dt):
            print("STEP 2: simulating _on_preset_changed...")
            try:
                sm.get_screen("settings")._on_preset_changed(None, "DeepSeek")
                print("  preset changed OK")
            except Exception:
                import traceback; traceback.print_exc()

        def step3(dt):
            print("STEP 3: simulating _on_theme_pick(black)...")
            try:
                sm.get_screen("settings")._on_theme_pick("black")
                print("  theme picked OK")
            except Exception:
                import traceback; traceback.print_exc()

        def step4(dt):
            print("STEP 4: simulating _on_save(None)...")
            try:
                sm.get_screen("settings")._on_save(None)
                print("  save OK")
            except Exception:
                import traceback; traceback.print_exc()
            App.get_running_app().stop()

        Clock.schedule_once(step1, 0.5)
        Clock.schedule_once(step2, 1.0)
        Clock.schedule_once(step3, 1.5)
        Clock.schedule_once(step4, 2.0)
        return sm


if __name__ == "__main__":
    SmokeApp().run()
    print("DONE")
