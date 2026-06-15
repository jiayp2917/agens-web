"""Character creation screen for the Android prototype."""

from __future__ import annotations

import random

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from service.engine_adapter import EngineAdapter
from theme import add_image_background, add_paper_background, add_scrim, current_theme, themed_button

from agens_novel.game.constants import (
    ATTRIBUTE_KEYS,
    ATTRIBUTE_LABELS,
    DEFAULT_ATTRIBUTES,
    DIFFICULTY_OPTIONS,
    FAMILY_BACKGROUNDS,
    SPECIAL_START_ATTRIBUTES,
    SPECIAL_START_CODE,
    SPECIAL_START_NAME,
    SPIRIT_ROOTS,
    TALENT_OPTIONS,
)

SPECIAL_TALENT = "天命道胎"
SPECIAL_FAMILY = "隐世仙族"
SPECIAL_ROOT = "混沌天灵根"


class CharacterCreateScreen(Screen):
    """Full-screen character creation form."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        self.attributes = dict(DEFAULT_ATTRIBUTES)
        self._result_panel = None
        self._attribute_widgets: dict[str, tuple[ProgressBar, Label]] = {}

        theme = current_theme()
        add_image_background(self, "ink_mountain_gate.png", fallback_color=theme.bg)
        add_scrim(self, color=(0.969, 0.953, 0.918, 0.58))
        root = BoxLayout(orientation="vertical", padding=[dp(14), dp(12)], spacing=dp(8))
        add_paper_background(root, color=(1.0, 0.973, 0.941, 0.86))

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        back_btn = themed_button("返回", font_size=dp(13), size_hint_x=0.28)
        back_btn.bind(on_release=lambda _: self._go_home())
        top.add_widget(back_btn)
        top.add_widget(Label(text="[b]创建角色[/b]", markup=True, font_size=dp(22), color=theme.text, size_hint_x=0.72))
        root.add_widget(top)

        scroll = ScrollView()
        self.form = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(8),
        )
        self.form.bind(minimum_height=self.form.setter("height"))
        scroll.bind(width=lambda _inst, width: setattr(self.form, "width", width))

        self.input_game_name = _input("青云小传", theme)
        self.input_char_name = _input("许满", theme)
        self.input_game_name.bind(text=lambda _inst, _text: self._sync_special_state())
        _field(self.form, "游戏名称", self.input_game_name, theme)
        _field(self.form, "角色名", self.input_char_name, theme)

        grid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        grid.bind(minimum_height=grid.setter("height"))
        self.spinner_talent = _spinner("剑心微明", TALENT_OPTIONS, theme)
        roots = [item["name"] for item in SPIRIT_ROOTS] + [SPECIAL_ROOT]
        self.spinner_root = _spinner("火灵根", roots, theme)
        self.spinner_family = _spinner("寒门", FAMILY_BACKGROUNDS, theme)
        self.spinner_difficulty = _spinner("普通", DIFFICULTY_OPTIONS, theme)
        _field(grid, "天赋", self.spinner_talent, theme)
        _field(grid, "灵根", self.spinner_root, theme)
        _field(grid, "家世", self.spinner_family, theme)
        _field(grid, "难度", self.spinner_difficulty, theme)
        self.form.add_widget(grid)

        attr_title = Label(
            text="基础属性",
            font_size=dp(12),
            color=theme.text_secondary,
            size_hint_y=None,
            height=dp(22),
            halign="left",
        )
        attr_title.bind(width=lambda *_a: attr_title.setter("text_size")(attr_title, (attr_title.width, None)))
        self.form.add_widget(attr_title)
        for key in ATTRIBUTE_KEYS:
            self.form.add_widget(self._attribute_row(key, theme))

        hint = Label(
            text="随机可能获得更好的初始面板，但也可能出现偏科或低起点。",
            font_size=dp(11),
            color=theme.text_secondary,
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        hint.bind(width=lambda *a: hint.setter("text_size")(hint, (hint.width, None)))
        self.form.add_widget(hint)

        self.result_container = BoxLayout(orientation="vertical", size_hint_y=None, height=0)
        self.form.add_widget(self.result_container)

        scroll.add_widget(self.form)
        root.add_widget(scroll)

        action_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50), spacing=dp(8))
        random_btn = themed_button("随机属性", font_size=dp(15))
        start_btn = themed_button("开始修行", font_size=dp(15))
        random_btn.bind(on_release=lambda _: self._randomize())
        start_btn.bind(on_release=lambda _: self._start())
        action_row.add_widget(random_btn)
        action_row.add_widget(start_btn)
        root.add_widget(action_row)
        self.add_widget(root)

    def on_enter(self, *args):
        self._sync_special_state()

    def _attribute_row(self, key: str, theme) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(6))
        label = Label(text=ATTRIBUTE_LABELS[key], font_size=dp(11), color=theme.text, size_hint_x=0.22)
        bar = ProgressBar(max=100, value=self.attributes[key], size_hint_x=0.58)
        value = Label(text=str(self.attributes[key]), font_size=dp(11), color=theme.text_secondary, size_hint_x=0.20)
        self._attribute_widgets[key] = (bar, value)
        row.add_widget(label)
        row.add_widget(bar)
        row.add_widget(value)
        return row

    def _randomize(self) -> None:
        self.attributes = {key: random.randint(35, 88) for key in ATTRIBUTE_KEYS}
        if random.random() < 0.18:
            boost = random.choice(ATTRIBUTE_KEYS)
            self.attributes[boost] = random.randint(89, 96)
        self._refresh_attributes()

    def _sync_special_state(self) -> None:
        if self.input_game_name.text.strip() == SPECIAL_START_CODE:
            self._hide_result_panel()
        else:
            self._hide_result_panel()

    def _refresh_attributes(self) -> None:
        for key, value in self.attributes.items():
            bar, label = self._attribute_widgets[key]
            bar.value = value
            label.text = str(value)

    def _show_result_panel(self) -> None:
        theme = current_theme()
        self.result_container.clear_widgets()
        self.result_container.height = dp(184)
        title = Label(text="[b]开局命格[/b]", markup=True, font_size=dp(17), color=theme.accent, size_hint_y=None, height=dp(30))
        self.result_container.add_widget(title)
        grid = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(98), spacing=dp(6))
        for text in ["属性\n全满", f"家世\n{SPECIAL_FAMILY}", f"天赋\n{SPECIAL_TALENT}", f"灵根\n{SPECIAL_ROOT}"]:
            grid.add_widget(Label(text=text, font_size=dp(12), color=theme.text, halign="center"))
        self.result_container.add_widget(grid)
        narrative = Label(
            text="云海倒悬，九峰钟声同时响起。一枚无主仙令悬在你掌心，像是早已等了很多年。",
            font_size=dp(12),
            color=theme.text_secondary,
            halign="left",
            valign="middle",
        )
        narrative.bind(width=lambda *a: narrative.setter("text_size")(narrative, (narrative.width, None)))
        self.result_container.add_widget(narrative)

    def _hide_result_panel(self) -> None:
        self.result_container.clear_widgets()
        self.result_container.height = 0

    def _start(self) -> None:
        self._sync_special_state()
        special = self.input_game_name.text.strip() == SPECIAL_START_CODE
        attributes = dict(SPECIAL_START_ATTRIBUTES if special else self.attributes)
        profile = {
            "game_name": self.input_game_name.text.strip(),
            "char_name": SPECIAL_START_NAME if special else (self.input_char_name.text.strip() or "无名"),
            "talent": SPECIAL_TALENT if special else self.spinner_talent.text,
            "spirit_root": SPECIAL_ROOT if special else self.spinner_root.text,
            "spirit_root_grade": "天" if special or self.spinner_root.text in {"冰灵根", "雷灵根", "风灵根", SPECIAL_ROOT} else "地",
            "family_background": SPECIAL_FAMILY if special else self.spinner_family.text,
            "difficulty": self.spinner_difficulty.text,
            "attributes": attributes,
            "special_start": special,
        }
        if special:
            profile.update({
                "hp": 999,
                "hp_max": 999,
                "mp": 999,
                "mp_max": 999,
                "gold": 9999,
                "current_scene": "九峰主殿",
                "location": "青玄宗九峰主殿",
                "opening_narrative": (
                    "云海倒悬，九峰钟声同时响起。你睁眼时，掌门与诸峰长老已经等在殿外，"
                    "无人敢高声言语。一枚无主仙令悬在你掌心，像是早已等了很多年。"
                ),
            })
        if self.adapter:
            self.adapter.start_from_profile(profile)
        if self.manager:
            game = self.manager.get_screen("game")
            game.narrative_view.clear()
            self.manager.current = "game"

    def _go_home(self) -> None:
        if self.manager:
            self.manager.current = "home"


def _input(text: str, theme) -> TextInput:
    return TextInput(
        text=text,
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


def _field(parent, label: str, widget, theme) -> None:
    box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(58), spacing=dp(3))
    lbl = Label(text=label, font_size=dp(11), color=theme.text_secondary, size_hint_y=None, height=dp(18), halign="left")
    lbl.bind(width=lambda *_a: lbl.setter("text_size")(lbl, (lbl.width, None)))
    box.add_widget(lbl)
    box.add_widget(widget)
    parent.add_widget(box)
