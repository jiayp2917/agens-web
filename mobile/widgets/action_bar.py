"""Bottom action bar focused on D typed action input."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from theme import add_paper_background, current_theme, themed_button


class GameActionBar(BoxLayout):
    """Bottom bar with text input as the primary game action.

    NOTE: Named GameActionBar to avoid collision with Kivy's built-in
    ActionBar (kivy.uix.actionbar.ActionBar) which has background_color,
    background_image etc. that Kivy's style.kv tries to apply.

    Events:
        on_action(text) — user submitted typed action
        on_command(cmd) — user tapped "more" or another exposed command
    """

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(82),
            spacing=dp(4),
            padding=[dp(8), dp(6)],
            **kwargs,
        )
        add_paper_background(self, color=(1.0, 0.973, 0.941, 0.90))

        self.preview_label = Label(
            text="当前输入预览：",
            font_size=dp(11),
            color=theme.text_secondary,
            size_hint_y=None,
            height=dp(18),
            halign="left",
            valign="middle",
        )
        self.preview_label.bind(width=lambda *_a: self.preview_label.setter("text_size")(self.preview_label, (self.preview_label.width, None)))
        self.add_widget(self.preview_label)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(6))

        self.more_btn = themed_button(
            "更多",
            font_size=dp(13),
            size_hint=(None, None),
            width=dp(58),
            height=dp(44),
        )
        self.more_btn.bind(on_release=lambda _: self._on_command("more"))
        row.add_widget(self.more_btn)

        self.text_input = TextInput(
            hint_text="D. 自行键入行动...",
            multiline=False,
            font_size=dp(14),
            background_color=theme.input_bg,
            foreground_color=theme.text,
            cursor_color=theme.primary,
            hint_text_color=theme.text_hint,
        )
        self.text_input.bind(text=self._on_text_changed)
        self.text_input.bind(on_text_validate=self._on_submit)
        row.add_widget(self.text_input)

        self.send_btn = themed_button(
            "发送",
            font_size=dp(13),
            size_hint=(None, None),
            width=dp(58),
            height=dp(44),
        )
        self.send_btn.bind(on_release=lambda _: self._on_submit(None))
        row.add_widget(self.send_btn)
        self.add_widget(row)
        self.bottom_spacer = BoxLayout(size_hint_y=None, height=0)
        self.add_widget(self.bottom_spacer)

        # State.
        self._combat_mode = False

        # Callbacks.
        self.on_action = None
        self.on_command = None

    def set_combat_mode(self, in_combat: bool) -> None:
        """Adjust the input hint while keeping typed play available."""
        theme = current_theme()
        self._combat_mode = in_combat
        if in_combat:
            self.text_input.hint_text = "战斗中，输入攻击、防御、逃跑或施展功法..."
            self.text_input.disabled = False
            self.send_btn.text = "发送"
        else:
            self.apply_choices_mode()
        # Re-apply theme colors so hint change doesn't dim the input.
        self.text_input.background_color = theme.input_bg
        self.text_input.foreground_color = theme.text
        self.text_input.cursor_color = theme.primary
        self.text_input.hint_text_color = theme.text_hint

    def apply_choices_mode(self) -> None:
        """Apply the single A/B/C choices + D typed-input behavior."""
        if self._combat_mode:
            return
        self.text_input.hint_text = "D. 自行键入行动..."
        self.text_input.disabled = False
        self.send_btn.text = "发送"

    def _on_text_changed(self, instance, text: str) -> None:
        preview = text.strip()
        self.preview_label.text = f"当前输入预览：{preview[:48]}" if preview else "当前输入预览："

    def _on_submit(self, instance) -> None:
        text = self.text_input.text.strip()
        if not text:
            return
        self.text_input.text = ""
        if self.on_action:
            self.on_action(text)

    def _on_command(self, cmd: str) -> None:
        if self.on_command:
            self.on_command(cmd)
