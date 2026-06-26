# Changelog

## 2026-06-26

### Changed — P2 引擎包装内联 + runner 缓存泄漏修复 + .gitignore 加固

- **GameEngine 无意义包装内联**：删除 5 个纯透传包装方法（`_is_pure_cultivation` / `_apply_breakthrough_flag_rule` / `_validate_narrative_delta_consistency` / `_merge_rule_delta` / `_advance_local_story`）与 no-op `_auto_save`（被 3 个 Flow 文件 6 处调用）；`TurnFlow` 改为直接 import `action_delta_policy` 底层函数。模块级 `_merge_rule_delta` 迁入 `action_delta_policy.py` 公开为 `merge_rule_delta`（与其余 3 个 delta helper 同处）。`test_is_pure_cultivation_detection` 同步改为直接测 `is_pure_cultivation`。净减 ~90 行，调用链少一层。
- **runner 缓存泄漏修复（重新落地）**：`WebGameService.runners` 字典长期无界增长——`ff5eee0`（post-Option-C quality pass）曾删除 `75099e8` 引入的 `_prune_idle_runners` 及其调用点，泄漏随之回归（CHANGELOG 未同步）。本轮以 LRU cap（128）+ idle TTL（30 min）双维度淘汰重新实现：新增 `_register_runner` / `_prune_runners` / `_drop_runner`，统一 `create_session` / `load` / `_runner` 三处写入点并在缓存命中时刷新访问时间。注册用户 runner 落库可经 `_runner` 懒加载重建（近乎无损）；guest runner 不落库，被淘汰即该访客会话失效（接受的权衡）。
- **`.gitignore` 加固**：新增 `.mcp.json` 规则（Claude Code 项目级 MCP 配置，按惯例保持本地未跟踪），`git status` 不再显示 `?? .mcp.json`。

### Changed — 代码审计质量复核后清理（build + 文档）

- **Dockerfile 层缓存**：`pip install -e .` 行加 BuildKit 缓存挂载 `--mount=type=cache,target=/root/.cache/pip` 并移除 `--no-cache-dir`，恢复增量构建依赖缓存（消除双依赖源后 `COPY src` 位于 install 之前，曾导致每次 src 变更重解析依赖）；补 `# syntax=docker/dockerfile:1` 显式启用 BuildKit 前端。
- **文档同步**：`docs/ARCHITECTURE.md` §4.2 补 `agents/common.py` 共享 helper 行，并修正 World Builder 行残留的 `_normalize_choices`（第二轮已迁至 `common.normalize_choices`）。
- **过时 SQLite / `DATABASE_BACKEND` 引用清理**（仅当前态文档，历史日志与 incident 记录不动）：
  - `docs/PROJECT_AUDIT.md`：目标架构数据层、目标调用链改为 PostgreSQL 单后端；技术债「SQLite/PostgreSQL 双轨」标记为方案 C 已解决。
  - `docs/RUNTIME_FLOW.md`：代码链路与生产数据库接入约束改为 PostgreSQL 单后端。
  - `docs/security.md`：生产 env 移除已不被读取的 `DATABASE_BACKEND=postgresql`（`security.is_production_mode()` 与 `database.py` 均只认 `AGENS_ENV` / `DATABASE_URL`）。

### Changed — SQLite / `DATABASE_BACKEND` 残留彻底清理（全仓多智能体扫描后）

接续上文「待跟进」项。全仓扫描 35 处 `sqlite`/`SQLite`/`database_sqlite`/`DATABASE_BACKEND` 引用，逐条分类（4 当前态过时 / 10 正确注释 / 17 历史记录 / 4 测试残留），仅清理当前态与测试残留，历史日志与 incident 记录全部保留：

- `deploy/production.env.example`：移除已不被任何生产代码读取的 `DATABASE_BACKEND=postgresql`。
- `web/backend/database_postgres.py:33`：`DATABASE_URL` 缺失的错误信息原写「when DATABASE_BACKEND=postgresql」（误导，该变量已不被读取），改为与 `database.py` 一致的「PostgreSQL-only since the Option C consolidation」。
- `tests/web/test_web_api.py`：移除 3 处 vestigial `setenv`（`AGENS_WEB_DB=...sqlite3`、`DATABASE_BACKEND=sqlite`、`DATABASE_BACKEND=postgresql`）——生产代码均不读取，连接由 `DATABASE_URL` 驱动。
- `tests/web/conftest.py`：移除 autouse 夹具中 vestigial 的 `setenv("DATABASE_BACKEND", "postgresql")`。
- `docs/GAME_MODE_SPEC.md` 实现状态表、`docs/NEXT_GOVERNANCE_BACKLOG.md` P1 backlog：双轨表述改为 PostgreSQL 单后端。

前一轮「待跟进」列出的项目现已全部完成；全仓再无当前态的 SQLite/`DATABASE_BACKEND` 残留（剩余命中均为历史日志、CHANGELOG 条目或正确解释现状的代码注释，按规则保留）。

## 2026-06-25

### Changed — 代码审计执行（方案 C：数据库统一 PostgreSQL）

执行审计计划 `zesty-popping-graham.md` 的 P0/P1/P2/P3：

- **P0 安全/稳定**：`web/backend/app.py` 在 `create_app()` 调用 `setup_logging()` 安装 `SecretRedactor`，防止 API key 从 web 日志泄露；删除 `GameEngine._has_api_key`（恒为 True 的不可达守卫）及其调用点；`WebGameService` 新增 `_prune_idle_runners(ttl=1800)`，按空闲超时淘汰 `runners` 字典，修复内存泄漏。
- **P1 减重**：`Settings` 改用 `pydantic-settings.BaseSettings`（`env_prefix="AGNES_"`）；删除死代码 `config/default.yaml`；合并 `dedupe_strings`、`_is_production_mode`→`is_production_mode`，删除未用的 `_parse_delta_int`。`logging_setup.py` 因 P0 被激活，保留。
- **P2 架构（方案 C）**：删除 `web/backend/database_sqlite.py`，`create_database()` 工厂恒返回 `PostgresWebDatabase` 并要求 `DATABASE_URL`；`web/backend/app.py` 改用模块 `__getattr__` 惰性构造 `app`，import 不再连库；删除 Flow 死代码 `_handle_local_story_action`、`auth.generate_invite_code`、`death_rewards.consume_legacy_bonus`（单数版）。净减约 900 行。
- **P2 测试迁移**：`tests/unit/game/test_game_turns_storage.py` 重写到 PostgreSQL；新增 `tests/web/conftest.py` 提供函数级 TRUNCATE 隔离夹具；未设置 `TEST_DATABASE_URL` 时 DB 往返测试自动跳过。
- **P3**：`Settings._mask` 复用 `agens_novel.utils.secrets.mask`（去重）。

### Changed — 部署/配置同步 PG-only

- `Dockerfile` 移除已失效的 `AGENS_WEB_DB=...sqlite3` 环境变量（工厂仅读 `DATABASE_URL`）。
- `deploy/docker-entrypoint.sh` 不再按 `DATABASE_BACKEND` 门控，`alembic upgrade head` 无条件执行（PostgreSQL 为唯一后端）。
- `.env.example` 移除 `AGENS_WEB_DB` 注释，`DATABASE_URL` 成为唯一数据库配置。
- `README.md`、`AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/PROJECT_AUDIT.md` 架构描述同步为 PostgreSQL-only。

### Notes — 故意未改（待用户确认）

- `web/backend/security.py` 的 `is_production_mode()` 读 `AGENS_ENV`（不再读 `DATABASE_BACKEND`）。第二轮已把 `database_postgres.py` 的 DDL 守卫统一到同一变量，生产态信号单一化（见下文「代码审计第二轮」）。
- `WebGameService` 与 `WebRunner` 未合并：审计「前者几乎全委托后者」的前提不成立（`WebRunner` 自带引擎回调、死亡奖励落库、响应序列化等大量逻辑），合并会产生 God Class。
- `llm/client.py` 的 `mask_key` 未与 `utils.secrets.mask` 统一（两者掩码长度策略不同）。

### Changed — 代码审计第二轮（死依赖 / 死代码 / AGENS_ENV 统一）

- **安全修复 — 生产态变量统一**：`database_postgres.py` 的 DDL 守卫原读 `APP_ENV`，与 `security.is_production_mode()` 读取的 `AGENS_ENV` 不同步；`deploy/production.env.example` 仅设 `AGENS_ENV=production`，导致生产下 DDL 守卫被绕过。统一为 `AGENS_ENV`（同步迁移 docstring 与 `docs/ARCHITECTURE.md`、`docs/PROJECT_AUDIT.md`）。
- **死依赖移除**：`langgraph`、`langchain-core`、`langchain-openai` 全库零 import（LLM 走原生 `httpx` + 自有 `Message` 类型），从 `pyproject.toml` 移除；`Dockerfile` 改为单一依赖源 `pip install -e .`，删除 `requirements.txt`（双源已导致 2026-06-24 部署失败）。
- **死代码清理**：删除零调用函数 `luck_from_attributes`、`parse_delta_int`、`get_realm_year_range`、`checkpoint_path`、`render._bar`、DB 接口方法 `get_invite_code`；删除未用常量 `WORLD_BUILDER_SYSTEM`；删除 `world_generator` 未用 import（`DEFAULT_ATTRIBUTES`、`json`）。
- **`state/` 包移除**：`state/reducers.py`（LangGraph `Annotated` reducer）与 `state/game_schema.py`（TypedDict）仅被自身测试引用、生产零引用、reducer 运行时不生效；连同 `tests/unit/state/` 一并删除。
- **去重**：新增 `agents/common.py`（`load_agent_settings` + `normalize_choices`），消除 narrator/world_builder/judge 三处 `load_settings` 与 narrator/world_builder 两处 `_normalize_choices` 的逐行重复。
- **死参数移除**：`create_app(db_path)` 与 `create_database(db_path)` 的 vestigial 参数（Option C 后被忽略）移除；`tests/web/test_web_api.py` 调用点同步，并迁移 2 个 SQLite 时代遗留的 DB 测试到 SQLAlchemy `text()`。

### Notes — 故意未改（第二轮）

- `llm/client.py` 仍为 async 接口包同步 `httpx`（原审计「不处理项」），未改；其自带 `_parse_sse_lines` 与 `sse.py` 的 `iter_sse_events` 各一套 SSE 解析，因涉及 client.py 暂未去重。
- `death_rewards.py`（352 行，P4）保留：已接入 `service.py` 终局流程（`categorize_death`→`evaluate_achievements`→`compute_rewards`→`build_run_summary`），非死代码。
- 代码与文档中 "LangGraph" 术语保留：描述 agent 节点 state 的 msgpack 序列化约束（`SequentialAgentGraph`），仅移除未用的 `langgraph` 包依赖与 `state/` reducer，不 purge 术语。

## 2026-06-24

### Added

- Homepage QQ card now uses the user-provided `xian-game-icon-256.png` asset under `web/frontend-react/public/assets`.
- `WebRunner.record()` includes the current character age in readable events so the chronicle timeline can infer display years from gameplay state.
- Frontend contract checks for the image-based QQ icon, the fate summary-card structure, and chronicle year-prefix cleanup.
- Project-status notes in `docs/PROJECT_AUDIT.md`, `docs/UI_REFACTOR_PLAN.md`, and `docs/INDEX.md` for the current UI batch, validation results, and browser-validation boundary.
- `docs/NEXT_GOVERNANCE_BACKLOG.md` as the active backlog separating production-approved work, local complexity reduction, cleanup, and validation rules.
- Production v5 local package manifest for commit `11ae5e9699277ce08b42a9331932354895922149`, archive `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.zip`, and SHA256 `526b8b6cbbc1abd60b1a03b1d73369778abf8c723d439579526532d9744017ad`.

### Changed

- Character creation fate groups use the approved plan A summary-card collapse design: selected item pill, color dot, chevron, one open group at a time, and internally scrolling option lists.
- Game chronicle rendering treats the card title year as authoritative and strips leading `玄历/玄元历...年` prefixes from narrative text.
- Narrator prompt now tells the model not to start each event body with a chronicle year prefix.
- Browser validation guidance now prefers Chrome DevTools MCP or external Chrome because the Codex in-app browser is unstable on this machine.
- FastAPI session endpoints now share one service-error wrapper for `KeyError` / `PermissionError` / `ValueError`, preserving the existing 404 / 403 / 400 response behavior while removing repeated route boilerplate.
- SQLite and PostgreSQL catalog seeding, catalog-row JSON preparation, and player-progress summaries now share helpers in `web/backend/database_common.py`, reducing duplicate data-layer logic without changing schema or API behavior.
- Game chronicle year/text shaping moved from `GamePage.tsx` into pure helpers in `web/frontend-react/src/lib/chronicle.ts`, keeping the page focused on rendering and interaction wiring.
- Chronicle year display now uses the strongest positive year candidate from event year, turn index, inferred turn, and age-year. This prevents local fallback events with unchanged character age from leaving turn 1 displayed as `玄元历 1 年`.
- Randomized character attributes now render as read-only meters instead of disabled manual sliders, so values above the manual cap remain visible and accessible without mismatched slider semantics.
- `WebGameService.choose()` and `WebGameService.act()` now share the same private turn-advance helper, keeping turn execution, settled-turn persistence, session persistence, and response shaping in one path.
- Alpha review and game-mode spec now align the production gate with Alembic head `20260622_0004` and the completed local Chrome/account/live-model validation coverage.
- `docs/INDEX.md` now routes structure cleanup and technical-debt work through the active governance backlog before deeper audit docs.
- Docker image hardening now strips CRLF from the copied `agens-web` entrypoint, and `.gitattributes` forces shell scripts and the Dockerfile to LF line endings.
- `GameEngine.attempt_breakthrough()` now delegates the breakthrough-narrator
  invocation to `_run_breakthrough_narrator()`. That helper only owns the raw
  exception branch (try/except + `_set_choices` fallback with
  `source="breakthrough_narrator_exception"`); the post-call `llm_error` branch
  with `source="breakthrough_narrator_error"` is still inlined in
  `attempt_breakthrough()`.
- `WebGameService` keeps `_require_non_guest_runner(action=...)`, which
  consolidates the `is_guest_user_id → PermissionError("访客…")` guard used by
  `save` and `load`. The intermediate `_with_runner()` alias was reverted in
  the same pass because it had no extra semantics over `_runner()`.
- `web/backend/database_common.py` adds `encode_game_turn_json()` to keep the
  `choices` / `state_delta` / `state_after` JSON encoding in lockstep between
  the SQLite and PostgreSQL `record_game_turn` writers; SQL, schema and
  column names are unchanged.
- `CharacterCreatePage` collapses the three repeated `<CatalogGroup>` blocks
  into a small `fateGroups` data-driven loop. `character-create.css` merges
  the duplicate `.character-page` rule.

### Verification

- `python -m compileall -q src tests web scripts migrations` clean.
- `pytest -q tests\web` -> 49 passed, 1 skipped (`TEST_DATABASE_URL` not configured).
- `pytest -q` -> 425 passed, 1 skipped.
- `pytest -q tests/unit/engine/test_game_engine_turn.py tests/unit/engine/test_game_engine_setup.py tests/unit/engine/test_game_engine_state.py tests/unit/game/test_database_common.py` -> 56 passed.
- `npm run build` passed; frontend contract test `tests\web\test_frontend_contract.py` passed 16 tests.
- `pytest -q tests\web\test_web_api.py::test_web_api_minimum_game_flow tests\web\test_web_api.py::test_session_routes_map_service_errors` -> 9 passed; the minimum flow now covers both `/choice` and `/action` turn persistence.
- Documentation consistency check: `rg` now routes production acceptance to Alembic head `20260622_0004`, while local Chrome/account/live-model coverage is separated from still-open production account/model smoke.
- Chrome desktop and 375px mobile smoke passed for guest start, fallback continuation, A/B/C/D visibility, and `玄元历 2 年 · 回合 1` after the first local fallback turn.
- Chrome 375px random-character smoke confirmed all six randomized attributes expose meters whose `aria-valuenow` matches the visible value.
- Chrome desktop local account smoke passed with a temporary SQLite database and local-only invite: register/login, account new game, save to `slot_1`, load from `slot_1`, and `/api/saves` returning the saved row all completed with HTTP 200.
- Chrome 2560x1440 emulation smoke passed for home, character creation, and initial game view. No horizontal overflow was detected; the creation panels, start button, game grid, status rail, story panel, and A/B/C/D buttons stayed within the viewport.
- Chrome local live-model smoke passed with a temporary SQLite database and non-secret environment-presence check only: guest start plus choice A returned `/api/sessions/{id}/choice` HTTP 200, `fallback_prompt.active=false`, turn count 1, refreshed narrative, and refreshed A/B/C/D choices.
- Server read-only validation confirmed public health/catalog and container health, but production Alembic is still `20260621_0002` and v5 tables `game_runs`, `game_turns`, `player_progress` are missing.
- Production package content check found no `.env`, `production.env`, `node_modules/`, `.venv/`, cache directories, or local frontend `dist` in the archive; the package was created from tracked `HEAD` files with `git archive`.
- Server deployment preflight thread `019ee2ee-823e-7441-bdaa-881782da7949` confirmed package hash visibility, public health/catalog, internal origin health, healthy `agens-web` container, and staging/backup path candidates; it did not deploy, back up, migrate, restart, or read/print secrets.
- Approved production v5 deployment attempt stopped before Alembic/restart: server package upload and SHA256 verification passed, PostgreSQL backup `/srv/jiayp/backups/postgres/postgres-20260624-180554.sql.gz` and app backup `/srv/jiayp/backups/agens-web/agens-web-app-20260624-180650.tar.gz` were created, `/srv/jiayp/apps/agens-web` was replaced, then Docker build failed resolving `langchain-core>=0.3.0`. Existing running container stayed healthy, public health/catalog stayed OK, and production Alembic remained `20260621_0002`.
- Read-only server diagnosis found `requirements.txt` still contains `langchain-core>=0.3.0`, Docker runtime is `python:3.12-slim`, and a temporary `python:3.12-slim` container can see `langchain-core` versions including `0.3.0`; the build stop is most likely a transient or build-context-specific pip index/network issue.
- Prepared the build-only retry prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.server-build-only-prompt.md`, scoped to image build only and explicitly excluding Alembic, restart/recreate, rollback, and public exposure changes until separate approval.
- Build-only retry passed using host-network fallback and produced image `sha256:f2d2b86e3de0c9aff5131ed238c84eb435cb0d31983e5e4629b8b75add4d6c15`; no Alembic, restart/recreate, rollback, or public exposure change was performed in that retry.
- Approved migration/restart batch upgraded production Alembic to `20260622_0004` and confirmed `game_runs`, `game_turns`, and `player_progress`, then stopped after the recreated `agens-web` container failed with exit 127 due CRLF in the image entrypoint (`env: 'sh\r': No such file or directory`). Public health was HTTP 502 at that stop point; the later approved entrypoint hotfix restored service.
- Prepared the entrypoint CRLF hotfix prompt `D:\chat\outputs\packages\agens-web\agens-web-11ae5e9-20260624-173644.entrypoint-crlf-hotfix-prompt.md`, scoped to LF normalization, build-only, only `agens-web` recreation, and post-deploy verification.
- Prepared entrypoint CRLF hotfix package `D:\chat\outputs\packages\agens-web\agens-web-entrypoint-crlf-hotfix-20260624-185815.zip` with SHA256 `261ecef7fbeac0928b076802e4cd458607c651ae15153f9ea700a01afd8ce1f4`; contents are limited to `.gitattributes`, `Dockerfile`, and `deploy/docker-entrypoint.sh`, and the packaged entrypoint is LF-only.
- Server read-only hotfix preflight confirmed production is still in the same failed state: container `Restarting (127)`, public health HTTP 502, origin connect failed, Alembic `20260622_0004`, v5 tables present, deployed entrypoint `crlf_count=10`, deployed Dockerfile hardening missing, backups present, and the prepared hotfix package visible with matching SHA256.
- Approved entrypoint CRLF hotfix passed: server changed only `.gitattributes`, `Dockerfile`, and `deploy/docker-entrypoint.sh`, backed those files up at `/srv/jiayp/backups/agens-web/entrypoint-crlf-hotfix-20260624-185815/`, built image `sha256:445367f496bf3b1acb8b091442f775b9c74240251cc19efdfab2d45562dbc791`, recreated only `agens-web`, and restored healthy origin/public health.
- Production smoke after the hotfix confirmed Alembic `20260622_0004`, `game_runs` / `game_turns` / `player_progress`, public catalog talents count 10, log sensitive-marker count 0, guest start HTTP 200, and guest one-turn HTTP 200 with four options.
- Production v5 is only partially accepted: account registration/login/save/load still needs a safe non-secret test account path, and live-model success was not accepted because the production guest smoke returned `fallback_prompt_active=true`.

## 2026-06-24 Local complexity governance (P1)

- This sub-section records a local-only governance pass. It does **not**
  accept any production action; production acceptance still requires the
  Codex / server thread batch described in
  `docs/PRODUCTION_V5_MIGRATION_CHECKLIST.md`.

### Added

- `GameEngine._run_breakthrough_narrator()` private helper that owns the
  breakthrough-narrator `run_turn_sync` call and its raw exception fallback
  (`source="breakthrough_narrator_exception"` + `_set_choices`). The post-call
  `llm_error` branch (`source="breakthrough_narrator_error"`) is still inlined
  inside `attempt_breakthrough()` and is the next P1 candidate.
- `WebGameService._require_non_guest_runner(action=...)` private helper that
  consolidates the `is_guest_user_id → PermissionError("访客…")` guard used
  by `save` and `load`. The original `_with_runner()` thin alias was removed
  in the same pass because it added no semantics over `_runner()`.
- `web/backend/database_common.encode_game_turn_json()` central helper used
  by both `database_sqlite.record_game_turn()` and
  `database_postgres.record_game_turn()` for the
  `choices` / `state_delta` / `state_after` JSON encoding step.

### Changed

- `GameEngine.attempt_breakthrough()` now invokes
  `_run_breakthrough_narrator()` instead of inlining the
  `run_turn_sync` + try/except branch. The `_set_choices` fallback emitted
  from that helper still uses `source="breakthrough_narrator_exception"`.
  The follow-up `if result.get("llm_error")` check, the
  `突破叙事失败: <error>` payload and the `source="breakthrough_narrator_error"`
  fallback remain inline inside `attempt_breakthrough()`.
- `WebGameService.save()` and `WebGameService.load()` now resolve runners
  through `_require_non_guest_runner(action=...)`, which centralises the
  `is_guest_user_id → PermissionError("访客…")` raise. The other call sites
  (`get_session`, `start_session`, `choose`, `act`, `end_session`,
  `death_summary`) keep the direct `self._runner(session_id, user_id=user_id)`
  call they used before; the interim `_with_runner()` alias was removed in
  the same pass because it had no extra logic.
- `database_sqlite.record_game_turn()` and
  `database_postgres.record_game_turn()` now call
  `encode_game_turn_json()` so the JSON encoding lives in one helper.
- `web/frontend-react/src/pages/CharacterCreatePage.tsx` declares a
  `fateGroups` config array and renders the three `<CatalogGroup>` items
  via a `.map()`; the per-group `selectedName` / `onSelect` / open-state
  wiring is unchanged.
- `web/frontend-react/src/styles/character-create.css` merges the duplicate
  `.character-page` rule into a single block (no visual change).

### Verification

- `python -m compileall -q src tests web scripts migrations` clean.
- `pytest -q tests\web` -> 49 passed, 1 skipped (`TEST_DATABASE_URL` not configured).
- `pytest -q` -> 425 passed, 1 skipped.
- `pytest -q tests/unit/engine/test_game_engine_turn.py tests/unit/engine/test_game_engine_setup.py tests/unit/engine/test_game_engine_state.py tests/unit/game/test_database_common.py` -> 56 passed.
- `cd web\frontend-react; npm.cmd run build` -> 1602 modules, 24.34 kB CSS, 190.37 kB JS.
- No server, deploy, SSH, production account, production live model, or
  browser/Playwright validation was performed in this pass.

### Known deferred items (still on the backlog)

- Production account flow verification on a safe non-secret test account.
- Production live-model success verification (the production guest smoke
  still returned `fallback_prompt_active=true`).
- Further `GameEngine` decomposition beyond the breakthrough-narrator
  slice; the next candidates are the `narrator_exception` / `narrator_error`
  paths in `handle_action` and the `world_builder` paths in
  `new_game` / `_generate_profile_opening`.
- React style file split is still a P2 candidate; the current pass only
  collapsed the duplicate `.character-page` rule.

## 2026-06-23

### Added

- `rarityToColor` / `colorLabel` helpers in `web/frontend-react/src/lib/util.ts` map legacy/internal rarity or grade strings into the unified 6-color palette (白/绿/蓝/紫/橙/红).
- CSS classes `.rarity-white`, `.rarity-green`, `.rarity-blue`, `.rarity-orange` in `styles.css`, alongside the existing `.rarity-purple` and `.rarity-red`.
- Contract-test assertions in `tests/web/test_frontend_contract.py` covering the homepage eyebrow removal, the short brand label `jiayp`, the 6 palette colors, the lifespan `remaining/cap` display, and the front-end reading `character.remaining_lifespan`.
- Project docs `docs/ARCHITECTURE.md` and `docs/USER_TUTORIAL.md` registered in `docs/INDEX.md`.
- UI background generation prompts in `docs/UI_REFACTOR_PLAN.md` for the homepage and character-creation screens.
- Contract checks for the homepage `仙` QQ mark, removal of the title red dot, centered homepage buttons, collapsible catalog groups, and the age-based `凡人长寿` rule.

### Changed

- Homepage (`HomePage.tsx`) drops the eyebrow line `WEB · 文字修仙模拟器` and the four-button descriptive paragraph; the brand link in `main.tsx` shortens to `jiayp` (the underlying URL `https://www.jiayp2917.xyz/` is preserved).
- `styles.css` removes the `.brand::after` jade dot, trims `.home` / `.home-shell` / `.home-preview` / `.hero` spacing so the page fits in a 1080p viewport.
- Character-creation `<option>` labels now render as `${name} · ${rarityToColor}`; the same colored dot is drawn on the host `<label>` because native `<option>` cannot host CSS consistently across browsers.
- Game-page choices are tighter: `.choice-list button` min-height 76 → 60 px, A/B/C/D badge 32 → 28 px; mobile breakpoint 58 → 56 px.
- `GamePage` reads `character.remaining_lifespan` first (fallback `lifespan - age`, clamped by `Math.min`); the summary now shows `${remainingLifespan}/${lifespanMax} 年`, matching `StatLine`.
- Source comments and docstrings in `death_rewards.py`, `game_engine.py`, `game_session.py`, and `game/__init__.py` no longer reference the removed combat / persistence modules.
- Homepage title stays on one line, the title red dot is removed, entry text is centered independently of the left icon, and the QQ badge now displays `仙`.
- Character-creation catalog groups are collapsible with internal scrolling; selected markers moved to the start of each row and the high-contrast rarity hint pills were replaced with plain helper text.
- `凡人长寿` now requires actual character age `>= 80` instead of using the lifespan cap; `/api/sessions/{id}/death_summary` prefers a live session recomputation before falling back to persisted rows.
- `README.md` now links to `docs/UI_REFACTOR_PLAN.md` instead of the removed `docs/WEB_ITERATION_PLAN.md`.

### Removed

- `src/agens_novel/game/combat.py` remnants in git history plus the dead `config/prompts/system/combat_narrator.md`.
- Empty `src/agens_novel/persistence/` shell and its leftover `__pycache__/`.
- `docs/WEB_ITERATION_PLAN.md` (superseded by `RUNTIME_FLOW.md` and `PROJECT_AUDIT.md`).
- Android APK skill `.agents/skills/build-apk/` (out of scope for the Web-only project).
- One-off Playwright smoke scripts under `web/frontend-react/.tmp/`.
- Redundant `.venv311/` Python 3.14 virtual environment alongside the active `.venv/`.
- Orphaned `__pycache__/*.pyc` files whose `.py` source had already been removed.
- Local `runtime/uvicorn-local.{err,out}.log` files.

### Verification

- `python -m compileall -q src tests web` clean.
- `pytest -q` → 466 passed, 1 skipped (no regressions).
- `npm run build` → 1590 modules, 15.18 kB CSS, 179.71 kB JS.

## 2026-06-22

### Added

- Alembic `20260622_0003` for game-mode v5 `game_runs`, `game_turns`, and `player_progress`.
- React public assets under `web/frontend-react/public/assets`, including BGM.
- Web service writes settled turns and terminal run progress for rarity unlocks.

### Changed

- React is the only product frontend entrypoint; old `web/frontend` fallback was removed.
- Docs now describe the current runtime as game-mode v5 Alpha with A/B/C/D fixed semantics.
- Frontend contract tests now target the React entrypoint and public assets.

## 2026-06-21

### Added

- PostgreSQL Alembic schema coverage for catalog tables and death reward tables.
- Production safety gates for allowed origins, OpenAPI hiding, and trusted host checks.
- React turn-action busy guards for A/B/C choices, fallback actions, and D input.
- PostgreSQL smoke path that runs only when `TEST_DATABASE_URL` is configured.
- Archived the game-mode planning draft under `docs/archive/`.
- Alpha review evidence and lessons in `docs/ALPHA_REVIEW_AND_LESSONS.md`.

### Changed

- `docs/INDEX.md` now separates current Alpha runtime docs from future game-mode v5 specs.
- `docs/PROJECT_AUDIT.md` records the React-first entrypoint, legacy frontend retirement, and PG/Alembic authority.
- `docs/ALPHA_REVIEW_AND_LESSONS.md` now records current conclusion, verification evidence, success lessons, failure lessons, residual risks, and follow-up execution rules.
- `/api/invites` now uses a typed request schema instead of ad hoc dict parsing.

## 2026-06-18

### Added

- FastAPI Web backend under `web/backend`.
- Static browser UI under `web/frontend`.
- SQLite users, sessions, saves, chat history snapshots, and masked model settings.
- Web API tests and frontend contract tests under `tests/web`.
- Web-only documentation entry points in `README.md`, `AGENTS.md`, `CLAUDE.md`, and `docs/`.

### Changed

- `master` is now the Web-only mainline.
- Root `main.py` and `Makefile` run the FastAPI app.
- Validation is now core engine tests, Web API tests, and browser UI checks.
- Model configuration is read or updated through the backend and returned only as masked state.

### Removed

- Mobile product source tree and packaging configuration.
- Mobile UI contract tests and mobile startup tests.
- Device-validation and packaging documentation from the Web project.
- Standalone BGM adapter layer that only served the old product path.
