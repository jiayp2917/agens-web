"""Visual constants for the Android ink-wash UI."""

from __future__ import annotations

import sys
import types


class _Dummy:
    def __init__(self, *args, **kwargs):
        pass


def _install_kivy_stubs(monkeypatch):
    modules = {
        "kivy": types.ModuleType("kivy"),
        "kivy.graphics": types.ModuleType("kivy.graphics"),
        "kivy.metrics": types.ModuleType("kivy.metrics"),
        "kivy.uix": types.ModuleType("kivy.uix"),
        "kivy.uix.button": types.ModuleType("kivy.uix.button"),
        "kivy.uix.popup": types.ModuleType("kivy.uix.popup"),
        "kivy.uix.progressbar": types.ModuleType("kivy.uix.progressbar"),
        "kivy.uix.widget": types.ModuleType("kivy.uix.widget"),
    }
    modules["kivy.graphics"].Color = _Dummy
    modules["kivy.graphics"].Line = _Dummy
    modules["kivy.graphics"].Rectangle = _Dummy
    modules["kivy.graphics"].RoundedRectangle = _Dummy
    modules["kivy.metrics"].dp = lambda value: value
    modules["kivy.uix.button"].Button = _Dummy
    modules["kivy.uix.popup"].Popup = _Dummy
    modules["kivy.uix.progressbar"].ProgressBar = _Dummy
    modules["kivy.uix.widget"].Widget = _Dummy
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def _hex_to_rgb(hex_value: str) -> tuple[float, float, float]:
    value = hex_value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _assert_close(actual, expected, tolerance=0.05):
    for a, e in zip(actual[:3], expected, strict=False):
        assert abs(a - e) <= tolerance


def test_paper_theme_matches_current_plan_values(monkeypatch):
    _install_kivy_stubs(monkeypatch)
    from mobile.theme import WHITE

    _assert_close(WHITE.bg, _hex_to_rgb("#f7f3ea"))
    _assert_close(WHITE.surface, _hex_to_rgb("#fff8f0"))
    _assert_close(WHITE.primary, _hex_to_rgb("#52746d"))
    _assert_close(WHITE.accent, _hex_to_rgb("#a77d38"))
    _assert_close(WHITE.text, _hex_to_rgb("#202a27"))


def test_additional_ink_themes_match_plan_values(monkeypatch):
    _install_kivy_stubs(monkeypatch)
    from mobile.theme import BLACK, GREEN

    _assert_close(GREEN.bg, _hex_to_rgb("#dfe9df"))
    _assert_close(GREEN.surface, _hex_to_rgb("#c8d8c8"))
    _assert_close(GREEN.primary, _hex_to_rgb("#3a5c42"))
    _assert_close(GREEN.accent, _hex_to_rgb("#8a6d2b"))

    _assert_close(BLACK.bg, _hex_to_rgb("#202a27"))
    _assert_close(BLACK.surface, _hex_to_rgb("#2d3b36"))
    _assert_close(BLACK.primary, _hex_to_rgb("#7aad9e"))
    _assert_close(BLACK.accent, _hex_to_rgb("#d4a54a"))
