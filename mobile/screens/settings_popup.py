"""Settings popup for the Android/Kivy home and tools screens."""

from __future__ import annotations

from audio_manager import AudioManager
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from service.model_presets import DEFAULT_PRESET, MODEL_PRESETS
from service.settings_store import (
    active_model_summary,
    apply_settings_to_env,
    has_saved_api_key,
    load_model_config,
    load_settings,
    save_api_key,
    save_model_config,
    save_settings,
)
from theme import THEME_KEY, add_paper_background, current_theme, set_theme, themed_button, themed_popup

THEME_CHOICES = [("宣纸白", "white"), ("墨绿", "green"), ("暗夜", "black")]


class SettingsPopup:
    """Build and manage the settings popup without owning the home screen."""

    def __init__(self, audio: AudioManager, on_audio_changed=None):
        self.audio = audio
        self.on_audio_changed = on_audio_changed
        self.popup = None
        self._selected_theme = "white"
        self._bgm_enabled = True
        self._sfx_enabled = True
        self._feedback = None
        self._theme_buttons = {}
        self._audio_buttons = {}

    def open(self):
        theme = current_theme()
        data = load_settings()
        model_cfg = load_model_config()
        self.audio.apply_settings(data)
        self._selected_theme = data.get(THEME_KEY, "white")
        self._bgm_enabled = self.audio.bgm_enabled
        self._sfx_enabled = self.audio.sfx_enabled

        outer = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        add_paper_background(outer, color=theme.surface)
        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        form.bind(minimum_height=form.setter("height"))

        preset_names = [preset[0] for preset in MODEL_PRESETS]
        preset = model_cfg.get("selected_preset", preset_names[0])
        self.spinner_preset = _spinner(preset if preset in preset_names else preset_names[0], preset_names, theme)
        self.input_base_url = _input(data.get("base_url", DEFAULT_PRESET[1]), theme)
        self.input_model = _input(data.get("model", model_cfg.get("custom_model", DEFAULT_PRESET[2])), theme)
        key_hint = "留空保留已保存的 Key" if has_saved_api_key() else "输入后保存到应用私有目录"
        self.input_api_key = _input("", theme, password=True, hint=key_hint)
        self.spinner_preset.bind(text=self._on_preset_changed)

        _add_field(form, "大模型连接", self.spinner_preset, theme)
        _add_field(form, "API Base URL", self.input_base_url, theme)
        _add_field(form, "Model", self.input_model, theme)
        _add_field(form, "API Key", self.input_api_key, theme)
        _add_field(
            form,
            "主题色",
            self._segmented(THEME_CHOICES, self._selected_theme, self._pick_theme, self._theme_buttons),
            theme,
        )
        _add_field(form, "音频", self._audio_segments(), theme)
        self._feedback = Label(
            text=active_model_summary(data),
            font_size=dp(12),
            color=theme.success_color,
            size_hint_y=None,
            height=dp(48),
            halign="left",
            valign="middle",
        )
        self._feedback.bind(width=lambda *_a: self._feedback.setter("text_size")(self._feedback, (self._feedback.width, None)))
        form.add_widget(self._feedback)
        scroll.add_widget(form)
        outer.add_widget(scroll)

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        save_btn = themed_button("保存设置", font_size=dp(13))
        close_btn = themed_button("关闭", font_size=dp(13))
        save_btn.bind(on_release=lambda _: self._save())
        close_btn.bind(on_release=lambda _: self.popup.dismiss() if self.popup else None)
        row.add_widget(close_btn)
        row.add_widget(save_btn)
        outer.add_widget(row)

        self.popup = themed_popup("设置", outer, size_hint=(0.88, 0.78), auto_dismiss=False)
        self.popup.open()
        return self.popup

    def _segmented(self, choices, selected, callback, button_store) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(6))
        theme = current_theme()
        button_store.clear()
        for label, value in choices:
            btn = themed_button(label, font_size=dp(11))
            button_store[value] = btn
            if value == selected:
                btn._bg_rect_color.rgba = theme.primary[0], theme.primary[1], theme.primary[2], 0.28
            btn.bind(on_release=lambda _inst, v=value: callback(v))
            row.add_widget(btn)
        return row

    def _audio_segments(self) -> BoxLayout:
        choices = [
            (f"BGM {'开' if self._bgm_enabled else '关'}", "bgm"),
            (f"音效 {'开' if self._sfx_enabled else '关'}", "sfx"),
            ("静音", "mute"),
        ]
        return self._segmented(choices, "", self._pick_audio, self._audio_buttons)

    def _pick_theme(self, value: str) -> None:
        self._selected_theme = value
        set_theme(value)
        Window.clearcolor = current_theme().bg
        self._refresh_controls()
        self._set_feedback("主题已切换，保存后下次启动继续使用。")

    def _pick_audio(self, value: str) -> None:
        if value == "bgm":
            self._bgm_enabled = not self._bgm_enabled
        elif value == "sfx":
            self._sfx_enabled = not self._sfx_enabled
        elif value == "mute":
            self._bgm_enabled = False
            self._sfx_enabled = False
        self.audio.bgm_enabled = self._bgm_enabled
        self.audio.sfx_enabled = self._sfx_enabled
        if self._bgm_enabled:
            self.audio.play_bgm("default")
        else:
            self.audio.stop_bgm()
        self._refresh_controls()
        if self.on_audio_changed:
            self.on_audio_changed()
        self._set_feedback("音频设置已应用，保存后下次启动继续使用。")

    def _refresh_controls(self) -> None:
        theme = current_theme()
        for value, btn in self._theme_buttons.items():
            btn.color = theme.button_text
            btn._bg_rect_color.rgba = (
                (theme.primary[0], theme.primary[1], theme.primary[2], 0.28)
                if value == self._selected_theme
                else theme.button_bg
            )
        labels = {
            "bgm": f"BGM {'开' if self._bgm_enabled else '关'}",
            "sfx": f"音效 {'开' if self._sfx_enabled else '关'}",
            "mute": "静音",
        }
        for value, btn in self._audio_buttons.items():
            btn.text = labels[value]
            btn.color = theme.button_text
            btn._bg_rect_color.rgba = theme.button_bg
        if not self._bgm_enabled and not self._sfx_enabled and "mute" in self._audio_buttons:
            self._audio_buttons["mute"]._bg_rect_color.rgba = theme.primary[0], theme.primary[1], theme.primary[2], 0.28
        elif self._bgm_enabled and "bgm" in self._audio_buttons:
            self._audio_buttons["bgm"]._bg_rect_color.rgba = theme.primary[0], theme.primary[1], theme.primary[2], 0.20

    def _set_feedback(self, text: str) -> None:
        if self._feedback is not None:
            self._feedback.text = text

    def _on_preset_changed(self, spinner, text: str) -> None:
        for name, base_url, model in MODEL_PRESETS:
            if name == text:
                if base_url:
                    self.input_base_url.text = base_url
                if model:
                    self.input_model.text = model
                break

    def _save(self) -> None:
        entered_key = self.input_api_key.text.strip()
        data = load_settings()
        data.update({
            "base_url": self.input_base_url.text.strip() or DEFAULT_PRESET[1],
            "model": self.input_model.text.strip() or DEFAULT_PRESET[2],
            THEME_KEY: self._selected_theme,
            "bgm_enabled": self._bgm_enabled,
            "sfx_enabled": self._sfx_enabled,
        })
        if entered_key:
            save_api_key(entered_key)
            runtime_data = {**data, "api_key": entered_key}
        else:
            runtime_data = dict(data)
        save_settings(data)
        save_model_config({
            "selected_preset": self.spinner_preset.text,
            "custom_model": self.input_model.text.strip(),
        })
        apply_settings_to_env(runtime_data)
        set_theme(self._selected_theme)
        Window.clearcolor = current_theme().bg
        self.audio.apply_settings(runtime_data)
        if self.on_audio_changed:
            self.on_audio_changed()
        self._set_feedback("设置已保存。\n" + active_model_summary(runtime_data))


def _input(text: str, theme, password: bool = False, hint: str = "") -> TextInput:
    return TextInput(
        text=text,
        hint_text=hint,
        password=password,
        multiline=False,
        font_size=dp(13),
        size_hint_y=None,
        height=dp(38),
        background_color=theme.input_bg,
        foreground_color=theme.text,
        cursor_color=theme.primary,
        hint_text_color=theme.text_hint,
    )


def _spinner(text: str, values: list[str], theme) -> Spinner:
    return Spinner(
        text=text,
        values=values,
        font_size=dp(13),
        size_hint_y=None,
        height=dp(38),
        background_color=theme.input_bg,
        color=theme.text,
    )


def _add_field(form: BoxLayout, label: str, widget: Widget, theme) -> None:
    form.add_widget(Label(
        text=label,
        font_size=dp(12),
        color=theme.text_secondary,
        halign="left",
        size_hint_y=None,
        height=dp(20),
    ))
    form.add_widget(widget)

