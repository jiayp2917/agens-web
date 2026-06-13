r"""Full cultivation flow demo — 练气 → 飞升 with mock LLM.

Launches the real Kivy UI and auto-drives a character through all 9 realms
using deterministic mock responses. Screenshots are saved at each milestone.

Usage:
    cd D:\chat\agens
    .venv311\Scripts\python.exe demo_full_flow.py
"""

from __future__ import annotations

import os
import sys
import random
import json
import time
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

# XP per realm to give rapid progression through all layers.
# We grant enough XP per action to advance ~2 layers at a time.
XP_PER_ACTION = {
    "练气": 250,   # 9 layers × 100 XP → ~4 actions to max
    "筑基": 350,   # 4 layers × 300 XP
    "金丹": 650,   # 4 layers × 600 XP
    "元婴": 1300,  # 4 layers × 1200 XP
    "化神": 2600,  # 4 layers × 2500 XP
    "合体": 5200,  # 4 layers × 5000 XP
    "大乘": 10200, # 4 layers × 10000 XP
    "渡劫": 20200, # 4 layers × 20000 XP
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
        },
    }


def _narrator_result(session):
    realm = getattr(session, "realm", "练气")
    stage = getattr(session, "realm_stage", 1)
    xp_grant = XP_PER_ACTION.get(realm, 200)

    narratives = NARRATIVES.get(realm, ["你默默修炼，修为有所精进。"])
    narrative = random.choice(narratives)

    return {
        "narrative": f"第{session.turn_count + 1}回合: {narrative}",
        "state_delta": {
            "character": {
                "mp": "-10",
                "experience": f"+{xp_grant}",
            },
            "world": {"current_scene": f"{realm}修炼中"},
        },
        "choices": ["继续修炼", "尝试突破", "四处探索"],
    }


# ── Demo driver ──────────────────────────────────────────────────────────

class DemoDriver:
    """Auto-drives the Kivy UI through the full cultivation flow."""

    MILESTONE_REALMS = ["练气", "筑基", "金丹", "元婴", "化神", "合体", "大乘", "渡劫", "飞升"]
    SCREENSHOT_NODES = [
        ("01_home", "主页"),
        ("02_character_create", "角色创建"),
        ("03_qi_refining", "练气"),
        ("04_foundation", "筑基"),
        ("05_golden_core", "金丹"),
        ("06_nascent_soul", "元婴"),
        ("07_spirit_transformation", "化神"),
        ("08_unity", "合体"),
        ("09_maha", "大乘"),
        ("10_tribulation", "渡劫"),
        ("11_ascension", "飞升结局"),
    ]

    def __init__(self):
        self.app = None
        self._step = 0
        self._realm_seen: set[str] = set()
        self._screenshot_idx = 0
        self._last_realm = ""
        self._game_started = False
        self._flow_done = False
        self._log_path = DEMO_LOG_PATH
        self._log_path.write_text("", encoding="utf-8")

    def start(self):
        """Launch the Kivy app with demo driver."""
        # Start BGM before the app boots so the music is already in flight
        # by the time the home screen paints.
        self._start_bgm()
        # Patch run_turn_sync before any game code imports.
        with patch("agens_novel.engine.game_engine.run_turn_sync", side_effect=_mock_narrator):
            # Also patch random.random for deterministic breakthroughs.
            with patch("agens_novel.game.realm.random.random", return_value=0.01):
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
            self._take_screenshot("03_qi_refining")
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

            # Check for finale.
            if session.finale:
                self._flow_done = True
                Clock.schedule_once(lambda dt: self._finish_finale("11_ascension"), 0.8)
                return
            if session.game_over:
                self._log_state("game_over_without_finale", session)
                self._take_screenshot("11_game_over_unexpected")
                print("[DEMO] Unexpected game over before ascension.")
                self._flow_done = True
                Clock.schedule_once(lambda dt: App.get_running_app().stop(), 2.0)
                return

            # Check for new realm milestone.
            if realm != self._last_realm and realm not in self._realm_seen:
                self._realm_seen.add(realm)
                self._last_realm = realm
                # Find matching screenshot node.
                for filename, label in self.SCREENSHOT_NODES:
                    if label == realm:
                        self._take_screenshot(filename)
                        print(f"[DEMO] {realm} screenshot taken")
                        break

            # If we've reached 飞升, stop.
            if realm == "飞升":
                self._flow_done = True
                Clock.schedule_once(lambda dt: self._finish_finale("11_ascension"), 0.8)
                return

            from agens_novel.game.constants import REALM_CONFIGS
            cfg = REALM_CONFIGS.get(realm, {})
            max_stage = cfg.get("stages", 4)
            insight_req = cfg.get("insight_required", 0)
            xp = getattr(session, "experience", 0)
            xp_needed = getattr(session, "experience_to_next", 100)
            insight = getattr(session, "insight", 0)

            at_max = stage >= max_stage
            xp_ready = xp >= xp_needed
            insight_ready = insight >= insight_req

            if at_max and xp_ready and insight_ready:
                action_text = "冲击突破"
                self._log_state("action_breakthrough", session, action_text)
                print(f"[DEMO] BREAKTHROUGH from {realm} "
                      f"(stage {stage}/{max_stage}, xp {xp}/{xp_needed}, 感悟 {insight}/{insight_req})")
            elif at_max and xp_ready and not insight_ready:
                # Stuck: XP full but 感悟 short — must do real deeds, not meditate.
                action_text = random.choice(["外出历练", "参悟功法", "寻找机缘"])
                self._log_state("action_insight", session, action_text)
                print(f"[DEMO] STUCK at max layer — {action_text} for 感悟 "
                      f"({insight}/{insight_req})")
            else:
                # Layers remain — cultivate, but weave in insight deeds so the
                # demo visibly does more than meditate.
                if not insight_ready and (self._step % 2 == 1):
                    action_text = random.choice(["外出历练", "参悟功法", "寻找机缘"])
                    self._log_state("action_insight", session, action_text)
                    print(f"[DEMO] {action_text} for 感悟 "
                          f"({insight}/{insight_req}) while in {realm} {stage}/{max_stage}")
                else:
                    action_text = "闭关修炼"
                    self._log_state("action_cultivate", session, action_text)
                    print(f"[DEMO] cultivate ({realm} {stage}/{max_stage}, "
                          f"xp {xp}/{xp_needed}, 感悟 {insight}/{insight_req})")

            self._step += 1

            # Call handle_action which goes through the mock LLM.
            Clock.schedule_once(lambda dt: self._feed_action(action_text), 0.3)

        except Exception as e:
            print(f"[DEMO] Error in _do_action: {e}")
            import traceback
            traceback.print_exc()

    def _feed_action(self, text):
        """Feed text action to the game."""
        try:
            game_screen = self.app.root.get_screen("game")
            # Simulate typing and sending.
            game_screen.action_bar.text_input.text = text
            game_screen.action_bar._on_submit(None)
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

    def _finish_finale(self, name: str):
        try:
            session = self.app.root.get_screen("game").adapter.game_session
            self._log_state("finale_screenshot", session)
            if self.app.root.current != "death":
                self.app.root.current = "death"
            self._take_screenshot(name)
            print("[DEMO] ASCENSION! Screenshot taken.")
        finally:
            Clock.schedule_once(lambda dt: App.get_running_app().stop(), 2.0)

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
            "game_over": bool(getattr(session, "game_over", False)),
            "finale": bool(getattr(session, "finale", False)),
            "current_screen": getattr(self.app.root, "current", "") if self.app else "",
        }
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    print("=" * 60)
    print("  文字修仙全流程演示 — 练气 → 飞升")
    print("=" * 60)
    print(f"  截图目录: {SCREENSHOTS_DIR}")
    print(f"  状态日志: {DEMO_LOG_PATH}")
    print()
    print("  Mock LLM: 已启用 (确定性响应)")
    print("  突破概率: 100% (演示模式)")
    print("  感悟门槛: 已启用 (纯修炼无法突破，须历练/参悟)")
    print()
    driver = DemoDriver()
    driver.start()
