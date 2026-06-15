"""Buildozer configuration contract tests."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read_spec() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / "mobile" / "buildozer.spec").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_buildozer_packages_android_only_runtime_assets():
    spec = _read_spec()

    assert spec["source.dir"] == ".."
    assert "main.py" in spec["source.include_patterns"]
    assert "bgm.flac" in spec["source.include_patterns"]
    assert "mobile/**/*" in spec["source.include_patterns"]
    assert "src/agens_novel/**/*" in spec["source.include_patterns"]
    assert "config/**/*" in spec["source.include_patterns"]
    assert "png" in spec["source.include_exts"].split(",")
    assert "flac" in spec["source.include_exts"].split(",")


def test_buildozer_excludes_non_product_paths():
    spec = _read_spec()

    excluded = {part.strip() for part in spec["source.exclude_dirs"].split(",")}
    assert {"tests", "docs", "runtime", ".venv311"}.issubset(excluded)


def test_final_image_assets_exist_and_are_used_by_android_ui():
    assets = ROOT / "mobile" / "assets" / "images"
    expected = {
        "ink_mountain_gate.png": ["mobile/screens/home_screen.py", "mobile/screens/game_screen.py"],
        "paper_texture.png": ["mobile/theme.py"],
        "death_mist_path.png": ["mobile/screens/death_screen.py"],
        "ascension_gate.png": ["mobile/screens/death_screen.py"],
    }

    for filename, source_paths in expected.items():
        asset = assets / filename
        assert asset.exists(), filename
        assert asset.stat().st_size > 1024, filename
        for source_path in source_paths:
            source = (ROOT / source_path).read_text(encoding="utf-8")
            assert filename in source
