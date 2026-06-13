"""Theme system for the Kivy mobile app.

Provides three switchable color palettes (明亮白 / 暗夜黑 / 清新绿)
plus themed widget factories (ThemedProgressBar, themed_button, themed_popup)
so every screen and widget can share one consistent visual style.

The active theme is read from settings_store at call time — no global
state to reset when the user picks a new theme in Settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.widget import Widget


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ThemePalette:
    """Immutable color palette. All RGBA values are 0-1 floats."""
    bg: Tuple[float, float, float, float]
    surface: Tuple[float, float, float, float]
    primary: Tuple[float, float, float, float]
    accent: Tuple[float, float, float, float]
    text: Tuple[float, float, float, float]
    text_secondary: Tuple[float, float, float, float]
    text_hint: Tuple[float, float, float, float]
    hp_high: Tuple[float, float, float, float]
    hp_low: Tuple[float, float, float, float]
    mp_color: Tuple[float, float, float, float]
    xp_color: Tuple[float, float, float, float]
    bar_bg: Tuple[float, float, float, float]
    button_bg: Tuple[float, float, float, float]
    button_text: Tuple[float, float, float, float]
    input_bg: Tuple[float, float, float, float]
    combat_indicator: Tuple[float, float, float, float]
    error_color: Tuple[float, float, float, float]
    success_color: Tuple[float, float, float, float]
    overlay_bg: Tuple[float, float, float, float]
    border_color: Tuple[float, float, float, float]


# 明亮白 (White) — bright, clean, cheerful
# text_secondary and text_hint tuned for WCAG AA contrast on light backgrounds.
WHITE = ThemePalette(
    bg=(0.95, 0.95, 0.97, 1),
    surface=(1.0, 1.0, 1.0, 1),
    primary=(0.2, 0.4, 0.8, 1),
    accent=(0.95, 0.6, 0.1, 1),
    text=(0.13, 0.13, 0.13, 1),
    text_secondary=(0.35, 0.35, 0.35, 1),   # ~5.6:1 on white — passes AA
    text_hint=(0.45, 0.45, 0.45, 1),         # ~3.9:1 — acceptable for hints
    hp_high=(0.2, 0.75, 0.3, 1),
    hp_low=(0.85, 0.2, 0.2, 1),
    mp_color=(0.25, 0.45, 0.85, 1),
    xp_color=(0.6, 0.3, 0.8, 1),
    bar_bg=(0.85, 0.85, 0.88, 1),
    button_bg=(0.2, 0.4, 0.8, 1),
    button_text=(1.0, 1.0, 1.0, 1),
    input_bg=(1.0, 1.0, 1.0, 1),
    combat_indicator=(0.85, 0.15, 0.15, 1),
    error_color=(0.85, 0.2, 0.2, 1),
    success_color=(0.2, 0.75, 0.3, 1),
    overlay_bg=(0, 0, 0, 0.5),
    border_color=(0.8, 0.8, 0.85, 1),
)

# 暗夜黑 (Black) — dark, elegant
BLACK = ThemePalette(
    bg=(0.12, 0.12, 0.15, 1),
    surface=(0.18, 0.18, 0.22, 1),
    primary=(0.4, 0.65, 1.0, 1),
    accent=(1.0, 0.75, 0.2, 1),
    text=(0.9, 0.9, 0.92, 1),
    text_secondary=(0.6, 0.6, 0.65, 1),
    text_hint=(0.45, 0.45, 0.5, 1),
    hp_high=(0.3, 0.8, 0.4, 1),
    hp_low=(0.9, 0.25, 0.25, 1),
    mp_color=(0.35, 0.55, 0.95, 1),
    xp_color=(0.7, 0.4, 0.9, 1),
    bar_bg=(0.25, 0.25, 0.3, 1),
    button_bg=(0.3, 0.5, 0.85, 1),
    button_text=(1.0, 1.0, 1.0, 1),
    input_bg=(0.2, 0.2, 0.25, 1),
    combat_indicator=(0.9, 0.2, 0.2, 1),
    error_color=(0.9, 0.25, 0.25, 1),
    success_color=(0.3, 0.8, 0.4, 1),
    overlay_bg=(0, 0, 0, 0.7),
    border_color=(0.3, 0.3, 0.35, 1),
)

# 清新绿 (Green) — fresh, nature-inspired
GREEN = ThemePalette(
    bg=(0.92, 0.96, 0.92, 1),
    surface=(1.0, 1.0, 0.98, 1),
    primary=(0.2, 0.6, 0.35, 1),
    accent=(0.9, 0.55, 0.15, 1),
    text=(0.15, 0.2, 0.15, 1),
    text_secondary=(0.4, 0.5, 0.4, 1),
    text_hint=(0.55, 0.65, 0.55, 1),
    hp_high=(0.2, 0.7, 0.35, 1),
    hp_low=(0.85, 0.2, 0.2, 1),
    mp_color=(0.2, 0.5, 0.8, 1),
    xp_color=(0.5, 0.35, 0.7, 1),
    bar_bg=(0.82, 0.88, 0.82, 1),
    button_bg=(0.2, 0.6, 0.35, 1),
    button_text=(1.0, 1.0, 1.0, 1),
    input_bg=(1.0, 1.0, 0.98, 1),
    combat_indicator=(0.8, 0.15, 0.15, 1),
    error_color=(0.85, 0.2, 0.2, 1),
    success_color=(0.2, 0.65, 0.35, 1),
    overlay_bg=(0, 0, 0, 0.5),
    border_color=(0.75, 0.85, 0.75, 1),
)


THEMES = {"white": WHITE, "black": BLACK, "green": GREEN}
THEME_KEY = "theme"

# Default theme name; loaded from settings on first call to current_theme().
_DEFAULT_THEME = "white"


def current_theme() -> ThemePalette:
    """Return the active theme palette.

    Reads from settings_store (which uses Kivy's user_data_dir), defaulting
    to WHITE if no setting is saved or the saved name is unknown.

    Importing settings_store is deferred to keep theme.py importable before
    Kivy's app is built (some screens import theme in module-level code).
    """
    try:
        from service.settings_store import load_settings
        data = load_settings()
        name = data.get(THEME_KEY, _DEFAULT_THEME)
        return THEMES.get(name, WHITE)
    except Exception:
        # settings_store may not be importable during early bootstrap;
        # fall back to the default rather than crashing the UI.
        return WHITE


def set_theme(name: str) -> None:
    """Persist the theme name. The next call to current_theme() will see it.

    Does NOT call save_settings here — the caller is expected to save the
    whole settings dict in one go (SettingsScreen does this).
    """
    global _DEFAULT_THEME
    if name in THEMES:
        _DEFAULT_THEME = name


# ---------------------------------------------------------------------------
# CJK font registration
# ---------------------------------------------------------------------------

_FONT_NAME = "NotoSansSC"
_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets", "fonts", "NotoSansSC-Regular.otf",
)

# Kivy's default font slots — registering our font under all four names
# means every Label/Button/TextInput/Spinner picks it up automatically
# without us touching a single widget.
_KIVY_DEFAULT_FONTS = ("Roboto", "DroidSans", "DejaVuSans", "FreeSans")

_font_registered = False


def register_cjk_font() -> bool:
    """Register the bundled CJK font as Kivy's default. Returns True on success.

    Must be called BEFORE importing kivy.uix modules (or at least before any
    widget tree is built). The first call is a no-op on subsequent runs.
    """
    global _font_registered
    if _font_registered:
        return True
    if not os.path.exists(_FONT_PATH):
        return False
    try:
        from kivy.core.text import LabelBase
        for name in _KIVY_DEFAULT_FONTS:
            LabelBase.register(name, _FONT_PATH)
        _font_registered = True
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

def rgba_to_hex(rgba) -> str:
    """Convert (r, g, b, a) 0-1 floats to a 'rrggbb' hex string.

    Used in Kivy markup like [color=rrggbb]…[/color]. Alpha is ignored
    because markup color tags don't accept alpha.
    """
    r, g, b = rgba[0], rgba[1], rgba[2]
    return f"{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


# ---------------------------------------------------------------------------
# Background helper — paint a solid-color rectangle behind a widget
# ---------------------------------------------------------------------------

def add_background(widget: Widget, color=None) -> Rectangle:
    """Draw a solid color rectangle as widget's background. Returns the rect.

    The rectangle follows widget.pos and widget.size automatically, so
    the background stays in sync when the layout reflows.
    """
    if color is None:
        color = current_theme().bg
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    return rect


def add_card_background(widget: Widget, color=None) -> RoundedRectangle:
    """Same as add_background but with rounded corners (slightly raised card)."""
    if color is None:
        color = current_theme().surface
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(6)])
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    return rect


# ---------------------------------------------------------------------------
# ThemedProgressBar — colored fill instead of Kivy's default gray
# ---------------------------------------------------------------------------

class ThemedProgressBar(ProgressBar):
    """ProgressBar with custom canvas for a colored fill on a track.

    Usage:
        bar = ThemedProgressBar(bar_color=theme.hp_high, max=100, value=80)

    Change color later:
        bar.bar_color = theme.hp_low
    """

    def __init__(self, bar_color=None, **kwargs):
        self._bar_color_value = bar_color or current_theme().hp_high
        super().__init__(**kwargs)

        theme = current_theme()
        # Track on canvas.before (drawn first, behind fill)
        with self.canvas.before:
            Color(*theme.bar_bg)
            self._track = Rectangle(pos=self.pos, size=self.size)
        # Fill on canvas.after (drawn on top of track)
        with self.canvas.after:
            self._fill_color = Color(*self._bar_color_value)
            self._fill = Rectangle(pos=self.pos, size=(0, self.height))

        self.bind(
            pos=self._update_geometry,
            size=self._update_geometry,
            value=self._update_fill,
            max=self._update_fill,
        )
        self._update_geometry()

    @property
    def bar_color(self):
        return self._bar_color_value

    @bar_color.setter
    def bar_color(self, value):
        self._bar_color_value = value
        self._fill_color.rgba = value

    def _update_geometry(self, *_args):
        self._track.pos = self.pos
        self._track.size = self.size
        self._update_fill()

    def _update_fill(self, *_args):
        norm = (self.value / self.max) if self.max else 0
        self._fill.pos = self.pos
        self._fill.size = (norm * self.width, self.height)


# ---------------------------------------------------------------------------
# themed_button — Button with rounded background filled with primary color
# ---------------------------------------------------------------------------

def themed_button(text: str, font_size=dp(13), **kwargs) -> Button:
    """Create a Button styled with the active theme.

    - background_color = (0,0,0,0) so Kivy's default gray square is hidden
    - RoundedRectangle drawn on canvas.before, filled with primary color
    - text color = button_text (white-ish for all three themes)
    """
    theme = current_theme()
    btn = Button(text=text, font_size=font_size, **kwargs)
    btn.background_color = (0, 0, 0, 0)  # transparent default
    btn.color = theme.button_text
    btn.background_normal = ""  # no default image
    btn.background_down = ""

    with btn.canvas.before:
        btn._bg_rect_color = Color(*theme.button_bg)
        btn._bg_rect = RoundedRectangle(
            pos=btn.pos, size=btn.size, radius=[dp(4)]
        )
    btn.bind(
        pos=lambda _w, _v, b=btn: setattr(b._bg_rect, "pos", _v),
        size=lambda _w, _v, b=btn: setattr(b._bg_rect, "size", _v),
    )
    return btn


# ---------------------------------------------------------------------------
# themed_popup — Popup with surface background and themed title/separator
# ---------------------------------------------------------------------------

def themed_popup(title: str, content, **kwargs) -> Popup:
    """Create a Popup styled with the active theme.

    Uses an empty string as background to override Kivy's dark default image,
    then sets a solid surface color on top.  This eliminates the dark-gray
    title bar that the default 9-patch image causes.
    """
    theme = current_theme()
    kwargs.setdefault("title_size", dp(18))
    kwargs.setdefault("size_hint", (0.85, 0.5))
    popup = Popup(
        title=title,
        content=content,
        background="",                     # no default dark image
        background_color=theme.surface,    # solid surface color
        title_color=theme.text,
        separator_color=theme.primary,
        **kwargs,
    )
    return popup
