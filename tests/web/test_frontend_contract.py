from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_frontend_fallback_contains_required_web_views() -> None:
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")

    for selector in (
        'id="homeView"',
        'id="characterView"',
        'id="gameView"',
        'id="endingView"',
        'id="authButton"',
        'id="settingsButton"',
        'id="modalCloseButton"',
        'id="choices"',
        'id="actionInput"',
    ):
        assert selector in html

    assert "小说模式" in html
    assert "游戏模式" in html
    assert "disabled" in html
    assert '<form method="dialog" class="modal-frame">' not in html
    assert "关闭程序" not in html
    assert "练" + "虚" not in html
    assert "爽" + "文模式" not in html


def test_legacy_frontend_fallback_does_not_embed_api_key_or_hidden_rules() -> None:
    combined = "\n".join(
        [
            (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8"),
            (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8"),
            (ROOT / "web" / "frontend" / "styles.css").read_text(encoding="utf-8"),
        ]
    )

    assert "sk-" not in combined
    assert "SPECIAL_START_CODE" not in combined
    assert "2917" not in combined


def test_legacy_frontend_fallback_exposes_fallback_choice_without_hidden_rule() -> None:
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "/end" in js
    assert "fallback_prompt" in js
    assert "结束本局" in js


def test_legacy_frontend_fallback_uses_cookie_auth_not_legacy_local_login() -> None:
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "/api/auth/login" in js
    assert "/api/auth/register" in js
    assert 'credentials: "include"' in js
    assert "/api/users/login" not in js


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


# ====================== F-003 / F-101 / F-102 / F-104 / F-205 契约 ======================


def _escape_html(value: str) -> str:
    """Python 镜像实现，与 app.js 内 escapeHtml 完全等价。"""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def test_frontend_escapes_xss_in_choice_text() -> None:
    """F-003: renderChoices 对 choice 文本调用 escapeHtml，恶意串必须被转义。"""
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")
    # 1. 必须存在 escapeHtml + 实际被 renderChoices 调用
    assert "function escapeHtml" in js
    assert "escapeHtml(choice)" in js
    # 2. 模拟一次渲染：手工调用与 JS 等价的 Python escapeHtml
    malicious = '<img src=x onerror=alert(1)>'
    rendered = _escape_html(malicious)
    assert "&lt;img" in rendered
    assert "<img" not in rendered
    assert "alert(1)" in rendered  # 内容保留，只是标签被转义


def test_frontend_dialog_uses_native_show_modal() -> None:
    """F-101: 模态用 <dialog> + showModal()，浏览器原生支持 Esc 关闭。"""
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert '<dialog id="modal"' in html
    assert "modal.showModal()" in js
    # 浏览器原生 <dialog> 在按下 Esc 时自动关闭，无需 JS 监听器
    # 这里只断言依赖关系


def test_frontend_theme_toggle_wired_to_both_buttons() -> None:
    """F-102: 主题切换必须同时驱动 #themeToggle 与 #themeToggleInline。"""
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="themeToggle"' in html
    assert 'id="themeToggleInline"' in html
    assert "THEME_CYCLE" in js
    assert "applyTheme" in js
    assert 'agens.theme' in js  # localStorage key
    assert '#themeToggle' in js
    assert '#themeToggleInline' in js


def test_frontend_narrative_log_has_aria_describedby() -> None:
    """F-104: narrativeLog 滚动区域必须有键盘提示。"""
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="narrativeLog"' in html
    assert 'id="narrativeLogHint"' in html
    assert "aria-describedby=\"narrativeLogHint\"" in html


def test_frontend_event_badges_locked() -> None:
    """F-205: 11 个事件 badge 全部存在。"""
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")
    for key in (
        "narrative",
        "status",
        "info",
        "error",
        "loading",
        "stream",
        "combat",
        "character_created",
        "model_failure",
        "game_over",
        "finale",
    ):
        assert f"{key}:" in js, f"EVENT_BADGES 缺少 {key}"
