from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_contains_required_web_views() -> None:
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")

    for selector in (
        'id="homeView"',
        'id="characterView"',
        'id="gameView"',
        'id="endingView"',
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


def test_frontend_does_not_embed_api_key_or_hidden_rules() -> None:
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


def test_frontend_exposes_fallback_choice_without_hidden_rule() -> None:
    js = (ROOT / "web" / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "/end" in js
    assert "fallback_prompt" in js
    assert "结束本局" in js
