"""Scrollable narrative text display widget with streaming support."""

from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from theme import add_background, current_theme, rgba_to_hex, themed_button


def _bind_wrapped_height(widget, min_height: float = 0) -> None:
    """Wrap text to widget width and grow height from rendered texture."""

    def update_text_size(instance, width) -> None:
        instance.text_size = (max(1, width), None)

    def update_height(instance, texture_size) -> None:
        instance.height = max(min_height, texture_size[1] + dp(2))

    widget.bind(width=update_text_size, texture_size=update_height)


def _soft_wrap_cjk(text: str, columns: int = 28) -> str:
    """Insert conservative line breaks for long CJK-heavy mobile text."""
    wrapped: list[str] = []
    break_chars = "，。；、！？：,.!?;:"
    for paragraph in text.splitlines() or [""]:
        line = paragraph.strip()
        while len(line) > columns:
            cut = max(line.rfind(ch, 0, columns + 1) for ch in break_chars)
            if cut < max(10, columns // 2):
                cut = columns
            else:
                cut += 1
            wrapped.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        wrapped.append(line)
    return "\n".join(wrapped)


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
            size_hint_x=1,
            size_hint_y=None,
            padding=[dp(8), dp(4)],
            spacing=dp(4),
        )
        add_background(self._layout, color=theme.bg)
        self._layout.bind(minimum_height=self._layout.setter("height"))
        self.bind(width=lambda _inst, width: setattr(self._layout, "width", width))
        self.add_widget(self._layout)

        # Current streaming label (for append_chunk).
        self._streaming_label: Label | None = None
        self._streaming_text: str = ""
        self._state_tag_seen: bool = False  # True once <state_update> appears
        self.on_choice = None
        self._choices_box: BoxLayout | None = None

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
            _bind_wrapped_height(lbl_header, dp(20))
            self._layout.add_widget(lbl_header)

        if text:
            lbl = Label(
                text=_soft_wrap_cjk(text),
                markup=False,
                font_size=dp(14),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=theme.text,
            )
            _bind_wrapped_height(lbl)
            self._layout.add_widget(lbl)

        # Clear streaming state.
        self._streaming_text = ""
        self._state_tag_seen = False
        self.clear_choices()

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
                self._streaming_label.text = _soft_wrap_cjk(clean)
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
            _bind_wrapped_height(self._streaming_label)
            self._layout.add_widget(self._streaming_label)
            self._streaming_text = ""

        self._streaming_text += text
        self._streaming_label.text = _soft_wrap_cjk(self._streaming_text)

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
        display_text = _soft_wrap_cjk(text, columns=30)
        lbl = Label(
            text=f"[color={rgba_to_hex(theme.text_hint)}]{display_text}[/color]",
            markup=True,
            font_size=dp(12),
            size_hint_y=None,
            halign="left",
            valign="top",
            color=theme.text_hint,
        )
        _bind_wrapped_height(lbl, dp(20))
        self._layout.add_widget(lbl)
        self.scroll_y = 0

    def render_choices(self, choices: list[str]) -> None:
        """Render suggested action choices below the current narrative."""
        self.clear_choices()
        if not choices:
            return
        theme = current_theme()
        box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(3),
            padding=[0, dp(5), 0, 0],
        )
        box.bind(minimum_height=box.setter("height"))
        labels = ("A", "B", "C")
        for index, choice in enumerate(choices[:3]):
            label = f"{labels[index]}. {choice}"
            label = _soft_wrap_cjk(label, columns=30)
            btn = themed_button(label, font_size=dp(11), size_hint_y=None, height=dp(32))
            btn.halign = "left"
            btn.valign = "middle"
            _bind_wrapped_height(btn, dp(32))
            btn.bind(on_release=lambda _inst, c=choice: self._emit_choice(c))
            box.add_widget(btn)
        hint = Label(
            text="[color={}]D. 自行键入行动[/color]".format(rgba_to_hex(theme.text_hint)),
            markup=True,
            font_size=dp(11),
            size_hint_y=None,
            height=dp(18),
            halign="left",
            valign="middle",
            color=theme.text_hint,
        )
        _bind_wrapped_height(hint, dp(18))
        box.add_widget(hint)
        self._choices_box = box
        self._layout.add_widget(box)
        self.scroll_y = 0

    def clear_choices(self) -> None:
        """Remove the current choices block."""
        if self._choices_box is not None:
            try:
                self._layout.remove_widget(self._choices_box)
            except Exception:
                pass
            self._choices_box = None

    def _emit_choice(self, choice: str) -> None:
        if self.on_choice:
            self.on_choice(choice)

    def clear(self) -> None:
        self._layout.clear_widgets()
        self._streaming_label = None
        self._streaming_text = ""
        self._state_tag_seen = False
        self._choices_box = None
