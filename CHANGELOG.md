# Changelog

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
