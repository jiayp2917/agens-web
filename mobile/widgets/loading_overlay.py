"""Loading overlay widget — shows a loading animation over the game screen."""

from __future__ import annotations

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivy.animation import Animation
from kivy.properties import BooleanProperty, StringProperty

from theme import current_theme


class LoadingOverlay(BoxLayout):
    """Semi-transparent overlay with a loading message.

    Usage:
        overlay = LoadingOverlay()
        overlay.show("天道运转中...")
        overlay.hide()
    """

    visible = BooleanProperty(False)
    message = StringProperty("加载中...")

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            **kwargs,
        )
        # Start hidden.
        self.opacity = 0
        self.disabled = True
        self.size_hint = (1, 1)
        self.pos_hint = {"x": 0, "y": 0}

        # Semi-transparent background using the theme's overlay color.
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            Color(*theme.overlay_bg)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

        # Center label — bright text so it stays visible on the dark overlay.
        self.lbl = Label(
            text="[b]加载中...[/b]",
            markup=True,
            font_size=dp(18),
            color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
        )
        self.add_widget(self.lbl)

        # Dot animation state.
        self._dot_count = 0
        self._anim_event = None

    def _update_rect(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

    def show(self, message: str = "加载中...") -> None:
        """Show the overlay with a message."""
        self.message = message
        self.lbl.text = f"[b]{message}[/b]"
        self.visible = True
        self.opacity = 1
        self.disabled = False

        # Start dot animation.
        self._dot_count = 0
        if self._anim_event:
            self._anim_event.cancel()
        from kivy.clock import Clock
        self._anim_event = Clock.schedule_interval(self._animate_dots, 0.5)

    def hide(self) -> None:
        """Hide the overlay."""
        self.visible = False
        self.opacity = 0
        self.disabled = True
        if self._anim_event:
            self._anim_event.cancel()
            self._anim_event = None

    def on_touch_down(self, touch):
        """Let touches pass through when the overlay is hidden.

        Kivy consumes touches on disabled widgets that collide with the touch
        area. This overlay is full-screen and sits above the game page, so the
        hidden state must explicitly opt out of touch handling.
        """
        if not self.visible or self.opacity <= 0:
            return False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if not self.visible or self.opacity <= 0:
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if not self.visible or self.opacity <= 0:
            return False
        return super().on_touch_up(touch)

    def _animate_dots(self, dt: float) -> None:
        """Append dots to the loading message for animation effect."""
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        self.lbl.text = f"[b]{self.message}{dots}[/b]"
