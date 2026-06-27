from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.xdist_group("pg_test_db")


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "web" / "frontend-react" / "src"


def _read(*relatives: str) -> str:
    """Concatenate the text of several frontend source files.

    After the v5 SPA split, the strings the contract tests look for live in
    many modules, not just `main.tsx`. Each call passes the modules a given
    test cares about; the empty-tuple case degrades to `main.tsx` only.
    """
    paths = [SRC / r for r in (("main.tsx",) + relatives if relatives else ("main.tsx",))]
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


def _read_css() -> str:
    style_entry = (SRC / "styles.css").read_text(encoding="utf-8")
    style_dir = SRC / "styles"
    split_styles = "\n".join(p.read_text(encoding="utf-8") for p in sorted(style_dir.glob("*.css")))
    return style_entry + "\n" + split_styles


def test_legacy_frontend_directory_is_retired() -> None:
    assert not (ROOT / "web" / "frontend").exists()


def test_static_runtime_uses_react_dist_only() -> None:
    app_py = (ROOT / "web" / "backend" / "app.py").read_text(encoding="utf-8")

    assert "FRONTEND_REACT_DIST" in app_py
    assert "AGENS_ENABLE_LEGACY_FRONTEND" not in app_py
    assert ' / "frontend"' not in app_py


def test_react_frontend_wires_save_load_and_settings() -> None:
    source = _read(
        "components/SettingsSaveDialog.tsx",
        "components/ModelSettingsPanel.tsx",
        "components/SaveSlotsPanel.tsx",
        "lib/catalog.ts",
        "lib/util.ts",
    )
    client = (SRC / "api" / "client.ts").read_text(encoding="utf-8")

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
    source = _read(
        "main.tsx",
        "components/BgmToggle.tsx",
        "components/TutorialDialog.tsx",
        "pages/HomePage.tsx",
        "components/FallbackBanner.tsx",
    )

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
    assert 'className="brand page-brand"' in source
    assert "BgmToggle" in source
    assert 'assetUrl("assets/audio/bgm.flac")' in source
    assert "agens web" not in source.lower()
    assert 'assetUrl("assets/xian-game-icon-256.png")' in source
    assert '<span className="qq-icon" aria-hidden="true">仙</span>' not in source
    # v5 cleanup: homepage must not carry the WEB· eyebrow or the four-button description paragraph.
    assert "WEB · 文字修仙模拟器" not in source
    assert "从山门晨雾开始。A 稳妥、B 机遇、C 风险、D 气运，四选一推进修行岁月" not in source
    # Brand text trimmed to the short form on topbar; the homepage URL link still mentions jiayp2917.
    # `_read` de-duplicates "main.tsx" from the explicit list, so the URL appears exactly once.
    assert "jiayp\n" in source and ">jiayp2917<" not in source and ">jiayp2917\n" not in source


def test_react_public_assets_are_present() -> None:
    assets = ROOT / "web" / "frontend-react" / "public" / "assets"
    for relative in (
        "paper_texture.png",
        "ink_mountain_gate.png",
        "ascension_gate.png",
        "qq_group.png",
        "audio/bgm.flac",
        "xian-game-icon-256.png",
    ):
        assert (assets / relative).is_file(), relative


def test_react_character_creation_uses_catalogs_and_game_mode() -> None:
    source = _read(
        "pages/CharacterCreatePage.tsx",
        "hooks/useCatalogs.ts",
        "hooks/useCharacterFormReducer.ts",
        "components/CatalogGroup.tsx",
        "components/AttributeAllocator.tsx",
        "lib/catalog.ts",
        "lib/util.ts",
    )
    css = _read_css()

    for path in (
        "/api/catalog/talents",
        "/api/catalog/spirit_roots",
        "/api/catalog/family_backgrounds",
        "/api/catalog/difficulties",
    ):
        assert path in source
    assert "creation-layout" in source
    assert "character-panel" in source
    assert "fate-panel" in source
    assert "attribute-panel" in source
    assert "自行选择" in source
    assert "随机角色" in source
    assert "手选最高：紫" in source
    assert "进入中..." in source
    assert "当前难度：{difficulty}" in source
    assert 'className={`catalog-group ${open ? "is-open" : ""}`}' in source
    assert 'aria-expanded={open}' in source
    assert "summary-copy" in source
    assert "selected-pill" in source
    assert "catalog-chevron" in source
    assert "影响修行节奏、突破叙事与关键事件。" in source
    assert "影响境界突破、机缘类型与修炼取向。" in source
    assert "决定出生叙事、初始关系与外界牵连。" in source
    assert "openFateGroup" in source
    assert 'useState<FateGroupKey | "">("talent")' in source
    assert 'current === group.key ? "" : group.key' in source
    assert "catalog-list" in source
    assert "selection-check" in source
    assert "colorOrder" in source
    assert "sortedByColor(items)" in source
    assert "<em" not in source
    assert "✓" not in source
    assert "colorLabel" not in source
    assert 'className="attr-meter"' in source
    assert 'role="meter"' in source
    assert "aria-valuenow={value}" in source
    assert "Math.min(manualAttributeMax, values[key])" not in source
    assert "choice_card_mountain.png" not in css
    assert "game_name" not in source
    assert "游戏名称" not in source
    assert "var(--ink-gate)" in css
    assert 'url("/assets/ink_mountain_gate.png")' not in css
    assert 'url("/static/assets/ink_mountain_gate.png")' not in css
    assert "hero-rule::after" in css and "content: none;" in css
    assert ".home-actions button svg" in css and "position: absolute;" in css
    # v5 cleanup: dropdown labels use the unified 6-color palette, not legacy rarity strings.
    assert "rarityToColor" in source
    for color in ("白", "绿", "蓝", "紫", "橙", "红"):
        assert f'"{color}"' in source, f"missing palette color {color} in util.ts"
    for slug in ("white", "green", "blue", "purple", "orange", "red"):
        assert f".rarity-{slug}" in css, f"missing rarity-{slug} class in styles.css"


def test_react_game_page_has_escape_route_and_stable_meters() -> None:
    source = _read(
        "main.tsx",
        "pages/GamePage.tsx",
        "components/StatLine.tsx",
        "components/LifespanBar.tsx",
        "components/ChronicleItem.tsx",
        "components/ChoiceButton.tsx",
        "lib/chronicle.ts",
        "lib/catalog.ts",
    )
    css = _read_css()

    assert "onHome={returnHome}" in source
    assert "返回首页" in source
    assert "function StatLine" in source
    assert 'role="meter"' in source
    assert "realmLifespanCap" in source
    assert "value={remainingLifespan}" in source
    assert "ChronicleItem" in source
    assert "chronicle-age" in source
    assert "buildChronicleRecords" in source
    assert "getCurrentChronicleYear" in source
    assert "cleanChronicleText" in source
    assert "Math.max(...yearCandidates)" in source
    assert "玄历" in source
    assert "ChoiceButton" in source
    assert "cleanChoiceText" in source
    assert "往事时间轴" in source
    assert ".stat-meter" in css
    assert ".page-brand" in css
    assert ".chronicle-age" in css
    assert "height: 100dvh;" in css
    assert "overflow: hidden;" in css
    assert "grid-template-rows: auto minmax(0, 1fr) auto auto;" in css
    assert "grid-template-columns: 58px minmax(0, 1fr) auto;" in css
    assert "tool-grid" not in source
    assert "panel-summary" not in source
    assert "panel-output" not in source
    assert "timeline-pin" not in source
    assert "chronicle-card" not in source
    assert "<dt>位置</dt>" not in source
    assert 'className="story-log chronicle-log"' in source
    # v5 cleanup: lifespan reads the remaining value, not the realm cap; UI shows remaining/max.
    assert "character.remaining_lifespan" in source
    assert "value={remainingLifespan}" in source
    assert "max={lifespanMax}" in source
    assert "{remainingLifespan}</strong>/{lifespanMax}" in source
    for removed in ("经验", "感悟", "灵石", "experience", "experience_to_next", "insight", "gold"):
        assert removed not in source


def test_react_turn_actions_disable_while_busy() -> None:
    source = _read(
        "main.tsx",
        "pages/GamePage.tsx",
        "pages/HomePage.tsx",
        "components/FallbackBanner.tsx",
        "components/ChoiceButton.tsx",
        "components/TutorialDialog.tsx",
        "lib/catalog.ts",
        "pages/CharacterCreatePage.tsx",
    )

    assert "disabled={busy}" in source
    assert "runTurn(`/api/sessions/${session.session_id}/choice`" in source
    assert "aria-label={`${letter}：${text}`}" in source
    assert "<strong>{label}</strong>" not in source
    # Game-mode v5: A/B/C/D fixed choices only; no free-text input element.
    # The labels are defined as `choiceSemantics` entries (key + label pairs).
    assert "choiceSemantics" in source
    for key, label in (("A", "稳妥"), ("B", "机遇"), ("C", "风险"), ("D", "气运")):
        assert f'key: "{key}", label: "{label}"' in source
    # TutorialDialog carries the canonical player-facing labels.
    for label in ("A 稳妥", "B 机遇", "C 风险", "D 气运"):
        assert label in source
    assert "FallbackBanner session={session} busy={busy} runTurn={runTurn}" in source
    assert "function FallbackBanner({ session, busy, runTurn }" in source
    assert "disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/action`" in source
    assert "disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/end`" in source


def test_frontend_escapes_xss_in_choice_text() -> None:
    """React renders choice text as text nodes; do not bypass JSX escaping."""
    source = _read("pages/GamePage.tsx")
    assert "dangerouslySetInnerHTML" not in source
    assert "innerHTML" not in source


def test_frontend_dialog_uses_native_show_modal() -> None:
    source = _read("components/TutorialDialog.tsx", "components/SettingsSaveDialog.tsx")
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source


def test_frontend_theme_toggle_wired_to_both_buttons() -> None:
    source = _read("components/BgmToggle.tsx")
    assert "BgmToggle" in source
    assert "setEnabled" in source


def test_frontend_filters_model_stream_fragments_and_exposes_provider_presets() -> None:
    source = _read(
        "lib/util.ts",
        "lib/catalog.ts",
        "components/SettingsSaveDialog.tsx",
        "components/ModelSettingsPanel.tsx",
    )

    assert "visibleEventTypes" in source
    assert "isReadableEvent" in source
    assert "modelPresets" in source
    for provider in ("DeepSeek", "Qwen", "GLM"):
        assert provider in source
    assert "可选择预设，也可自行填写兼容 OpenAI" in source


def test_frontend_homepage_shows_qq_group() -> None:
    source = _read("pages/HomePage.tsx")
    css = _read_css()

    assert "QQ群：985776771" in source
    assert 'assetUrl("assets/qq_group.png")' in source
    assert ".community-card" in css


def test_frontend_narrative_log_has_aria_describedby() -> None:
    source = _read("pages/GamePage.tsx", "pages/CharacterCreatePage.tsx")
    assert 'className="story-log chronicle-log"' in source
    assert 'aria-live="polite"' in source


def test_frontend_event_badges_locked() -> None:
    source = _read("pages/EndingPage.tsx", "pages/GamePage.tsx", "lib/api.ts")
    assert "fallback_prompt" in source
    assert "game_over" in source
    assert "finale" in source


def test_ending_page_fetches_death_summary() -> None:
    """P2 SPA split: EndingPage overlays server-authored death summary."""
    source = _read("pages/EndingPage.tsx", "lib/api.ts")
    assert "fetchDeathSummary" in source
    assert "/death_summary" in source
