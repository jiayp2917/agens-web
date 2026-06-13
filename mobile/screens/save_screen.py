"""Save screen — multi-slot save/load management UI."""

from __future__ import annotations

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp

from service.engine_adapter import EngineAdapter
from theme import add_background, current_theme, themed_button


class SaveScreen(Screen):
    """Multi-slot save management screen."""

    def __init__(self, adapter: EngineAdapter | None = None, **kwargs):
        super().__init__(**kwargs)
        self.adapter = adapter
        theme = current_theme()
        add_background(self, color=theme.bg)

        self.layout = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(12)],
            spacing=dp(8),
        )

        # Title.
        self.layout.add_widget(Label(
            text="[b]存档管理[/b]",
            markup=True,
            font_size=dp(18),
            size_hint_y=None,
            height=dp(36),
            color=theme.text,
        ))

        # Auto-save slot.
        self.auto_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(50),
            spacing=dp(8),
        )
        self.layout.add_widget(self.auto_box)

        # Manual save slots (in a scroll view).
        self.slots_layout = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(4),
        )
        self.slots_layout.bind(minimum_height=self.slots_layout.setter("height"))

        scroll = ScrollView()
        scroll.add_widget(self.slots_layout)
        self.layout.add_widget(scroll)

        # Bottom buttons.
        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8),
        )
        back_btn = themed_button("返回游戏", font_size=dp(14))
        back_btn.bind(on_release=lambda _: self._go_back())
        refresh_btn = themed_button("刷新", font_size=dp(14))
        refresh_btn.bind(on_release=lambda _: self.refresh())

        btn_row.add_widget(refresh_btn)
        btn_row.add_widget(back_btn)
        self.layout.add_widget(btn_row)

        self.add_widget(self.layout)

    def on_enter(self, *args):
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the save slot display."""
        if not self.adapter:
            return

        theme = current_theme()
        saves = self.adapter.list_saves()
        saves_by_name = {s["name"]: s for s in saves if not s.get("error")}

        # Auto-save slot.
        self.auto_box.clear_widgets()
        auto_info = saves_by_name.get("autosave")
        auto_label = Label(
            text=self._format_save_info("自动存档", auto_info),
            font_size=dp(12),
            halign="left",
            size_hint_x=0.6,
            color=theme.text,
        )
        auto_label.bind(width=lambda *a: auto_label.setter("text_size")(auto_label, (auto_label.width, None)))

        auto_load_btn = themed_button("读取", font_size=dp(12), size_hint_x=0.2)
        auto_load_btn.bind(on_release=lambda _: self._load("autosave"))

        self.auto_box.add_widget(auto_label)
        self.auto_box.add_widget(auto_load_btn)

        # Manual slots.
        self.slots_layout.clear_widgets()
        for i in range(1, 6):
            slot_name = f"slot_{i}"
            slot_info = saves_by_name.get(slot_name)

            row = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(44),
                spacing=dp(4),
            )

            lbl = Label(
                text=self._format_save_info(f"存档 {i}", slot_info),
                font_size=dp(12),
                halign="left",
                size_hint_x=0.5,
                color=theme.text,
            )
            lbl.bind(width=lambda *a, w=lbl: w.setter("text_size")(w, (w.width, None)))

            save_btn = themed_button("保存", font_size=dp(11), size_hint_x=0.17)
            save_btn.bind(on_release=lambda _, sn=slot_name: self._save(sn))

            load_btn = themed_button("读取", font_size=dp(11), size_hint_x=0.17)
            load_btn.bind(on_release=lambda _, sn=slot_name: self._load(sn))

            del_btn = themed_button("删除", font_size=dp(11), size_hint_x=0.16)
            del_btn.bind(on_release=lambda _, sn=slot_name: self._delete(sn))

            row.add_widget(lbl)
            row.add_widget(save_btn)
            row.add_widget(load_btn)
            row.add_widget(del_btn)
            self.slots_layout.add_widget(row)

    def _format_save_info(self, label: str, info: dict | None) -> str:
        if info is None:
            return f"{label}: [空]"
        name = info.get("char_name", "?")
        realm = info.get("realm", "?")
        turn = info.get("turn_count", 0)
        return f"{label}: {name} [{realm}] 回合{turn}"

    def _save(self, name: str) -> None:
        if self.adapter:
            self.adapter.save(name)
            self.refresh()

    def _load(self, name: str) -> None:
        if self.adapter:
            self.adapter.load(name)
            self._go_back()

    def _delete(self, name: str) -> None:
        if self.adapter:
            self.adapter.delete_save(name)
            self.refresh()

    def _go_back(self) -> None:
        if self.manager:
            self.manager.current = "game"
