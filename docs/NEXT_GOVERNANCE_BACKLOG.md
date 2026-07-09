# Next Governance Backlog

This is the active backlog for `agens-web`. It separates local code work, local validation, and production/server work so local success is not mistaken for production acceptance.

## Current Evidence

- Current local code baseline includes sanitized model diagnostics, the 2026-07-04 attribute-scale cleanup, the 2026-07-07 P1 gameplay-state slice, the 2026-07-08 chronicle-content slice, and the 2026-07-09 visible content-audit/de-duplication batch.
- Validation after the latest local P1 visible content-audit batch passed:
  - `python -m compileall -q src tests web scripts migrations`
  - `python -m pytest -q tests\web` -> 74 passed with local PostgreSQL `TEST_DATABASE_URL`
  - full `python -m pytest -q` with local PostgreSQL `TEST_DATABASE_URL` -> 555 passed
  - `cd web\frontend-react; npm.cmd run build` -> passed
  - `git diff --check` -> passed with LF/CRLF warnings only
- User-scoped model settings are implemented:
  - `/api/settings/model` is a logged-in user endpoint for personal config.
  - `/api/admin/settings/model` is the admin-only system-default endpoint.
  - `user_model_configs` stores one encrypted config per `user_id`; system default remains in `model_config`.
  - Runtime model calls resolve config by current session/user and do not mutate process-global `AGNES_API_KEY`.
- Previous dynamic-opening Chrome acceptance `local-visible-dynamic-opening-20260706-strict-live5`, `local-visible-p1-final-20260706`, `local-visible-history-softcap-c1d8628-20260707`, `local-visible-a69a8af-20260708`, and `local-visible-chronicle-events-routes-20260708` remain historical comparison evidence. The current visible content-audit evidence is the 2026-07-09 batch listed below; generated evidence remains under `output/playwright/` and is ignored by default.
- Production P0 is accepted for the latest deployed production batch: server thread deployed `25ad3d15`, kept Alembic at `20260622_0005`, verified `user_model_configs`, health/catalog/container state, sanitized log scan, real-account flow, and production start+choice non-fallback with `turn_count=1`.
- Latest local code adds sanitized `model_result` diagnostics with numeric/boolean fields only: narrator/judge elapsed time, repair elapsed time, prompt size, history count, game-state size, and provider token counters when available. This is measurement, not a latency fix.
- Dynamic character-driven opening generation is implemented: difficulty, talent, spirit root, family background, six attributes, and random/manual mode feed a unified opening payload for world profile, 0-16 chronicle, age-16 situation, external intelligence, and initial A/B/C/D choices. Model-unavailable starts use profile-aware fallback and still surface fallback status; fallback remains invalid as live-model success.
- Current local working batch also closes the attribute-scale audit: runtime attributes are 0-10 with 5 as neutral, and old 0-100 values are compatibility inputs only. New realm, reward, catalog, or model-prompt logic must not use 50 as the neutral midpoint or 100 as the normal cap.
- Active phase plan remains `docs/PLAYABLE_GAMEPLAY_ROADMAP_20260629.md`: P0 current batch is closed; next work is P1 gameplay quality and model-efficiency iteration without broad architecture changes.
- Previous local visible Chrome baseline `local-visible-chronicle-events-routes-20260708` remains historical comparison evidence: dynamic live start passed, 20/20 choice turns were non-fallback, save/load passed, fallback was 0, repair stayed 0/20, judge ran 4 turns, average choice latency was about 17.35s and max about 59.3s. The current content-quality baseline is the 2026-07-09 `final2` batch below.
- 2026-07-07 defensive runtime batch is closed: malformed nested `state_delta.character/world/meta` sections are ignored with warnings instead of crashing; `fallback_prompt.active` now reflects current failure/local-story state rather than historical `model_failure` events and is restored from persisted events when a runner is rebuilt; `/choice` accepts `choice_index`, A/B/C/D, and `"1"`-`"4"` while still rejecting free text.
- 2026-07-07 P1 gameplay-state slice is closed in automation and was later covered by the `a69a8af` Chrome run: stage feedback uses deterministic route events; ordinary-turn narrative consistency is checked after model delta sanitization and rule-delta merge; Judge reviews technique grants and sensitive inventory grants such as breakthrough, lifespan, key-item, inheritance, or high-rarity items.
- 2026-07-08 chronicle-content batch is accepted locally: four fixed world packs are centralized, profile starts save a structured `fate_profile`, ordinary turns use a data-driven event catalog, narrator results expose sanitized contract diagnostics, and `/choice` now preserves A/B/C/D route semantics before rule settlement. Verified by full automation and `local-visible-chronicle-events-routes-20260708`.
- 2026-07-08 visible content-audit tooling is available but does not by itself prove content quality. `scripts/local_visible_playtest.cjs` now has opt-in content-audit snapshots, preserves issue category labels even when captured UI text is stored, and flags `judge_failed` as a P1 consistency issue. `scripts/local_visible_content_audit.cjs` can orchestrate the base 20-turn run, four route-biased 20-turn runs, a mixed long run, and a double-click probe.
- 2026-07-09 current content-audit evidence: final accepted batch is `local-content-basic-cycle-final2-20260709`, `local-content-route-{a,b,c,d}-final2-20260709`, and `local-content-mixed-60-final2-20260709`. Base, route A, route B, and route D completed 20/20 live turns; route C reached a natural terminal state at turn 19; mixed reached a natural terminal state at turn 49. Every final run had `fallback_count=0`, P0 0, P1 0, no player-visible forbidden text, no repeated exact chronicle hits, and strict JSON/NDJSON/CSV evidence. Final D: `avg_elapsed_ms=14365`, `max_elapsed_ms=64150`, `narrator_incomplete_output_count=16`, save/load passed. Mixed: 49 accepted non-fallback live turns, `max_previous_similarity=0.59`, `avg_elapsed_ms=9305`, `max_elapsed_ms=64085`, `narrator_incomplete_output_count=46/49`, `judge_count=4`.
- Remaining P1/P2 after the 2026-07-09 content-audit batch: narrator output is still structurally unreliable (`narrator_incomplete_output_count=46/49` in the mixed run, mostly missing `state_update` / bad choices), live latency still has long tails, and terminal-page UI capture is incomplete after game-over (`passed_terminal` proves API terminal state, but the post-terminal UI snapshot fields are empty). Keep tightening narrator contract and improve terminal evidence capture before inviting broader real-player testing.

## Lessons To Keep

- Do not count HTTP 200 as live-model success. Acceptance requires `fallback=false` and turn progression.
- Keep local, production, and code-change validation separate. Local Chrome success does not replace production non-fallback proof.
- Keep generated Playwright evidence out of normal commits unless explicitly promoted.
- Production reports must be sanitized: booleans, counts, revisions, table names, HTTP status, and error classes only. Do not output keys, cookies, real accounts, invite codes, database URLs, raw prompts, raw responses, or secrets.
- A healthy deploy can still fail gameplay acceptance; live-model fallback remains a product/runtime failure.
- Browser evidence must be strict JSON/NDJSON/CSV so future audits can parse it.
- Treat UI text as first-class evidence before inviting real players. A passing 20-turn technical Chrome run proves flow stability, not that the chronicle is readable, non-repetitive, or free of player-visible fallback/internal text.
- Chrome playtests must not run concurrently with `tests\web` against the same database because Web tests truncate the shared test DB.
- Local service startup should reuse `scripts/start_local_pg.ps1` for PostgreSQL and then run backend/frontend separately on `127.0.0.1:8000` and `127.0.0.1:5173`; do not delete `.tmp\pg-test-20260626-55432` while PostgreSQL is running.
- Treat model output as untrusted at every authority boundary. Malformed nested `state_delta` sections should be ignored with diagnostics, not allowed to crash a turn.
- Keep UI prompt state explicit and current. Do not infer current fallback visibility by scanning whether any historical `model_failure` event ever occurred.
- Keep API choice compatibility narrow and deterministic: `choice_index`, A/B/C/D, and exact `"1"`-`"4"` are valid; free text, mixed strings, and out-of-range values stay invalid.

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
3. Visible content-audit gate before real-player testing.
   - Run with content audit enabled after major gameplay-content, narrator-contract, timeline, or option-generation changes.
   - Required proof: no player-visible fallback/internal text, no JSON/tag/English residue, no consecutive repeated chronicle entries, external intelligence changes or has an explicit reason within 3-5 turns, timeline age/status stay coherent, and choices remain four non-empty A/B/C/D semantic buttons.
   - Full batch command: `node scripts/local_visible_content_audit.cjs`. For a shorter smoke run, set `AGENS_CONTENT_AUDIT_RUNS=base`.
   - Current blockers: route-biased content audits and the mixed-run high-similarity repetition are closed in the 2026-07-09 batch. Remaining work is to reduce narrator incomplete/missing-structure dependency, improve terminal-page evidence capture, and continue treating future provider request fallback as non-acceptance for that run.

## P1: Gameplay Quality And Model Efficiency

Next work should be data-led and gameplay-facing.

1. Continue latency work — **2026-07-06 narrator 采样重塑优先级**。
   - `narrator-sample-20260706`（20 回合 chrome-devtools 采样，见 `docs/PROJECT_AUDIT.md` 同日采样段）：平均回合 ~30.4s、max 65.6s；**repair 率 70%（14/20），repair 占总延迟 56%**；history cap 20 后 repair 率 ~100%。
   - **这推翻 `local-visible-p1-final-20260706` 的 "repair 0/20，lever exhausted"** —— 当前 narrator 契约在 history 增长后频繁失效（p1-final 与本采样 repair 率差异大，可能因模型 key/版本/配置不同）。
2. 杠杆排序（采样驱动）：
   - **history 压缩**（最高杠杆）：第一批软上限切片已落地；`local-visible-chronicle-events-routes-20260708` 显示 repair 0/20、平均约 17.35s、最大约 59.3s。后续重点从“repair 次数”转向 narrator/provider 长尾、输出契约和内容质量。
   - **narrator 输出契约/解析器重构**（次高，高风险）：`nodes.py` 539 行解析器堆积，独立批次 + 充分测试。本采样已证明它是根因，不再是"先采样再决定"。
   - repair 是契约失效的后果，不是独立杠杆。
   - judge elapsed 全 0（非源）；provider narrator 首次 ~13.4s（可接受）。
3. Improve 20-turn playable content.
   - 0-16 岁 opening chronicle is implemented in the dynamic-opening chain; keep it as a regression guard, not a fresh task.
   - First deterministic stage-feedback/event-pool slice has been expanded into a structured world-pack/fate-profile/event-catalog design. Every turn now has event context for narrator, and every fourth turn persists stage feedback to `world.lore_add`.
   - Next content work should continue enriching the event catalog depth, route-specific consequences, and third-person chronicle texture; the current batch already has real 20-turn Chrome coverage.
   - Reduce repeated retreat/breakthrough loops.
   - Keep small-realm progress mostly implicit; reserve major breakthroughs for stage events.
   - Keep Qi Refining pacing credible: age and turn count should prevent a 20-turn slice from lingering in early small layers.
4. Tighten authoritative state accounting.
   - Key items, techniques, attribute growth, titles, relationships, injuries, lifespan, realm changes, and karma must be structured state or rewritten/suppressed.
   - Current automation covers attribute-growth claims against final post-sanitize/post-rule-merge delta, technique grants, and sensitive inventory Judge routing; keep extending this for ordinary-turn titles, relationships, injuries, lifespan, and karma.
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

- Governance invariant (demoted from P1 §3): the sidebar "外界情报" is read-only, fed by existing world summaries; it is not a future resource system unless the gameplay design explicitly calls for one.
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

### 留后续项（2026-07-06 复核审计后，本轮处理后剩余）

2026-07-06 复核审计（见 `docs/PROJECT_AUDIT.md` 同日"复核审计"段）登记的多数遗留项已于本轮（commits `f7fa7e8`..`59dc483` + retire/demote 固化批）处理：死代码 7 项清理、`call_agnes_llm` 抽 common、`import logging` 迁移、`normalize_choices` docstring drift、CHANGELOG superseded 标注、AGENTS↔CLAUDE 仓库内准则块 source-of-truth 标注、`start_flow` 抽 `decline_or_continue` closure、retire/demote 固化（外界情报 demote 到 P2、repair/judge bullets 收窄）。bare-except 8 处与 A/B-C/D zip 经评估**保留/跳过**。复核推翻的项（三套 merge helper 合并、`normalize_choices` 合并、world-reset 关键词、`_choose_model_failure` 误判）见 PROJECT_AUDIT 复核段，不再列为待办。以下为仍未处理项：

**已评估、有意不做**：

- `save_artifact` audit dict 抽取：agent-specific parse/return 逻辑占主导，抽取增间接层、收益 modest。
- `call_agnes_llm` narrator 合并：streaming + repair 特殊化无法干净合并（judge + world_builder 已抽取）。
- bare-except 8 处收窄：经评估均为 intentional defensive seam（LLM 失败兜底 / UI callback / decode fallback），收窄风险 > 收益。
- A/B-C/D letter→index zip cleanup：`game_engine.py:343` 含数字键（zip 不适用），`service.py:709` 字面量比 zip+import 更直白，净收益为负（见 commit `59dc483` 评估说明）。

**待办（按主流程需要推进）**：

- `narrator/nodes.py` 539 行解析器堆积（7+ 私有 JSON 容错 helper，含手写括号深度状态机，`nodes.py:226-525`）：refactor 候选，**高风险**，需谨慎不改 parse 语义，独立批次 + 充分测试预算。建议先以 20 回合采样数据证明它是延迟/契约根因再动。

**跨仓库（不在本仓库范围）**：

- `D:\chat\CLAUDE.md`（上级工作区治理文件）的"通用编码准则"块与本仓库 `AGENTS.md`/`CLAUDE.md` 仍重复：本仓库内已加 source-of-truth 维护说明，跨仓库同步需在上级工作区单独处理。

**retire/demote 决策（2026-07-06 已固化）**：

- "Keep the sidebar 外界情报 read-only" 已从 P1 §3 活动 demote 为 P2 governance invariant。
- repair/judge P1 sub-bullets 已收窄为“repair 不是独立杠杆”。2026-07-07 复采显示 repair 仍为 0/20，但 judge 为 5 次且总耗时仍高；P1 §1-2 当前应聚焦 provider/narrator 长尾、模型输出契约和 judge 调用成本。

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
