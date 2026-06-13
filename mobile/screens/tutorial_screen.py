"""Tutorial screen — new player guide for the xianxia simulator."""

from __future__ import annotations

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from theme import add_background, current_theme, themed_button

# Tutorial pages content.
_TUTORIAL_PAGES = [
    {
        "title": "欢迎来到文字修仙",
        "content": (
            "这是一款AI驱动的修真模拟器。\n\n"
            "你将扮演一名修真者，在仙侠世界中修炼、探索、战斗、突破境界。\n\n"
            "你的每一个选择都会影响修真之路的走向。"
        ),
    },
    {
        "title": "基本操作",
        "content": (
            "· 在输入框中输入行动文字，点击发送\n"
            "· 使用底部快捷按钮查看状态、背包等\n"
            "· AI会根据你的行动生成叙事和状态变化\n\n"
            "例如：输入「前往灵山修炼」\n"
            "天道会描述修炼过程和收获。"
        ),
    },
    {
        "title": "境界与灵根",
        "content": (
            "· 修真境界：练气→筑基→金丹→元婴→化神→合体→大乘→渡劫→飞升\n"
            "· 每个境界有多个层次，需逐步提升\n"
            "· 灵根决定修炼天赋：\n"
            "  - 天灵根(冰/雷/风)：修炼1.5倍速\n"
            "  - 地灵根(金/木/水/火/土)：修炼1.2倍速\n"
            "· 突破有失败风险，需充分准备"
        ),
    },
    {
        "title": "战斗系统",
        "content": (
            "· 战斗采用回合制：你一回合，敌人一回合\n"
            "· 5种操作：普攻/功法/丹药/防御/逃跑\n"
            "  - 普攻：基础伤害\n"
            "  - 功法：消耗MP，高伤害\n"
            "  - 丹药：恢复HP/MP\n"
            "  - 防御：减少50%伤害\n"
            "  - 逃跑：80%成功率(Boss战不可逃)\n"
            "· 境界压制：高境界攻击和防御更强"
        ),
    },
    {
        "title": "装备与物品",
        "content": (
            "· 3个装备位：武器/防具/饰品\n"
            "· 物品品质：凡品→良品→上品→极品→仙品\n"
            "· 丹药可在战斗中使用恢复HP/MP\n"
            "· NPC可以交易和教授功法"
        ),
    },
    {
        "title": "祝修行顺利",
        "content": (
            "· 善用存档功能，避免损失\n"
            "· 注意HP，归零即游戏结束\n"
            "· 与NPC交流获取任务和奖励\n"
            "· 修炼积累经验，突破提升境界\n\n"
            "现在，开始你的修真之旅吧！"
        ),
    },
]


class TutorialScreen(Screen):
    """New player tutorial with swipeable pages."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        theme = current_theme()
        add_background(self, color=theme.bg)

        self._current_page = 0

        self.layout = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(16)],
            spacing=dp(12),
        )

        # Page indicator.
        self.lbl_page = Label(
            text="1 / 6",
            font_size=dp(12),
            size_hint_y=None,
            height=dp(20),
            color=theme.text_hint,
        )
        self.layout.add_widget(self.lbl_page)

        # Content area.
        scroll = ScrollView()
        self.lbl_content = Label(
            text="",
            markup=True,
            font_size=dp(14),
            halign="left",
            valign="top",
            size_hint_y=None,
            color=theme.text,
        )
        self.lbl_content.bind(
            width=lambda *a: self.lbl_content.setter("text_size")(self.lbl_content, (self.lbl_content.width, None)),
            texture_size=self.lbl_content.setter("size"),
        )
        scroll.add_widget(self.lbl_content)
        self.layout.add_widget(scroll)

        # Navigation buttons.
        nav_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(8),
        )
        self.btn_prev = themed_button("上一页", font_size=dp(14))
        self.btn_next = themed_button("下一页", font_size=dp(14))
        self.btn_start = themed_button("开始游戏", font_size=dp(14))

        self.btn_prev.bind(on_release=lambda _: self._prev_page())
        self.btn_next.bind(on_release=lambda _: self._next_page())
        self.btn_start.bind(on_release=lambda _: self._start_game())

        nav_row.add_widget(self.btn_prev)
        nav_row.add_widget(self.btn_next)
        nav_row.add_widget(self.btn_start)
        self.layout.add_widget(nav_row)

        self.add_widget(self.layout)

    def on_enter(self, *args):
        self._current_page = 0
        self._update_page()

    def _update_page(self) -> None:
        page = _TUTORIAL_PAGES[self._current_page]
        title = page["title"]
        content = page["content"]
        total = len(_TUTORIAL_PAGES)

        self.lbl_page.text = f"{self._current_page + 1} / {total}"
        self.lbl_content.text = f"[b]{title}[/b]\n\n{content}"

        # Update button states.
        self.btn_prev.disabled = self._current_page == 0
        self.btn_next.disabled = self._current_page == total - 1
        self.btn_start.disabled = False

        # Show "开始游戏" more prominently on last page.
        if self._current_page == total - 1:
            self.btn_start.text = "[开始游戏]"
        else:
            self.btn_start.text = "跳过引导"

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_page()

    def _next_page(self) -> None:
        if self._current_page < len(_TUTORIAL_PAGES) - 1:
            self._current_page += 1
            self._update_page()

    def _start_game(self) -> None:
        """Go to the game screen (or settings if no key)."""
        if self.manager:
            self.manager.current = "game"
