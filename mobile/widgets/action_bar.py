"""Bottom action bar — text input + quick-action buttons + combat mode."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from theme import add_background, current_theme, themed_button


class GameActionBar(BoxLayout):
    """Bottom bar with quick-action buttons and text input.

    Switches between normal mode and combat mode.

    NOTE: Named GameActionBar to avoid collision with Kivy's built-in
    ActionBar (kivy.uix.actionbar.ActionBar) which has background_color,
    background_image etc. that Kivy's style.kv tries to apply.

    Events:
        on_action(text)     — user submitted free-text action
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
            height=dp(112),
            **kwargs,
        )
        add_background(self, color=theme.surface)

        # Button row inside a scroll view.
        self._btn_row = GridLayout(
            cols=5,
            size_hint_y=None,
            height=dp(64),
            spacing=[dp(4), dp(4)],
            padding=[dp(2), dp(4)],
        )
        self._build_normal_buttons()
        self.add_widget(self._btn_row)

        # Input row.
        input_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(4),
            padding=[dp(4), dp(2)],
        )
        self.text_input = TextInput(
            hint_text="输入行动...",
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
        self._game_mode = "high"

        # Callbacks.
        self.on_action = None
        self.on_command = None

    def _build_normal_buttons(self) -> None:
        """Build normal mode buttons."""
        self._btn_row.clear_widgets()
        for label, cmd in self.BUTTONS:
            btn = themed_button(label, font_size=dp(10))
            btn.bind(on_release=lambda instance, c=cmd: self._on_command(c))
            self._btn_row.add_widget(btn)

    def set_combat_mode(self, in_combat: bool) -> None:
        """Switch button layout for combat vs normal mode."""
        theme = current_theme()
        self._combat_mode = in_combat
        if in_combat:
            self.text_input.hint_text = "战斗中 — 使用战斗按钮操作"
            self.text_input.disabled = True
        else:
            self.apply_game_mode(self._game_mode)
        # Re-apply theme colors so hint change doesn't dim the input.
        self.text_input.background_color = theme.input_bg
        self.text_input.foreground_color = theme.text
        self.text_input.cursor_color = theme.primary
        self.text_input.hint_text_color = theme.text_hint

    def apply_game_mode(self, mode: str) -> None:
        """Apply high/mid/low freedom input behavior."""
        self._game_mode = mode
        if self._combat_mode:
            return
        if mode == "low":
            self.text_input.text = ""
            self.text_input.hint_text = "请选择上方行动"
            self.text_input.disabled = True
            self.send_btn.text = "定"
        elif mode == "mid":
            self.text_input.hint_text = "也可以自由输入行动..."
            self.text_input.disabled = False
            self.send_btn.text = "送"
        else:
            self.text_input.hint_text = "输入任意行动..."
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
