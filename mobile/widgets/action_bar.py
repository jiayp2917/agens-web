"""Bottom action bar — typed action input with compact utility commands."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from theme import add_background, current_theme, themed_button


class GameActionBar(BoxLayout):
    """Bottom bar with text input as the primary game action.

    NOTE: Named GameActionBar to avoid collision with Kivy's built-in
    ActionBar (kivy.uix.actionbar.ActionBar) which has background_color,
    background_image etc. that Kivy's style.kv tries to apply.

    Events:
        on_action(text)     — user submitted typed action
        on_command(cmd)     — user tapped a quick-action button
    """

    BUTTONS = [
        ("新游戏", "new"),
        ("重开", "restart"),
        ("设置", "settings"),
        ("存档", "save"),
        ("读档", "load"),
        ("状态", "status"),
        ("装备", "equipment"),
        ("背包", "inv"),
        ("功法", "skills"),
        ("任务", "quest"),
    ]

    def __init__(self, **kwargs):
        theme = current_theme()
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=dp(84),
            **kwargs,
        )
        add_background(self, color=theme.surface)

        # Compact horizontally scrolling tool row. This keeps Android portrait
        # layouts from overflowing while preserving every command.
        self._tool_scroll = ScrollView(
            size_hint_y=None,
            height=dp(40),
            do_scroll_x=True,
            do_scroll_y=False,
            bar_width=0,
            scroll_type=["content"],
        )
        self._btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            size_hint_x=None,
            spacing=dp(4),
            padding=[dp(2), dp(4)],
        )
        self._btn_row.bind(minimum_width=self._btn_row.setter("width"))
        self._build_normal_buttons()
        self._tool_scroll.add_widget(self._btn_row)
        self.add_widget(self._tool_scroll)

        # Input row.
        input_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(42),
            spacing=dp(4),
            padding=[dp(4), dp(2)],
        )
        self.text_input = TextInput(
            hint_text="D. 自行键入行动...",
            multiline=False,
            font_size=dp(14),
            background_color=theme.input_bg,
            foreground_color=theme.text,
            cursor_color=theme.primary,
            hint_text_color=theme.text_hint,
        )
        self.text_input.bind(on_text_validate=self._on_submit)

        self.send_btn = themed_button("送", font_size=dp(13), size_hint_x=None, width=dp(56))
        self.send_btn.bind(on_release=lambda _: self._on_submit(None))

        input_row.add_widget(self.text_input)
        input_row.add_widget(self.send_btn)
        self.add_widget(input_row)

        # State.
        self._combat_mode = False

        # Callbacks.
        self.on_action = None
        self.on_command = None

    def _build_normal_buttons(self) -> None:
        """Build normal mode buttons."""
        self._btn_row.clear_widgets()
        for label, cmd in self.BUTTONS:
            btn = themed_button(
                label,
                font_size=dp(11),
                size_hint=(None, None),
                width=dp(56),
                height=dp(32),
            )
            btn.bind(on_release=lambda instance, c=cmd: self._on_command(c))
            self._btn_row.add_widget(btn)

    def set_combat_mode(self, in_combat: bool) -> None:
        """Adjust the input hint while keeping typed play available."""
        theme = current_theme()
        self._combat_mode = in_combat
        if in_combat:
            self.text_input.hint_text = "战斗中，输入攻击、防御、逃跑或施展功法..."
            self.text_input.disabled = False
            self.send_btn.text = "送"
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
        self.send_btn.text = "送"

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
