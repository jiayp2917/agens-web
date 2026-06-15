# Changelog

## [Unreleased]

### Added
- GitHub Actions CI pipeline (`.github/workflows/ci.yml`) — pytest + ruff on windows-latest
- `ARCHITECTURE.md` describing module layering and data flow
- Restructured test layout: `tests/{e2e,integration,unit,mobile,destructive}`

### Changed
- Test split: large test files broken into focused modules (1038 lines → 3 files)
- Single Kivy entry: only `mobile/main.py`, root `main.py` removed
- `AGENTS.md` and `CLAUDE.md` updated for Android-only workflow
- `.gitignore` covers dev residues, demo artifacts, and audio assets

### Removed
- Terminal REPL/CLI entry points and old terminal UI modules
- Stale demo screenshots (moved to `F:\Projects\test`)

### Fixed
- BGM file path resolution updated to `mobile/assets/audio/`
- Test imports use `mobile.audio_manager` package path

## 2026-06-14

### Changed

- Project direction is Android-only. The supported product entry is the Kivy/Buildozer mobile app.
- Shared game state, persistence, and agent turn execution live outside the old terminal UI namespace.
- The game screen uses a single A/B/C/D flow: A/B/C choices come from the model or fallback logic, and D is the player typed action.
- Secondary tools are opened through the Android "more" sheet instead of permanent bottom buttons.
- Combat is handled by typed natural-language actions and a compact status strip, not permanent combat buttons.

### Removed

- Terminal product entry points and old terminal UI modules.
- Android slash-command routing from the D input box.
- Stale mobile screens that had been replaced by home popups and the current game screen.

### Fixed

- Buildozer now packages from the repository root, including `main.py`, `mobile/**/*`, `src/agens_novel/**/*`, `config/**/*`, and `bgm.flac`.
- BGM packaging includes the `flac` extension.
- Mobile startup resolves `AGENS_NOVEL_ROOT` to the packaged repository root.

### Verification

- Use `python mobile/main.py` for desktop Kivy debugging.
- Use `buildozer android debug` from `mobile/` for APK builds.
- Run `python -m compileall -q src tests mobile/main.py mobile/audio_manager.py mobile/screens mobile/widgets mobile/service demo_full_flow.py`.
- Run `python -m pytest -q`.
