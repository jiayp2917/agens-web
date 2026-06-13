"""Scrollable narrative text display widget with streaming support."""

from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp
from kivy.properties import NumericProperty

from theme import add_background, current_theme, rgba_to_hex


class NarrativeView(ScrollView):
    """Scrollable area that accumulates narrative text.

    Supports both batch add (add_narrative) and streaming (append_chunk).
    Streaming mode filters out ``<state_update>`` JSON blocks so only clean
    narrative is shown to the player.
    """

    scroll_y = NumericProperty(0)

    # Tag used by LLM to separate narrative from state delta.
    _STATE_TAG = "<state_update>"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        theme = current_theme()
        # Painted onto the inner layout so the scroll content reads on the
        # theme background; ScrollView itself remains transparent.
        self._layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(8), dp(4)],
            spacing=dp(4),
        )
        add_background(self._layout, color=theme.bg)
        self._layout.bind(minimum_height=self._layout.setter("height"))
        self.add_widget(self._layout)

        # Current streaming label (for append_chunk).
        self._streaming_label: Label | None = None
        self._streaming_text: str = ""
        self._state_tag_seen: bool = False  # True once <state_update> appears

    def add_narrative(self, text: str, turn: int = 0) -> None:
        """Append a narrative block.

        If there is an active streaming label, it is removed and replaced by
        this clean text (the streaming label contained raw LLM output that may
        have been partially displayed).
        """
        theme = current_theme()

        # Remove the streaming label — it will be replaced by the clean text.
        if self._streaming_label is not None:
            self._layout.remove_widget(self._streaming_label)
            self._streaming_label = None

        if turn > 0:
            header = f"[color={rgba_to_hex(theme.text_hint)}]── 第 {turn} 回合 ──[/color]"
            lbl_header = Label(
                text=header,
                markup=True,
                font_size=dp(12),
                size_hint_y=None,
                height=dp(20),
                halign="left",
                valign="middle",
                color=theme.text_hint,
            )
            lbl_header.bind(width=lambda *a: lbl_header.setter("text_size")(lbl_header, (lbl_header.width, None)))
            self._layout.add_widget(lbl_header)

        if text:
            lbl = Label(
                text=text,
                markup=False,
                font_size=dp(14),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=theme.text,
            )
            lbl.bind(width=lambda *a: lbl.setter("text_size")(lbl, (lbl.width, None)))
            lbl.bind(texture_size=lbl.setter("size"))
            self._layout.add_widget(lbl)

        # Clear streaming state.
        self._streaming_text = ""
        self._state_tag_seen = False

        # Auto-scroll to bottom.
        self.scroll_y = 0

    def append_chunk(self, text: str) -> None:
        """Append a streaming text chunk to the current label.

        Creates a new label on first chunk, then updates it incrementally.
        This gives a typewriter-style streaming effect.

        Filters out ``<state_update>`` blocks: once the tag is detected,
        no further chunks are displayed (they are silently consumed).
        """
        # If we've already seen the state tag, silently ignore all subsequent chunks.
        if self._state_tag_seen:
            return

        # Check if this chunk (or accumulated text) contains the state tag.
        prospective = self._streaming_text + text
        tag_pos = prospective.find(self._STATE_TAG)
        if tag_pos >= 0:
            # Only display text before the tag.
            clean = prospective[:tag_pos].rstrip()
            self._state_tag_seen = True
            if not clean:
                # Entirely state_update; remove the streaming label if it's empty.
                if self._streaming_label is not None and not self._streaming_text:
                    self._layout.remove_widget(self._streaming_label)
                    self._streaming_label = None
                return
            # Show only the narrative portion.
            self._streaming_text = clean
            if self._streaming_label is not None:
                self._streaming_label.text = clean
            self.scroll_y = 0
            return

        theme = current_theme()
        if self._streaming_label is None:
            # Create a new label for streaming.
            self._streaming_label = Label(
                text="",
                markup=False,
                font_size=dp(14),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=theme.text,
            )
            self._streaming_label.bind(
                width=lambda *a: self._streaming_label.setter("text_size")(
                    self._streaming_label, (self._streaming_label.width, None)
                )
            )
            self._streaming_label.bind(texture_size=self._streaming_label.setter("size"))
            self._layout.add_widget(self._streaming_label)
            self._streaming_text = ""

        self._streaming_text += text
        self._streaming_label.text = self._streaming_text

        # Auto-scroll to bottom.
        self.scroll_y = 0

    def finalize_stream(self) -> None:
        """Called when streaming ends. Finalize the current streaming label."""
        # The streaming label is already in the layout with full text.
        # Just reset the streaming state so next narrative starts fresh.
        self._streaming_label = None
        self._streaming_text = ""
        self._state_tag_seen = False

    def add_info(self, text: str) -> None:
        """Append a dim info line."""
        theme = current_theme()
        lbl = Label(
            text=f"[color={rgba_to_hex(theme.text_hint)}]{text}[/color]",
            markup=True,
            font_size=dp(12),
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
            color=theme.text_hint,
        )
        lbl.bind(width=lambda *a: lbl.setter("text_size")(lbl, (lbl.width, None)))
        self._layout.add_widget(lbl)
        self.scroll_y = 0

    def clear(self) -> None:
        self._layout.clear_widgets()
        self._streaming_label = None
        self._streaming_text = ""
        self._state_tag_seen = False
