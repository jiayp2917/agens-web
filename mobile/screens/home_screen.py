"""Home screen matching the Android ink-wash prototype."""

from __future__ import annotations

import os

from audio_manager import AudioManager
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from service.engine_adapter import EngineAdapter
from service.settings_store import load_settings, save_settings
from screens.settings_popup import SettingsPopup
from theme import (
    add_background,
    add_image_background,
    add_paper_background,
    add_scrim,
    current_theme,
    themed_button,
    themed_popup,
)


class HomeScreen(Screen):
    """Main menu with background art, BGM switch, and paper popups."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        self.audio = AudioManager()
        self._tutorial_page = 0
        self._bgm_enabled = True
        self._sfx_enabled = True
        self._popup = None

        self.root = FloatLayout()
        self._paint_background()
        self._build_content()
        self.add_widget(self.root)

    def on_enter(self, *args):
        data = load_settings()
        self.audio.apply_settings(data)
        self._bgm_enabled = self.audio.bgm_enabled
        self._sfx_enabled = self.audio.sfx_enabled
        self._play_menu_bgm()
        self._refresh_audio_button()

    def _paint_background(self) -> None:
        theme = current_theme()
        if os.environ.get("AGENS_REAL_CLICK_SIMPLE_RENDER") == "1":
            add_background(self.root, color=theme.bg)
        else:
            add_image_background(self.root, "ink_mountain_gate.png", fallback_color=theme.bg)
            add_scrim(self.root, color=(0.969, 0.953, 0.918, 0.36))

    def _build_content(self) -> None:
        theme = current_theme()

        self.btn_audio = themed_button("♪", font_size=dp(18), size_hint=(None, None), size=(dp(38), dp(38)))
        self.btn_audio.pos_hint = {"right": 0.94, "top": 0.96}
        self.btn_audio.bind(on_release=lambda _: self._toggle_bgm())
        self.root.add_widget(self.btn_audio)

        title_box = BoxLayout(
            orientation="vertical",
            size_hint=(0.74, None),
            height=dp(150),
            pos_hint={"center_x": 0.5, "top": 0.82},
            spacing=dp(8),
        )
        title = Label(
            text="[b]文字修仙\n模拟器[/b]",
            markup=True,
            font_size=dp(32),
            line_height=1.05,
            color=theme.text,
            halign="center",
            valign="middle",
        )
        title.bind(width=lambda *_a: title.setter("text_size")(title, (title.width, None)))
        title_box.add_widget(title)
        title_box.add_widget(Label(
            text="天道有常",
            font_size=dp(13),
            color=theme.error_color,
            size_hint_y=None,
            height=dp(24),
        ))
        self.root.add_widget(title_box)

        menu = BoxLayout(
            orientation="vertical",
            size_hint=(0.72, None),
            height=dp(292),
            pos_hint={"center_x": 0.5, "y": 0.07},
            spacing=dp(12),
        )
        buttons = [
            ("新游戏", self._on_new_game, dp(48)),
            ("读档", self._show_load_popup, dp(48)),
            ("教程", self._show_tutorial_popup, dp(48)),
            ("设置", self._show_settings_popup, dp(48)),
            ("退出", self._on_quit, dp(42)),
        ]
        for label, handler, height in buttons:
            btn = themed_button(label, font_size=dp(16), size_hint_y=None, height=height)
            btn.bind(on_release=lambda _inst, h=handler: h())
            menu.add_widget(btn)
        self.root.add_widget(menu)

    def _on_new_game(self) -> None:
        if self.manager:
            self.manager.current = "character_create"

    def _show_load_popup(self) -> None:
        theme = current_theme()
        outer = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        add_paper_background(outer, color=theme.surface)
        scroll = ScrollView(size_hint_y=1)
        slots = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7))
        slots.bind(minimum_height=slots.setter("height"))

        saves = self.adapter.list_saves() if self.adapter else []
        by_name = {item["name"]: item for item in saves if not item.get("error")}
        entries = [("自动存档", "autosave")] + [(f"档位{i}", f"slot_{i}") for i in range(1, 6)]
        for label, slot_name in entries:
            slots.add_widget(self._save_slot_row(label, slot_name, by_name.get(slot_name), theme))
        scroll.add_widget(slots)
        outer.add_widget(scroll)
        close_btn = themed_button("关闭", font_size=dp(13), size_hint_y=None, height=dp(38))
        outer.add_widget(close_btn)
        popup = themed_popup("读档", outer, size_hint=(0.88, 0.72), auto_dismiss=False)
        close_btn.bind(on_release=lambda _: popup.dismiss())
        self._popup = popup
        popup.open()

    def _save_slot_row(self, label: str, slot_name: str, info: dict | None, theme) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(58), spacing=dp(6))
        meta = "尚未创建存档"
        if info:
            meta = f"{info.get('char_name', '?')} · {info.get('realm', '?')} · 第 {info.get('turn_count', 0)} 回合"
        text = f"[b]{label}[/b]\n[color={_hex(theme.text_secondary)}]{meta}[/color]"
        lbl = Label(text=text, markup=True, font_size=dp(12), color=theme.text, halign="left", valign="middle", size_hint_x=0.58)
        lbl.bind(width=lambda *a: lbl.setter("text_size")(lbl, (lbl.width, None)))
        row.add_widget(lbl)
        load_btn = themed_button("读取", font_size=dp(11), size_hint_x=0.20)
        load_btn.disabled = info is None
        load_btn.opacity = 1.0 if info else 0.38
        load_btn.bind(on_release=lambda _: self._load_slot(slot_name))
        del_btn = themed_button("删除", font_size=dp(11), size_hint_x=0.20)
        del_btn.disabled = info is None or slot_name == "autosave"
        del_btn.opacity = 1.0 if (info and slot_name != "autosave") else 0.38
        del_btn.bind(on_release=lambda _: self._delete_slot(slot_name))
        row.add_widget(load_btn)
        row.add_widget(del_btn)
        return row

    def _load_slot(self, slot_name: str) -> None:
        if self.adapter:
            self.adapter.load(slot_name)
        if self._popup:
            self._popup.dismiss()
        if self.manager:
            self.manager.current = "game"

    def _delete_slot(self, slot_name: str) -> None:
        if self.adapter:
            self.adapter.delete_save(slot_name)
        if self._popup:
            self._popup.dismiss()
        self._show_load_popup()

    def _show_tutorial_popup(self) -> None:
        self._tutorial_page = 0
        self._open_tutorial_popup()

    def _open_tutorial_popup(self) -> None:
        theme = current_theme()
        page = _TUTORIAL_PAGES[self._tutorial_page]
        outer = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        add_paper_background(outer, color=theme.surface)
        title = Label(
            text=f"[b]教程 · {self._tutorial_page + 1}[/b]",
            markup=True,
            font_size=dp(18),
            color=theme.text,
            size_hint_y=None,
            height=dp(32),
        )
        outer.add_widget(title)
        content = Label(
            text=page,
            font_size=dp(14),
            color=theme.text_secondary,
            halign="left",
            valign="top",
        )
        content.bind(width=lambda *a: content.setter("text_size")(content, (content.width, None)))
        outer.add_widget(content)
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        prev_btn = themed_button("上一页", font_size=dp(13))
        next_btn = themed_button("下一页", font_size=dp(13))
        close_btn = themed_button("关闭", font_size=dp(13))
        prev_btn.disabled = self._tutorial_page == 0
        next_btn.disabled = self._tutorial_page == len(_TUTORIAL_PAGES) - 1
        prev_btn.bind(on_release=lambda _: self._turn_tutorial(-1))
        next_btn.bind(on_release=lambda _: self._turn_tutorial(1))
        close_btn.bind(on_release=lambda _: self._popup.dismiss() if self._popup else None)
        row.add_widget(prev_btn)
        row.add_widget(next_btn)
        row.add_widget(close_btn)
        outer.add_widget(row)
        if self._popup:
            self._popup.dismiss()
        self._popup = themed_popup("教程", outer, size_hint=(0.88, 0.55), auto_dismiss=False)
        self._popup.open()

    def _turn_tutorial(self, delta: int) -> None:
        self._tutorial_page = max(0, min(len(_TUTORIAL_PAGES) - 1, self._tutorial_page + delta))
        self._open_tutorial_popup()

    def _show_settings_popup(self) -> None:
        settings = SettingsPopup(self.audio, on_audio_changed=self._refresh_audio_button)
        self._popup = settings.open()

    def _toggle_bgm(self) -> None:
        enabled = self.audio.toggle_bgm()
        self._bgm_enabled = enabled
        data = load_settings()
        data["bgm_enabled"] = enabled
        save_settings(data)
        if enabled:
            self._play_menu_bgm()
        self._refresh_audio_button()

    def _refresh_audio_button(self) -> None:
        if hasattr(self, "btn_audio"):
            self.btn_audio.text = "♪" if self.audio.bgm_enabled else "♪/"
            self.btn_audio.opacity = 1.0 if self.audio.bgm_enabled else 0.55

    def _play_menu_bgm(self) -> None:
        # Alias routed through agens_novel.bgm — resolves to project-root
        # bgm.flac (or a track-specific alias when more files are added).
        self.audio.play_bgm("default")

    def _on_quit(self) -> None:
        from kivy.app import App
        App.get_running_app().stop()


def _hex(rgba) -> str:
    return f"{int(rgba[0] * 255):02x}{int(rgba[1] * 255):02x}{int(rgba[2] * 255):02x}"


_TUTORIAL_PAGES = [
    (
        "你将以自然语言行动，天道会根据选择生成回合叙事与状态变化。\n\n"
        "每回合显示 A/B/C 三个建议行动；D 为底部输入框，可自行键入任意行动。"
    ),
    (
        "境界依次为练气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。\n\n"
        "突破有失败风险，死亡后可以重新开始或读取存档。"
    ),
    (
        "AI 会保持世界逻辑、角色信息和后天选择之间的关联。\n\n"
        "随机事件会更真实，但结果不会脱离修仙小说的基本规则。"
    ),
]
