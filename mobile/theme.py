"""Theme system for the Kivy mobile app.

Provides three ink-wash palettes (宣纸白 / 墨绿 / 暗夜)
plus themed widget factories (ThemedProgressBar, themed_button, themed_popup)
so every screen and widget can share one consistent visual style.

The active theme is read from settings_store at call time — no global
state to reset when the user picks a new theme in Settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
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
    bg: tuple[float, float, float, float]
    surface: tuple[float, float, float, float]
    primary: tuple[float, float, float, float]
    accent: tuple[float, float, float, float]
    text: tuple[float, float, float, float]
    text_secondary: tuple[float, float, float, float]
    text_hint: tuple[float, float, float, float]
    hp_high: tuple[float, float, float, float]
    hp_low: tuple[float, float, float, float]
    mp_color: tuple[float, float, float, float]
    xp_color: tuple[float, float, float, float]
    bar_bg: tuple[float, float, float, float]
    button_bg: tuple[float, float, float, float]
    button_text: tuple[float, float, float, float]
    input_bg: tuple[float, float, float, float]
    combat_indicator: tuple[float, float, float, float]
    error_color: tuple[float, float, float, float]
    success_color: tuple[float, float, float, float]
    overlay_bg: tuple[float, float, float, float]
    border_color: tuple[float, float, float, float]


# 宣纸白 — aligned to docs/prototypes/prototype.css :root.
WHITE = ThemePalette(
    bg=(0.969, 0.953, 0.918, 1),            # #f7f3ea
    surface=(1.0, 0.973, 0.941, 1),         # #fff8f0
    primary=(0.322, 0.455, 0.427, 1),       # #52746d
    accent=(0.655, 0.490, 0.220, 1),        # #a77d38
    text=(0.125, 0.165, 0.153, 1),          # #202a27
    text_secondary=(0.325, 0.380, 0.361, 1),
    text_hint=(0.45, 0.46, 0.42, 1),
    hp_high=(0.322, 0.455, 0.427, 1),
    hp_low=(0.608, 0.267, 0.239, 1),
    mp_color=(0.322, 0.455, 0.427, 1),
    xp_color=(0.655, 0.490, 0.220, 1),
    bar_bg=(0.875, 0.851, 0.800, 1),
    button_bg=(0.322, 0.455, 0.427, 0.18),
    button_text=(0.125, 0.165, 0.153, 1),
    input_bg=(1.0, 1.0, 1.0, 0.45),
    combat_indicator=(0.608, 0.267, 0.239, 1),
    error_color=(0.608, 0.267, 0.239, 1),
    success_color=(0.322, 0.455, 0.427, 1),
    overlay_bg=(0.122, 0.149, 0.137, 0.22),
    border_color=(0.125, 0.165, 0.153, 0.28),
)

# 暗夜 — ink-dark reading mode.
BLACK = ThemePalette(
    bg=(0.125, 0.165, 0.153, 1),            # #202a27
    surface=(0.176, 0.231, 0.212, 1),       # #2d3b36
    primary=(0.478, 0.678, 0.620, 1),       # #7aad9e
    accent=(0.831, 0.647, 0.290, 1),        # #d4a54a
    text=(0.926, 0.902, 0.835, 1),
    text_secondary=(0.700, 0.745, 0.702, 1),
    text_hint=(0.580, 0.620, 0.590, 1),
    hp_high=(0.478, 0.678, 0.620, 1),
    hp_low=(0.780, 0.350, 0.310, 1),
    mp_color=(0.478, 0.678, 0.620, 1),
    xp_color=(0.831, 0.647, 0.290, 1),
    bar_bg=(0.220, 0.290, 0.260, 1),
    button_bg=(0.478, 0.678, 0.620, 0.22),
    button_text=(0.926, 0.902, 0.835, 1),
    input_bg=(0.176, 0.231, 0.212, 1),
    combat_indicator=(0.780, 0.350, 0.310, 1),
    error_color=(0.780, 0.350, 0.310, 1),
    success_color=(0.478, 0.678, 0.620, 1),
    overlay_bg=(0, 0, 0, 0.68),
    border_color=(0.478, 0.678, 0.620, 0.28),
)

# 墨绿 — pale green paper variant.
GREEN = ThemePalette(
    bg=(0.875, 0.914, 0.875, 1),            # #dfe9df
    surface=(0.784, 0.847, 0.784, 1),       # #c8d8c8
    primary=(0.227, 0.361, 0.259, 1),       # #3a5c42
    accent=(0.541, 0.427, 0.169, 1),        # #8a6d2b
    text=(0.125, 0.165, 0.153, 1),
    text_secondary=(0.290, 0.380, 0.320, 1),
    text_hint=(0.420, 0.500, 0.430, 1),
    hp_high=(0.227, 0.361, 0.259, 1),
    hp_low=(0.608, 0.267, 0.239, 1),
    mp_color=(0.227, 0.361, 0.259, 1),
    xp_color=(0.541, 0.427, 0.169, 1),
    bar_bg=(0.737, 0.804, 0.737, 1),
    button_bg=(0.227, 0.361, 0.259, 0.18),
    button_text=(0.125, 0.165, 0.153, 1),
    input_bg=(1.0, 1.0, 1.0, 0.42),
    combat_indicator=(0.608, 0.267, 0.239, 1),
    error_color=(0.608, 0.267, 0.239, 1),
    success_color=(0.227, 0.361, 0.259, 1),
    overlay_bg=(0.122, 0.149, 0.137, 0.24),
    border_color=(0.125, 0.165, 0.153, 0.24),
)


THEMES = {"white": WHITE, "black": BLACK, "green": GREEN}
THEME_KEY = "theme"

# Default theme name; loaded from settings on first call to current_theme().
_DEFAULT_THEME = "white"
_THEME_INITIALIZED = False


def current_theme() -> ThemePalette:
    """Return the active theme palette.

    Reads from settings_store (which uses Kivy's user_data_dir), defaulting
    to WHITE if no setting is saved or the saved name is unknown.

    Importing settings_store is deferred to keep theme.py importable before
    Kivy's app is built (some screens import theme in module-level code).
    """
    if _THEME_INITIALIZED:
        return THEMES.get(_DEFAULT_THEME, WHITE)
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
    whole settings dict in one go (the home settings popup does this).
    """
    global _DEFAULT_THEME, _THEME_INITIALIZED
    if name in THEMES:
        _DEFAULT_THEME = name
        _THEME_INITIALIZED = True


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


def asset_path(*parts: str) -> str:
    """Return an absolute path under ``mobile/assets``."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", *parts)


def image_asset(name: str) -> str:
    """Return an absolute path for a generated UI image asset."""
    return asset_path("images", name)


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


def add_image_background(widget: Widget, filename: str, fallback_color=None) -> Rectangle:
    """Draw an image behind a widget, falling back to a theme color."""
    if fallback_color is None:
        fallback_color = current_theme().bg
    source = image_asset(filename)
    with widget.canvas.before:
        Color(1, 1, 1, 1)
        if os.path.exists(source):
            rect = Rectangle(source=source, pos=widget.pos, size=widget.size)
        else:
            Color(*fallback_color)
            rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    return rect


def add_scrim(widget: Widget, color=None) -> Rectangle:
    """Draw a translucent readability layer over image backgrounds."""
    if color is None:
        color = current_theme().overlay_bg
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    return rect


def add_paper_background(widget: Widget, color=None, border: bool = True) -> Rectangle:
    """Draw the generated paper texture with a subtle ink border."""
    if color is None:
        color = current_theme().surface
    theme = current_theme()
    source = image_asset("paper_texture.png")
    with widget.canvas.before:
        Color(*color)
        if os.path.exists(source):
            rect = Rectangle(source=source, pos=widget.pos, size=widget.size)
        else:
            rect = Rectangle(pos=widget.pos, size=widget.size)
        if border:
            Color(*theme.border_color)
            line = Line(rectangle=(widget.x, widget.y, widget.width, widget.height), width=1)
        else:
            line = None
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    if line is not None:
        widget.bind(
            pos=lambda w, _v, b=line: setattr(b, "rectangle", (w.x, w.y, w.width, w.height)),
            size=lambda w, _v, b=line: setattr(b, "rectangle", (w.x, w.y, w.width, w.height)),
        )
    return rect


def add_card_background(widget: Widget, color=None) -> RoundedRectangle:
    """Same as add_background but with rounded corners (slightly raised card)."""
    if color is None:
        color = current_theme().surface
    theme = current_theme()
    with widget.canvas.before:
        Color(*color)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(6)])
        Color(*theme.border_color)
        border = Line(
            rounded_rectangle=(widget.x, widget.y, widget.width, widget.height, dp(6)),
            width=1,
        )
    widget.bind(
        pos=lambda _w, _v, r=rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=rect: setattr(r, "size", _v),
    )
    widget.bind(
        pos=lambda w, _v, b=border: setattr(b, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(6))),
        size=lambda w, _v, b=border: setattr(b, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(6))),
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

def themed_button(text: str, font_size=None, **kwargs) -> Button:
    """Create a Button styled with the active theme.

    - background_color = (0,0,0,0) so Kivy's default gray square is hidden
    - RoundedRectangle drawn on canvas.before, filled with paper-ink color
    - text color = button_text
    """
    theme = current_theme()
    if font_size is None:
        font_size = dp(13)
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
        Color(*theme.border_color)
        btn._border = Line(
            rounded_rectangle=(btn.x, btn.y, btn.width, btn.height, dp(4)),
            width=1,
        )
    btn.bind(
        pos=lambda _w, _v, b=btn: setattr(b._bg_rect, "pos", _v),
        size=lambda _w, _v, b=btn: setattr(b._bg_rect, "size", _v),
    )
    btn.bind(
        pos=lambda w, _v, b=btn: setattr(b._border, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(4))),
        size=lambda w, _v, b=btn: setattr(b._border, "rounded_rectangle", (w.x, w.y, w.width, w.height, dp(4))),
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
