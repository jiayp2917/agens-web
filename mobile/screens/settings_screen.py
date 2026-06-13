"""Settings screen — API Key, Base URL, Model configuration, and theme picker."""

from __future__ import annotations

import os

from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from service.settings_store import (
    apply_settings_to_env,
    load_model_config,
    load_settings,
    save_model_config,
    save_settings,
)
from theme import (
    THEME_KEY,
    THEMES,
    add_background,
    current_theme,
    rgba_to_hex,
    themed_button,
)
from theme import (
    set_theme as set_active_theme,
)

# Preset providers: (display_name, base_url, default_model)
PRESETS = [
    ("Agnes Flash (内置)", "https://apihub.agnes-ai.com/v1", "agnes-2.0-flash"),
    ("Agnes 2.0", "https://apihub.agnes-ai.com/v1", "agnes-2.0"),
    ("Agnes 1.5", "https://apihub.agnes-ai.com/v1", "agnes-1.5"),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    ("Ollama (本地)", "http://10.0.2.2:11434/v1", "qwen2.5"),
    ("自部署", "", ""),
]

PRESET_NAMES = [p[0] for p in PRESETS]

# Map preset display name → (base_url, model)
PRESET_MAP = {p[0]: (p[1], p[2]) for p in PRESETS}

# Theme picker entries: (display_name, theme_key, preview_color)
THEME_CHOICES = [
    ("宣纸白", "white", (0.322, 0.455, 0.427, 1)),
    ("暗夜", "black", (0.478, 0.678, 0.620, 1)),
    ("墨绿", "green", (0.227, 0.361, 0.259, 1)),
]

GAME_MODE_CHOICES = [("高自由度", "high"), ("中自由度", "mid"), ("低自由度", "low")]


def _color_swatch(color, size=None):
    """Small square filled with `color` — used as theme preview indicator."""
    if size is None:
        size = dp(20)
    sw = Widget(size_hint_x=None, width=size, size_hint_y=None, height=size)
    with sw.canvas.before:
        Color(*color)
        sw._rect = Rectangle(pos=sw.pos, size=sw.size)
    sw.bind(
        pos=lambda _w, _v, r=sw._rect: setattr(r, "pos", _v),
        size=lambda _w, _v, r=sw._rect: setattr(r, "size", _v),
    )
    return sw


class SettingsScreen(Screen):
    """Settings form for API Key, Base URL, Model, and theme selection."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        theme = current_theme()
        add_background(self, color=theme.bg)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(16)],
            spacing=dp(8),
        )

        # Title.
        layout.add_widget(Label(
            text="[b]设置[/b]",
            markup=True,
            font_size=dp(18),
            size_hint_y=None,
            height=dp(36),
            color=theme.text,
        ))

        # Built-in key status.
        self.lbl_key_status = Label(
            text="",
            markup=True,
            font_size=dp(12),
            size_hint_y=None,
            height=dp(22),
            color=theme.success_color,
        )
        layout.add_widget(self.lbl_key_status)

        # Preset provider spinner.
        layout.add_widget(Label(
            text="服务商预设 (自动填入 Base URL):",
            font_size=dp(13),
            halign="left",
            size_hint_y=None,
            height=dp(24),
            color=theme.text,
        ))
        self.spinner_preset = Spinner(
            text=PRESET_NAMES[0],
            values=PRESET_NAMES,
            size_hint_y=None,
            height=dp(40),
            font_size=dp(14),
            background_color=theme.input_bg,
            color=theme.text,
        )
        self.spinner_preset.bind(text=self._on_preset_changed)
        layout.add_widget(self.spinner_preset)

        # API Key.
        layout.add_widget(Label(
            text="API Key (本次启动临时使用，不写入磁盘):",
            font_size=dp(13),
            halign="left",
            size_hint_y=None,
            height=dp(24),
            color=theme.text,
        ))
        self.input_api_key = TextInput(
            hint_text="sk-... (留空使用内置Key)",
            multiline=False,
            password=True,
            font_size=dp(14),
            size_hint_y=None,
            height=dp(40),
            background_color=theme.input_bg,
            foreground_color=theme.text,
            cursor_color=theme.primary,
            hint_text_color=theme.text_hint,
        )
        layout.add_widget(self.input_api_key)

        # Base URL.
        layout.add_widget(Label(
            text="Base URL:",
            font_size=dp(13),
            halign="left",
            size_hint_y=None,
            height=dp(24),
            color=theme.text,
        ))
        self.input_base_url = TextInput(
            hint_text="https://apihub.agnes-ai.com/v1",
            multiline=False,
            font_size=dp(14),
            size_hint_y=None,
            height=dp(40),
            background_color=theme.input_bg,
            foreground_color=theme.text,
            cursor_color=theme.primary,
            hint_text_color=theme.text_hint,
        )
        layout.add_widget(self.input_base_url)

        # Custom model input.
        layout.add_widget(Label(
            text="Model 名称 (覆盖预设默认):",
            font_size=dp(11),
            halign="left",
            size_hint_y=None,
            height=dp(20),
            color=theme.text_secondary,
        ))
        self.input_custom_model = TextInput(
            hint_text="留空使用预设的默认模型",
            multiline=False,
            font_size=dp(14),
            size_hint_y=None,
            height=dp(36),
            background_color=theme.input_bg,
            foreground_color=theme.text,
            cursor_color=theme.primary,
            hint_text_color=theme.text_hint,
        )
        layout.add_widget(self.input_custom_model)

        # Bind Enter key to advance focus / save.
        def _focus_base(inst):
            self.input_base_url.focus = True

        def _focus_model(inst):
            self.input_custom_model.focus = True

        self.input_api_key.bind(on_text_validate=_focus_base)
        self.input_base_url.bind(on_text_validate=_focus_model)
        self.input_custom_model.bind(
            on_text_validate=lambda inst: self._on_save(None)
        )

        # ---- Theme picker ----
        layout.add_widget(Label(
            text="主题颜色:",
            font_size=dp(13),
            halign="left",
            size_hint_y=None,
            height=dp(24),
            color=theme.text,
        ))
        self._theme_buttons: dict[str, object] = {}
        self._selected_theme = current_theme_value()
        theme_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )
        for label_text, theme_name, _preview_color in THEME_CHOICES:
            btn = themed_button(label_text, font_size=dp(13))
            btn.bind(
                on_release=lambda _inst, tn=theme_name: self._on_theme_pick(tn)
            )
            self._theme_buttons[theme_name] = btn
            theme_row.add_widget(btn)
        layout.add_widget(theme_row)

        layout.add_widget(Label(
            text="游玩模式:",
            font_size=dp(13),
            halign="left",
            size_hint_y=None,
            height=dp(24),
            color=theme.text,
        ))
        self._selected_game_mode = "high"
        self._mode_buttons: dict[str, object] = {}
        mode_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8),
        )
        for label_text, mode in GAME_MODE_CHOICES:
            btn = themed_button(label_text, font_size=dp(12))
            btn.bind(on_release=lambda _inst, m=mode: self._on_mode_pick(m))
            self._mode_buttons[mode] = btn
            mode_row.add_widget(btn)
        layout.add_widget(mode_row)

        # Spacer.
        layout.add_widget(Label(size_hint_y=None, height=dp(8)))

        # Buttons.
        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8),
        )
        save_btn = themed_button("保存", font_size=dp(14))
        back_btn = themed_button("返回游戏", font_size=dp(14))

        save_btn.bind(on_release=self._on_save)
        back_btn.bind(on_release=self._on_back)

        btn_row.add_widget(save_btn)
        btn_row.add_widget(back_btn)
        layout.add_widget(btn_row)

        # Status label.
        self.status_label = Label(
            text="",
            font_size=dp(12),
            size_hint_y=None,
            height=dp(24),
            color=theme.success_color,
        )
        layout.add_widget(self.status_label)

        self.add_widget(layout)

        # Highlight the currently active theme button.
        self._refresh_theme_button_highlight()

    def _on_preset_changed(self, spinner, text) -> None:
        """Auto-fill Base URL and Model when a preset is selected."""
        preset = PRESET_MAP.get(text)
        if preset is None:
            return
        base_url, model = preset
        if base_url:
            self.input_base_url.text = base_url
        if model:
            self.input_custom_model.hint_text = f"默认: {model}"

    def on_enter(self, *args):
        """Load current settings into form."""
        data = load_settings()
        self.input_api_key.text = ""
        self.input_base_url.text = data.get("base_url", "https://apihub.agnes-ai.com/v1")

        # Load model config.
        model_cfg = load_model_config()
        custom_model = model_cfg.get("custom_model", "")
        selected_preset = model_cfg.get("selected_preset", PRESET_NAMES[0])

        self.spinner_preset.text = selected_preset
        self.input_custom_model.text = custom_model
        self.status_label.text = ""

        # Show built-in key status.
        theme = current_theme()
        success_hex = rgba_to_hex(theme.success_color)
        warn_hex = rgba_to_hex(theme.accent)
        has_user_key = bool(os.environ.get("AGNES_API_KEY"))
        if has_user_key:
            self.lbl_key_status.text = f"[color={success_hex}]使用自定义 API Key[/color]"
        else:
            self.lbl_key_status.text = f"[color={warn_hex}]使用内置 API Key (可直接游玩)[/color]"

        # Sync theme picker with current selection.
        self._selected_theme = data.get(THEME_KEY, "white")
        self._selected_game_mode = data.get("game_mode", "high")
        self._refresh_theme_button_highlight()
        self._refresh_mode_button_highlight()

    def _on_theme_pick(self, theme_name: str) -> None:
        """Update local selection — the actual save happens in _on_save."""
        if theme_name not in THEMES:
            return
        self._selected_theme = theme_name
        self._refresh_theme_button_highlight()

    def _refresh_theme_button_highlight(self) -> None:
        """Tint the active theme button with accent color, others with primary."""
        theme = current_theme()
        for name, btn in self._theme_buttons.items():
            target = theme.accent if name == self._selected_theme else theme.button_bg
            btn._bg_rect_color.rgba = target

    def _on_mode_pick(self, mode: str) -> None:
        self._selected_game_mode = mode
        self._refresh_mode_button_highlight()

    def _refresh_mode_button_highlight(self) -> None:
        theme = current_theme()
        for name, btn in self._mode_buttons.items():
            target = theme.accent if name == self._selected_game_mode else theme.button_bg
            btn._bg_rect_color.rgba = target

    def _on_save(self, instance) -> None:
        # Resolve effective model: custom input > preset default.
        custom_model = self.input_custom_model.text.strip()
        preset_name = self.spinner_preset.text
        preset = PRESET_MAP.get(preset_name, ("", ""))
        default_model = preset[1] if preset else "agnes-2.0-flash"
        effective_model = custom_model or default_model

        data = {
            "api_key": self.input_api_key.text.strip(),
            "base_url": self.input_base_url.text.strip() or "https://apihub.agnes-ai.com/v1",
            "model": effective_model,
            THEME_KEY: self._selected_theme,
            "game_mode": self._selected_game_mode,
        }
        apply_settings_to_env(data)
        save_settings(data)

        # Apply theme immediately so the user sees the change.
        set_active_theme(self._selected_theme)
        from kivy.core.window import Window
        Window.clearcolor = current_theme().bg

        # Save model config separately.
        save_model_config({
            "selected_preset": preset_name,
            "custom_model": custom_model,
        })

        # Update key status.
        theme = current_theme()
        success_hex = rgba_to_hex(theme.success_color)
        warn_hex = rgba_to_hex(theme.accent)
        if os.environ.get("AGNES_API_KEY"):
            self.lbl_key_status.text = f"[color={success_hex}]使用自定义 API Key[/color]"
        else:
            self.lbl_key_status.text = f"[color={warn_hex}]使用内置 API Key (可直接游玩)[/color]"

        self.status_label.text = f"[color={success_hex}]已保存[/color]"

    def _on_back(self, instance) -> None:
        self._on_save(None)
        self.manager.current = "game"


def current_theme_value() -> str:
    """Read the active theme name from settings (defaults to 'white')."""
    try:
        data = load_settings()
        return data.get(THEME_KEY, "white")
    except Exception:
        return "white"
