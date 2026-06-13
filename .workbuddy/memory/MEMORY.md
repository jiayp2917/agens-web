# Project Memory - AI Xianxia Simulator (agens_novel)

## Project Overview
- Python package: `agens_novel` — AI-powered xianxia cultivation simulator
- Location: `D:\chat\agens\src\agens_novel\`
- Tech stack: Pure Python (no frontend), LLM-driven narrative engine

## Key Architecture
- Engine: `engine/game_engine.py` — core game loop, action handling
- REPL: `repl/game_session.py`, `repl/loop.py`, `repl/save_manager.py` — interactive session
- Game logic: `game/constants.py`, `game/realm.py`, `game/combat.py`, `game/game_schema.py`, `game/reducers.py`
- LLM: `llm/client.py` — API client with built-in key fallback
- Judge: `judge/nodes.py` — content validation, default approved=False (safe default)
- Prompts: `prompts/judge.md`, `prompts/narrator.md`, `prompts/combat_narrator.md`, `prompts/world_builder.md`

## Test Suite
- 435 tests across 14 files, all passing
- Core test files in `tests/unit/`

## Known Design Notes
- `_has_api_key()` always returns True (built-in key fallback) — not a bug, intentional
- Judge defaults to `approved=False` on parse failure (security feature)
- HP is clamped to `[0, hp_max]` to prevent overflow
- Import convention: modules in `repl/` use `from ..game.constants` (two dots, not one)

## Team Workflow
- This project went through standard SOP: PM → Architect → Engineer → QA
- 1 bug found in QA (import path in game_session.py), fixed by team lead directly
- 16 test bugs (outdated assertions) fixed by QA engineer