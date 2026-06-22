from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_frontend_directory_is_retired() -> None:
    assert not (ROOT / "web" / "frontend").exists()


def test_static_runtime_uses_react_dist_only() -> None:
    app_py = (ROOT / "web" / "backend" / "app.py").read_text(encoding="utf-8")

    assert "FRONTEND_REACT_DIST" in app_py
    assert "AGENS_ENABLE_LEGACY_FRONTEND" not in app_py
    assert ' / "frontend"' not in app_py


def test_react_frontend_wires_save_load_and_settings() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    client = (ROOT / "web" / "frontend-react" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert "/api/saves" in source
    assert '/load`' in source
    assert "读档" in source
    assert "覆盖保存" in source
    assert "保存到此档" in source
    assert "/api/settings/model" in source
    assert "当前 Key 状态" in source
    assert "留空则保持当前 Key" in source
    assert "访客游玩不提供云端存档" in source
    assert "邀请码注册" in source
    assert 'credentials: "include"' in client
    assert "sk-" not in source


def test_react_homepage_buttons_have_handlers() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "onLoad" in source
    assert "onTutorial" in source
    assert "onSettings" in source
    assert "TutorialDialog" in source
    assert "模型暂不可用，当前以本地故事继续。" in source
    assert "A 稳妥、B 机遇、C 风险、D 气运" in source
    assert "D 代表随缘与天命路线，不是自由输入" in source
    assert "D 输入框可以写自由行动" not in source
    assert "D 写下自己的行动" not in source
    assert "requireAuth" not in source
    assert 'href="https://www.jiayp2917.xyz/"' in source
    assert "BgmToggle" in source
    assert "/assets/audio/bgm.flac" in source
    assert "agens web" not in source.lower()


def test_react_public_assets_are_present() -> None:
    assets = ROOT / "web" / "frontend-react" / "public" / "assets"
    for relative in (
        "paper_texture.png",
        "ink_home_bg.png",
        "ink_mountain_gate.png",
        "game_desktop_bg.png",
        "ascension_gate.png",
        "audio/bgm.flac",
    ):
        assert (assets / relative).is_file(), relative


def test_react_character_creation_uses_catalogs_and_game_mode() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    css = (ROOT / "web" / "frontend-react" / "src" / "styles.css").read_text(encoding="utf-8")

    for path in (
        "/api/catalog/talents",
        "/api/catalog/spirit_roots",
        "/api/catalog/family_backgrounds",
        "/api/catalog/difficulties",
    ):
        assert path in source
    assert "游戏模式 Alpha" in source
    assert "自行选择" in source
    assert "随机生成" in source
    assert "手选最高：紫" in source
    assert "推演中..." in source
    assert "choice_card_mountain.png" not in css
    assert 'url("/assets/ink_mountain_gate.png")' in css


def test_react_game_page_has_escape_route_and_stable_meters() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    css = (ROOT / "web" / "frontend-react" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "onHome={returnHome}" in source
    assert "返回首页" in source
    assert "function StatLine" in source
    assert "role=\"meter\"" in source
    assert ".stat-meter" in css
    assert "grid-template-rows: auto minmax(0, 1fr) auto;" in css


def test_react_turn_actions_disable_while_busy() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "disabled={busy}" in source
    assert "runTurn(`/api/sessions/${session.session_id}/choice`" in source
    # Game-mode v5: A/B/C/D fixed choices only; no free-text input element.
    for label in ("A 稳妥", "B 机遇", "C 风险", "D 气运"):
        assert label in source
    assert "FallbackBanner session={session} busy={busy} runTurn={runTurn}" in source
    assert "function FallbackBanner({ session, busy, runTurn }" in source
    assert "disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/action`" in source
    assert "disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/end`" in source


def test_frontend_escapes_xss_in_choice_text() -> None:
    """React renders choice text as text nodes; do not bypass JSX escaping."""
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in source
    assert "innerHTML" not in source


def test_frontend_dialog_uses_native_show_modal() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source


def test_frontend_theme_toggle_wired_to_both_buttons() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "BgmToggle" in source
    assert "setEnabled" in source


def test_frontend_narrative_log_has_aria_describedby() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert 'className="story-log"' in source
    assert 'aria-live="polite"' in source


def test_frontend_event_badges_locked() -> None:
    source = (ROOT / "web" / "frontend-react" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "fallback_prompt" in source
    assert "game_over" in source
    assert "finale" in source
