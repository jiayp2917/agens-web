# Next Governance Backlog

This is the active backlog for `agens-web`. It separates local code work, local validation, and production/server work so local success is not mistaken for production acceptance.

## Current Evidence

- Current local code baseline includes sanitized model diagnostics and the 2026-07-04 attribute-scale cleanup.
- Validation after the latest P1 model-efficiency slice passed:
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web` -> 73 passed with local PostgreSQL `TEST_DATABASE_URL`
  - full `python -m pytest -q` with local PostgreSQL `TEST_DATABASE_URL` -> 503 passed
  - `cd web\frontend-react; npm.cmd run build` -> passed
  - `git diff --check` -> passed with LF/CRLF warnings only
- User-scoped model settings are implemented:
  - `/api/settings/model` is a logged-in user endpoint for personal config.
  - `/api/admin/settings/model` is the admin-only system-default endpoint.
  - `user_model_configs` stores one encrypted config per `user_id`; system default remains in `model_config`.
  - Runtime model calls resolve config by current session/user and do not mutate process-global `AGNES_API_KEY`.
- Previous dynamic-opening Chrome acceptance `local-visible-dynamic-opening-20260706-strict-live5` remains historical comparison evidence. The current local visible Chrome acceptance is `local-visible-p1-final-20260706`; generated evidence remains under `output/playwright/` and is ignored by default.
- Production P0 is accepted for the latest deployed production batch: server thread deployed `25ad3d15`, kept Alembic at `20260622_0005`, verified `user_model_configs`, health/catalog/container state, sanitized log scan, real-account flow, and production start+choice non-fallback with `turn_count=1`.
- Latest local code adds sanitized `model_result` diagnostics with numeric/boolean fields only: narrator/judge elapsed time, repair elapsed time, prompt size, history count, game-state size, and provider token counters when available. This is measurement, not a latency fix.
- Dynamic character-driven opening generation is implemented: difficulty, talent, spirit root, family background, six attributes, and random/manual mode feed a unified opening payload for world profile, 0-16 chronicle, age-16 situation, external intelligence, and initial A/B/C/D choices. Model-unavailable starts use profile-aware fallback and still surface fallback status; fallback remains invalid as live-model success.
- Current local working batch also closes the attribute-scale audit: runtime attributes are 0-10 with 5 as neutral, and old 0-100 values are compatibility inputs only. New realm, reward, catalog, or model-prompt logic must not use 50 as the neutral midpoint or 100 as the normal cap.
- Active phase plan remains `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`: P0 current batch is closed; next work is P1 gameplay quality and model-efficiency iteration without broad architecture changes.
- Current local P1 model-efficiency slice is verified by `local-visible-p1-final-20260706`: dynamic live start passed, 20/20 choice turns were non-fallback, save/load passed, fallback was 0, repair fell from 18/20 to 0/20, and judge fell from 6 to 3 turns. Reviewer follow-up fixed stage-feedback persistence and runtime opening-context pruning with automated coverage. Latency is improved from the earlier sampling run but remains a P1 tuning target: average choice latency was about 25.9s and max about 57.1s, with the remaining slow path in provider/narrator/judge latency, not repair calls.

## Lessons To Keep

- Do not count HTTP 200 as live-model success. Acceptance requires `fallback=false` and turn progression.
- Keep local, production, and code-change validation separate. Local Chrome success does not replace production non-fallback proof.
- Keep generated Playwright evidence out of normal commits unless explicitly promoted.
- Production reports must be sanitized: booleans, counts, revisions, table names, HTTP status, and error classes only. Do not output keys, cookies, real accounts, invite codes, database URLs, raw prompts, raw responses, or secrets.
- A healthy deploy can still fail gameplay acceptance; live-model fallback remains a product/runtime failure.
- Browser evidence must be strict JSON/NDJSON/CSV so future audits can parse it.
- Chrome playtests must not run concurrently with `tests\web` against the same database because Web tests truncate the shared test DB.
- Local service startup should reuse `scripts/start_local_pg.ps1` for PostgreSQL and then run backend/frontend separately on `127.0.0.1:8000` and `127.0.0.1:5173`; do not delete `.tmp\pg-test-20260626-55432` while PostgreSQL is running.

## P0: Acceptance And Deployment Gates

P0 is currently closed for the latest local and production batches. Re-run only when a gate is touched.

1. Production live-model gate.
   - Re-run after every production deployment, model-config change, provider change, or migration affecting runtime model calls.
   - Required proof: production start and at least one choice are non-fallback, and choice advances `turn_count`.
   - Server thread owns this gate.
2. Local visible Chrome 20-turn gate.
   - Re-run after gameplay pacing, state/chronicle consistency, option constraints, model-efficiency, or major UI-flow changes.
   - Required proof: start has a successful `world_builder`/`profile_opening` model event (`start_model_ok=true`), is non-fallback with 4 initial choices plus dynamic `world_profile` fields (`world_name`, `chronicle_0_16`, `initial_situation_16`), 20/20 choices are non-fallback, save/load works, `game_turns` stays continuous, and evidence is strict JSON/NDJSON/CSV.
   - Do not run concurrently with pytest against the same database.

## P1: Gameplay Quality And Model Efficiency

Next work should be data-led and gameplay-facing.

1. Continue latency work from the post-fix evidence.
   - `local-visible-p1-final-20260706` shows repair is no longer the dominant cost: repair 0/20, judge 3 turns, average narrator about 22.5s, average judge about 21.8s.
   - Do not treat the repair reduction as a full performance fix; total choice latency is still too high.
2. Choose the next latency fix from evidence.
   - If prompt/history grows: compress `chat_history` into summary + recent turns.
   - If narrator still emits narrative-only outputs: tighten the narrator output contract/parser without accepting missing narrative or missing usable choices as success.
   - If judge dominates: narrow judge trigger conditions to authoritative/risky state changes.
   - If provider dominates: document model performance differences and rely on user-configurable providers.
3. Improve 20-turn playable content.
   - Add the 0-16 岁 opening chronicle per `docs/GAME_MODE_SPEC.md` §3.5.
   - Continue improving 3-5 turn stage feedback; the first lightweight every-fourth-turn `world.lore_add` feedback is implemented but not enough for full content quality.
   - Build event pools for steady, opportunity, risk, and luck routes.
   - Reduce repeated retreat/breakthrough loops.
   - Keep small-realm progress mostly implicit; reserve major breakthroughs for stage events.
   - Keep Qi Refining pacing credible: age and turn count should prevent a 20-turn slice from lingering in early small layers.
   - Keep the sidebar "外界情报" read-only and fed by existing world summaries; do not turn it into a new resource system until the gameplay design explicitly calls for one.
4. Tighten authoritative state accounting.
   - Key items, techniques, attribute growth, titles, relationships, injuries, lifespan, realm changes, and karma must be structured state or rewritten/suppressed.
   - Ordinary chronicle rumors, intentions, or non-authoritative color text do not automatically become inventory.
   - Model text can polish narrative and choices, but cannot decide authoritative numbers.
   - Breakthrough text is especially strict: success/failure/death/fall-back results must match the rule delta, and "修为尽废" is forbidden unless the rule engine actually performs severe loss or terminal failure.

## P1: Complexity Governance

Only do complexity work that supports the main flow.

- `tests/web/test_web_api.py`: split by account/model settings/session/save-load/turn persistence when touched.
- `web/backend/service.py`: extract session progression, model config resolution, persistence, and error mapping helpers without changing API behavior.
- `web/backend/database_postgres.py`: extract row shaping and repeated SQL helpers without schema changes.
- `src/agens_novel/engine/game_engine.py`: make small slices around fallback, breakthrough, local story, and model failure.
- Avoid broad router rewrites or architecture restructuring unless a blocking bug proves it necessary.

## P2: Documentation And Cleanup

- Keep `docs/INDEX.md`, `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`, `docs/GAME_MODE_SPEC.md`, `docs/RUNTIME_FLOW.md`, and this file aligned.
- Historical planning drafts and UI prototypes have been removed from `docs/archive/`; current state belongs in current docs, and history belongs in `CHANGELOG.md` or concise lessons sections.
- Keep `scripts/start_local_pg.ps1` as the PG startup/recovery helper. Do not delete `.tmp\pg-test-20260626-55432` while PG is running.
- `output/playwright/` remains ignored generated evidence. Do not stage it in ordinary code/docs commits.

## 2026-07-06 Subagent Audit - Refined Plan

Sourced from the read-only subagent audit (see `docs/PROJECT_AUDIT.md` same-date section). No code changed in this pass; the following is the prioritized execution queue. The plan was reviewed by an independent critique agent, which dropped one fabricated item (a plan file that does not exist in this repo), promoted the secret-redaction drift to P0, and corrected the dead-chain verification to acknowledge a remaining test reference.

**Status (2026-07-06):** All P0/P1/P2 items below were executed in commits `cd57215..026cd69` — secret-marker unification, catalog except narrowing, default-literal consolidation, local-story chat_history fix + `record_turn`, dead profile-opening chain removal, zero-caller helpers/PNG/component removal, `_prompt_metrics` unification, `WebGameService` split (`ModelConfigService` + `DeathRewardsService`), flow→engine coupling convergence, and doc structure fixes. See the CHANGELOG same-date "governance audit execution" entry for the full summary. The items below are retained as the execution record; none remain open. The only deferral was `save_artifact` audit-dict extraction (verifier found agent-specific parse/return logic dominates — kept inline per the simplicity guideline).

### P0 (security / factual - do first)

1. Unify the secret-redaction marker list.
   - Current: `engine/game_engine.py:58` (7 markers) and `web/backend/service.py:51` (9 markers) diverge; the engine copy fails to redact `postgresql://` and sits on the model-failure log surface.
   - Action: define one `SECRET_MARKERS` in a shared low-level module and import it in both; do not broaden redaction semantics.
   - Verify: a reason string containing `postgresql://user:pass@host` is redacted on both engine and service log paths; existing secret-safe tests pass.

### P1 (high-leverage quality / correctness)

2. Split the `WebGameService` god class.
   - Extract `ModelConfigService` (the 7 `_*_model_config` methods + encryption glue) and `DeathRewardsService` (`death_summary` + 4 helpers + `_persist_death_rewards`) into separate modules, mirroring the existing `service_summaries.py` split.
   - Verify: `tests/web` and full pytest pass; API behavior unchanged.
3. Tighten flow->engine private coupling.
   - The three `*Flow` classes are instantiated only in `GameEngine.__init__` with zero reuse; either promote the called `engine._*` helpers to public methods and type `engine` as `GameEngine`, or fold the flows back into `game_engine.py`.
   - Verify: flows no longer reference `engine._` privates; engine and flow-failure-path tests pass.
4. Remove the verified-dead StartFlow / profile-opening chain.
   - `generate_world_profile`, `generate_profile_opening`, and their GameEngine wrappers have zero callers repo-wide; delete them and collapse `generate_world_profile` to `return build_world_fallback(profile)`.
   - Verify: zero non-test references in `src/`/`web/` after removal; `tests/unit/game/test_character_create.py:265` still does `monkeypatch.delenv("AGNES_START_MODEL_WORLD")` and must be removed in the same change; full pytest passes.
5. Fix the local-story turn-history gap.
   - `handle_local_story_action` (`turn_flow.py:71-81`) omits the chat_history append+compact, so local-story turns silently never enter narrator prompt history.
   - Action: extract one `session.record_turn(input, narrative, delta, *, local_story=None)` and route all four turn-recording sites through it.
   - Verify: a local-story turn appends to `chat_history`; relevant engine tests pass.
6. Consolidate default base_url/model literals to `Settings`.
   - 11 inline sites (`service.py` x4, `agents/common.py`, `game_engine.py`, `turn_runner.py`, `llm/client.py`, `database_postgres.py`, `app_models.py`) read from `Settings()` or a single constant instead.
   - Verify: grep for `apihub.agnes-ai.com` / `agnes-2.0-flash` hits only `settings.py`; full pytest passes.
7. Narrow the catalog bare `except Exception`.
   - `service.py:883,891` silently swallow DB errors and return empty catalog/grade; narrow to specific exceptions and `log.warning`.
   - Verify: catalog fetch failures are visible in logs and still return safe values; catalog tests pass.

### P2 (cleanup / boilerplate consolidation)

8. Consolidate agent LLM-call + `save_artifact` + `_prompt_metrics` boilerplate into `agents/common.py` (the repo's established dedup pattern).
9. Remove verified zero-caller helpers: `default_lifespan_for_realm`, `RealmSystem.public_realm_name`, `choices.display_choice_text`, `profile_opening.profile_concept`, `lib/util.randomBetween`, `paths.save_path`, the 6 `render.py` formatters and their tests. Note: removing `StatLine.tsx` requires also updating `tests/web/test_frontend_contract.py:209,220`; `_session_flags`/`_inventory_text` must NOT be removed (`realm.py:136-137` uses them).
10. Remove the 3 unreferenced tracked PNGs under `output/` (`agens-web-local-pg-*`).
11. Governance doc structure cleanup (low priority): drop the duplicate condensed guidelines block in `AGENTS.md`; fix the `## 实现状态` heading nested inside a `>` blockquote in `GAME_MODE_SPEC.md`; split dated evidence out of the "current status" sections in `INDEX`/`RUNTIME_FLOW`.

### Items to retire / demote in the existing backlog

- "Keep the sidebar 外界情报 read-only" is already a stable invariant; demote from active P1 to a governance note.
- The repair/judge P1 sub-bullets ("tighten narrator output contract/parser", "narrow judge triggers") should be narrowed: repair is already 0/20 and judge is 3, so the lever is largely exhausted; remaining latency work should focus on provider/narrator first response and history compression.

### 留后续项（2026-07-06 审计未处理）

下述条目经 6 维度 finder + 3 verifier 对抗式复核核实，未在 `cd57215..026cd69` 执行批次处理；按主流程需要或单独批次推进。Complexity Governance 段中 `service.py` 的 model-config/persistence 抽取与 `game_engine` 的 flow 耦合收敛已完成，其余方向仍适用该段指引。**复核推翻的项**（三套 merge helper 合并、`normalize_choices` 合并、world-reset 关键词、`_choose_model_failure` 误判）见 `docs/PROJECT_AUDIT.md` "2026-07-06 复核审计" 段，不再列为待办。

**死代码清理批次（verifier 确证零调用，低风险，建议优先）**：

- `GameEngine.expand()`（`engine/game_engine.py:379`）— 零调用任何位置。
- `GameEngine.get_log()` + `format_log()`（`game_engine.py:418` + `render.py:51`）+ `engine/README.md:20` doc row — 仅测试。
- `local_story_available()`（`engine/local_story.py:295`）— 零调用。
- `validate_local_story_graph()`（`engine/local_story.py:402`）— 仅测试，删除须同步删 `tests/unit/engine/test_local_story_fallback.py`。
- `ensure_runtime_dirs()` + `CHECKPOINT_DIR`（`paths.py:28,21`）— 仅 `tests/conftest.py`，删除须同步迁移 conftest 用法。
- `MODEL_FAILURE_PROMPT` import（`game_engine.py:38`）— 未用 import（常量本身亦零引用）。

**已评估、有意不做**：

- `save_artifact` audit dict 抽取：verifier 发现 agent-specific parse/return 逻辑占主导，抽取增间接层、收益 modest。
- `call_agnes_llm` 整体合并：narrator 因 streaming + repair 特殊化无法干净合并（judge + world_builder 的部分抽取见下条"待办"）。

**待办（按主流程需要推进）**：

- `narrator/nodes.py` 539 行解析器堆积（7+ 私有 JSON 容错 helper，含手写括号深度状态机，`nodes.py:226-525`）：refactor 候选，需谨慎不改 parse 语义，独立批次 + 充分测试预算。
- `call_agnes_llm` 抽 `common.call_agnes_llm_common`（prelude + 单次非流式 call + epilogue）：仅 judge + world_builder 适用，narrator 保留（streaming/repair）。MEDIUM。
- bare-except：catalog 2 处已收窄为 `SQLAlchemyError`；`web/backend/service.py:101,638` 仍剩 2 处，全仓库其余分散处待逐处评估收窄 + `log.warning`。
- `normalize_choices` docstring drift：`agents/common.py:9-10` 与 `docs/ARCHITECTURE.md:82` 声称"复用 engine choice 清理"但实际没有——修 docstring，不改实现。
- `start_flow` confirm→fallback-or-end 模式重复 6 次（`start_flow.py:76-95,165-217`）：低优先，可抽 helper。
- A/B/C/D letter→index 映射（`game_engine.py:343`、`service.py:709`）：服务不同输入面，不强合并；可选 `dict(zip(CHOICE_LABELS, range(4)))` minor cleanup。
- `import logging` 位于 `service.py` 文件尾（`# noqa: E402`）：移到文件头，低优先。
- CHANGELOG 旧条目称普通回合 `repair=True`（`CHANGELOG.md:438-440`，已被当日顶部条目反转）：可选标注 superseded。

**跨文件协同（单独一次处理）**：

- `AGENTS.md` 与 `CLAUDE.md`（含 `D:\chat\CLAUDE.md`）的"通用编码准则"块近乎逐字重复：涉及多个治理根文件协同修改，2026-07-06 审计明确留作单独一次处理。

**待固化的 retire/demote 决策**：

- "Keep the sidebar 外界情报 read-only" 已是稳定不变量，建议从 P1 §3 活动 demote 为 governance note（现仍在 P1 第 70 行）。
- repair/judge P1 sub-bullets：repair 已 0/20、judge 3 次，lever 基本耗尽；剩余延迟工作应聚焦 provider/narrator 首次响应与 history 压缩（现仍在 P1 §1-2）。

## Validation Rules

- Backend/service changes:
  - targeted tests first
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web`
  - full `python -m pytest -q` when touching shared gameplay/service code
- Frontend/UI changes:
  - `npm.cmd run build`
  - visible Chrome smoke for changed viewport/workflow
- Production:
  - follow `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`
  - never read or print secrets
  - never use `AGENS_PG_AUTO_DDL=1` in production
  - never count fallback as live-model success
