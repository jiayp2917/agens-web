r"""Visual Kivy flow demo for the cultivation rules.

Launches the real Kivy UI and drives a short, inspectable rules loop:
create character → gain a small layer → hit a breakthrough bottleneck →
obtain preparation through deeds → attempt breakthrough. It prefers the real
UI chain and logs whenever mock LLM or deterministic random is used.

Usage:
    cd D:\chat\agens
    .venv311\Scripts\python.exe demo_full_flow.py
"""

from __future__ import annotations

import sys
import random
import json
from pathlib import Path
from unittest.mock import patch

# ── Kivy config (must be before any other Kivy import) ──────────────────
from kivy.config import Config
Config.set('graphics', 'width', '420')
Config.set('graphics', 'height', '780')
Config.set('graphics', 'resizable', False)
Config.set('kivy', 'window_icon', '')
Config.set('kivy', 'log_level', 'warning')

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

# ── Project paths ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
SCREENSHOTS_DIR = PROJECT_ROOT / "demo_screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)
DEMO_LOG_PATH = PROJECT_ROOT / "demo_full_flow_log.jsonl"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ── Mock LLM responses ───────────────────────────────────────────────────

XP_PER_ACTION = {
    "练气": 100,
    "筑基": 120,
    "金丹": 180,
    "元婴": 260,
    "化神": 360,
    "合体": 520,
    "大乘": 760,
    "渡劫": 1000,
}

NARRATIVES = {
    "练气": [
        "你盘膝而坐，灵气如溪流般涌入丹田。真气在经脉中奔涌，修为稳步提升。",
        "山间灵气充沛，你心无旁骛地运转功法，周身真气渐渐凝实。",
        "月华如水，你吐纳天地之灵，每一次呼吸都让修为更进一分。",
        "你感受到体内灵力达到瓶颈，是该尝试突破的时候了。",
    ],
    "筑基": [
        "筑基之后，你根基大固。灵气化作液体在丹田流转，每一次修炼都让根基更加扎实。",
        "你运转筑基功法，大地灵气如潮水般涌来，修为节节攀升。",
        "筑基期的修炼远比练气艰难，但你心志坚定，不惧苦修。",
    ],
    "金丹": [
        "丹田之中，一缕金芒渐显。那是即将凝聚金丹的征兆。",
        "你以真火煅烧灵力，将其压缩凝结，金丹之形渐成。",
        "金丹大道，一步一重天。你沉浸在修炼之中，不知岁月流转。",
    ],
    "元婴": [
        "金丹碎裂，元婴初成。你感受到前所未有的力量在体内觉醒。",
        "元婴小人盘坐丹田，与你同步呼吸吐纳，修为增长速度远超金丹期。",
        "元婴期的每一分进步都让你更接近天地大道。",
    ],
    "化神": [
        "元婴化为元神，你开始触碰天地法则的边缘。",
        "化神期的修炼不再是单纯的灵力积累，而是对天道的领悟。",
        "你闭关参悟，元神与天地交感，修为在静默中飞升。",
    ],
    "合体": [
        "元神与肉身合为一体，你感受到天地之力在体内流转。",
        "合体期的大能，翻手为云覆手为雨。你潜心修炼，不敢懈怠。",
    ],
    "大乘": [
        "大乘之境，你已触摸到飞升的门槛。天地法则在你眼中清晰可见。",
        "你以天地为炉，以肉身为丹，不断淬炼自己的道果。",
    ],
    "渡劫": [
        "天劫将至，雷云密布。你盘坐山巅，以肉身迎接九天雷劫的洗礼。",
        "每一道天雷都携带着毁灭之力，但你在雷劫中越战越强。",
    ],
}


def _mock_narrator(agent_name, user_input, session, **kwargs):
    """Mock run_turn_sync: return deterministic responses for demo."""
    if agent_name == "world_builder":
        return _world_builder_result()
    elif agent_name == "narrator":
        return _narrator_result(session)
    elif agent_name == "judge":
        return {"approved": True, "corrected_delta": {}, "judgment_note": "合理", "review_score": 8}
    return {}


def _world_builder_result():
    return {
        "generated_data": {
            "character": {
                "name": "许满",
                "realm": "练气", "realm_stage": 1,
                "hp": 100, "hp_max": 100, "mp": 50, "mp_max": 50,
                "spirit_root": "火灵根", "spirit_root_grade": "地",
                "experience": 0, "experience_to_next": 100,
                "breakthrough_flags": [],
                "gold": 50, "age": 16,
                "talent": "剑心微明", "family_background": "寒门", "luck": "中上",
                "difficulty": "普通",
                "techniques": [{"name": "基础吐纳术", "level": 1, "type": "内功", "mp_cost": 5}],
                "inventory": [{"name": "粗布道袍", "quantity": 1, "type": "防具", "rarity": "凡品"}],
                "status_effects": [], "lifespan": 100,
            },
            "world": {
                "current_scene": "青玄宗山门",
                "location": "青玄宗山门", "region": "东荒",
                "npcs_present": [{"name": "陈师兄", "relation": "同门", "realm": "练气"}],
                "active_quests": [],
                "discovered_locations": ["青玄宗山门"],
                "lore_facts": ["青玄宗立于东荒云脉之上，山门深处常有灵雾不散。"],
                "day_count": 1,
            },
            "opening_narrative": (
                "晨雾漫过青玄宗山门，许满踏上山门石阶。"
                "火灵根在丹田深处泛起微光，修真之路就此开启。"
            ),
            "choices": ["向陈师兄请教入门规矩", "在山门边试行吐纳", "查看随身物品与功法"],
        },
        "llm_error": "",
    }


def _narrator_result(session):
    realm = getattr(session, "realm", "练气")
    action = getattr(session, "_demo_pending_action", "")
    xp_grant = XP_PER_ACTION.get(realm, 200)
    is_deed = any(word in action for word in ("历练", "参悟", "寻找", "请教", "炼丹", "法宝", "阵法"))

    if is_deed:
        narrative = (
            f"第{session.turn_count + 1}回合: 你没有继续闭门苦修，而是循着山门外的线索行动。"
            "陈师兄指出破境不只靠灵气，还要丹药、护持与机缘。"
        )
        char_delta = {
            "mp": "-8",
            "experience": f"+{max(20, xp_grant // 2)}",
            "insight": "+25",
            "breakthrough_flags_add": ["foundation_aid"],
            "inventory_add": [{"name": "筑基丹线索", "quantity": 1, "type": "机缘"}],
        }
        scene = "山门外历练"
        choices = ["回山门整理所得", "继续请教陈师兄", "检查筑基准备"]
    else:
        narratives = NARRATIVES.get(realm, ["你默默修炼，修为有所精进。"])
        narrative = f"第{session.turn_count + 1}回合: {random.choice(narratives)}"
        char_delta = {
            "mp": "-10",
            "experience": f"+{xp_grant}",
        }
        scene = f"{realm}修炼中"
        choices = ["继续吐纳稳固气息", "请教附近修士", "查看破境准备"]

    return {
        "narrative": narrative,
        "state_delta": {
            "character": char_delta,
            "world": {"current_scene": scene},
        },
        "choices": choices,
        "llm_error": "",
    }


# ── Demo driver ──────────────────────────────────────────────────────────

class DemoDriver:
    """Auto-drives the Kivy UI through a visible rules loop."""

    SCREENSHOT_NODES = [
        ("01_home", "主页"),
        ("02_character_create", "角色创建"),
        ("03_game_initial", "初始游戏"),
        ("04_cultivation_stage_gain", "修炼升层"),
        ("05_bottleneck_blocked", "瓶颈阻断"),
        ("06_insight_action", "历练得机缘"),
        ("07_breakthrough_attempt", "突破尝试"),
        ("08_breakthrough_result", "突破结果"),
    ]

    def __init__(self):
        self.app = None
        self._step = 0
        self._realm_seen: set[str] = set()
        self._screenshot_idx = 0
        self._last_realm = ""
        self._game_started = False
        self._flow_done = False
        self._script = [
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("闭关修炼", "action_cultivate"),
            ("冲击突破", "action_breakthrough_blocked"),
            ("外出历练，向陈师兄请教筑基机缘", "action_insight"),
            ("冲击突破", "action_breakthrough"),
        ]
        self._log_path = DEMO_LOG_PATH
        self._log_path.write_text("", encoding="utf-8")
        self._log_meta()

    def start(self):
        """Launch the Kivy app with demo driver."""
        # Start BGM before the app boots so the music is already in flight
        # by the time the home screen paints.
        self._start_bgm()
        # Patch run_turn_sync before any game code imports. This is a visible
        # UI smoke demo, not a live LLM integration run; metadata is logged.
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_mock_narrator):
            with patch("agens_novel.game.realm.random.random", return_value=0.05):
                # Import the app inside patches.
                from mobile.main import XianxiaApp
                self.app = XianxiaApp()

                # Schedule the demo flow.
                Clock.schedule_once(self._init_demo, 1.0)

                self.app.run()

    def _start_bgm(self):
        """Best-effort BGM start. Swallows any audio failure."""
        try:
            from agens_novel.bgm import get_service
            svc = get_service()
            ok = svc.play("default", loop=True)
            if ok:
                print("[DEMO] BGM started (bgm.flac, looping)")
            else:
                print("[DEMO] BGM: no audio backend, continuing silently")
        except Exception as exc:
            print(f"[DEMO] BGM init failed (non-fatal): {exc}")

    def _init_demo(self, dt):
        """Navigate to character creation and start the flow."""
        self._take_screenshot("01_home")
        print("[DEMO] Home screen screenshot taken")

        # Navigate to character creation.
        Clock.schedule_once(self._go_to_create, 1.0)

    def _go_to_create(self, dt):
        """Go to character create screen."""
        try:
            screen = self.app.root.current_screen
            if hasattr(screen, 'manager') and screen.manager:
                screen.manager.current = "character_create"
                self._take_screenshot("02_character_create")
                print("[DEMO] Character create screenshot taken")
                # Start the game.
                Clock.schedule_once(self._start_game, 1.0)
        except Exception as e:
            print(f"[DEMO] Error navigating to create: {e}")

    def _start_game(self, dt):
        """Click start on character create screen."""
        try:
            screen = self.app.root.get_screen("character_create")
            screen._start()
            self._game_started = True
            Clock.schedule_once(self._begin_gameplay, 1.5)
        except Exception as e:
            print(f"[DEMO] Error starting game: {e}")

    def _begin_gameplay(self, dt):
        """Navigate to game screen and begin the auto-play."""
        try:
            self.app.root.current = "game"
            self._take_screenshot("03_game_initial")
            print("[DEMO] Game start screenshot taken")
            self._last_realm = "练气"
            self._realm_seen.add("练气")
            # Start the action loop.
            Clock.schedule_once(self._do_action, 0.8)
        except Exception as e:
            print(f"[DEMO] Error beginning gameplay: {e}")

    def _do_action(self, dt):
        """Feed one action to advance the game.

        Three-state policy that visibly does more than just meditate:
          - all breakthrough conditions met  → 突破
          - stuck at max layer (XP full) but 感悟 short → 历练/参悟 (gain insight)
          - layers still to gain             → 闭关修炼 (interspersed with 历练)
        """
        if self._flow_done:
            return

        try:
            game_screen = self.app.root.get_screen("game")
            adapter = game_screen.adapter
            session = adapter.game_session
            realm = getattr(session, "realm", "练气")
            stage = getattr(session, "realm_stage", 1)
            self._log_state("tick", session)

            if session.game_over:
                self._log_state("game_over_without_finale", session)
                self._take_screenshot("09_game_over_unexpected")
                print("[DEMO] Unexpected game over before ascension.")
                self._flow_done = True
                Clock.schedule_once(lambda dt: App.get_running_app().stop(), 2.0)
                return

            if self._step >= len(self._script):
                self._flow_done = True
                self._take_screenshot("08_breakthrough_result")
                self._log_state("demo_complete", session)
                Clock.schedule_once(lambda dt: App.get_running_app().stop(), 2.0)
                return

            action_text, event = self._script[self._step]
            self._log_state(event, session, action_text)
            print(f"[DEMO] {event}: {action_text} ({realm} {stage}层)")

            self._step += 1

            # Call handle_action which goes through the mock LLM.
            if event == "action_breakthrough":
                self._take_screenshot("07_breakthrough_attempt")
            Clock.schedule_once(lambda dt: self._feed_action(action_text, event), 0.3)

        except Exception as e:
            print(f"[DEMO] Error in _do_action: {e}")
            import traceback
            traceback.print_exc()

    def _feed_action(self, text, event: str):
        """Feed text action to the game."""
        try:
            game_screen = self.app.root.get_screen("game")
            # Simulate typing and sending.
            setattr(game_screen.adapter.game_session, "_demo_pending_action", text)
            game_screen.action_bar.text_input.text = text
            game_screen.action_bar._on_submit(None)
            if event == "action_breakthrough_blocked":
                Clock.schedule_once(lambda _dt: self._take_screenshot("05_bottleneck_blocked"), 0.8)
            elif "历练" in text:
                Clock.schedule_once(lambda _dt: self._take_screenshot("06_insight_action"), 0.8)
            elif self._step == 1:
                Clock.schedule_once(lambda _dt: self._take_screenshot("04_cultivation_stage_gain"), 0.8)
            # Schedule next action after processing.
            Clock.schedule_once(self._do_action, 1.5)
        except Exception as e:
            print(f"[DEMO] Error feeding action: {e}")

    def _take_screenshot(self, name: str):
        """Save a screenshot."""
        try:
            path = str(SCREENSHOTS_DIR / f"{name}.png")
            Window.screenshot(name=path)
            print(f"[DEMO] Screenshot saved: {path}")
        except Exception as e:
            print(f"[DEMO] Screenshot error: {e}")

    def _log_meta(self) -> None:
        payload = {
            "event": "demo_meta",
            "mode": "ui_smoke_mock_llm",
            "real_kivy_window": True,
            "real_llm": False,
            "mock_llm": True,
            "judge_mock": True,
            "forced_random": True,
            "goal": "创建角色→修炼升层→瓶颈阻断→历练得机缘→突破尝试",
        }
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _log_state(self, event: str, session, action: str = "") -> None:
        payload = {
            "event": event,
            "step": self._step,
            "action": action,
            "realm": getattr(session, "realm", ""),
            "realm_stage": getattr(session, "realm_stage", 0),
            "experience": getattr(session, "experience", 0),
            "experience_to_next": getattr(session, "experience_to_next", 0),
            "insight": getattr(session, "insight", 0),
            "breakthrough_flags": getattr(session, "breakthrough_flags", []),
            "game_over": bool(getattr(session, "game_over", False)),
            "finale": bool(getattr(session, "finale", False)),
            "current_screen": getattr(self.app.root, "current", "") if self.app else "",
        }
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    print("=" * 60)
    print("  文字修仙流程演示 — 修炼瓶颈与破境准备")
    print("=" * 60)
    print(f"  截图目录: {SCREENSHOTS_DIR}")
    print(f"  状态日志: {DEMO_LOG_PATH}")
    print()
    print("  真实 Kivy 窗口: 已启用")
    print("  Mock LLM: 已启用并写入日志")
    print("  随机数: 固定为可回放演示值")
    print("  验证重点: 纯修炼只能升小层，缺资源/机缘时突破会被阻断")
    print()
    driver = DemoDriver()
    driver.start()
