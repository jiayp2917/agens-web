> Archive note: historical Claude Code follow-up list from 2026-06-20.
> Some items are already complete or superseded by the React-first Alpha path. Do not use this file as current project status.

# Claude Code 可做遗留项 — agens-web

最后更新: 2026-06-20
项目状态: Web-only 引导模式已上线；3 前端文件 + FastAPI + SQLite；4 个后端 API 测试 + 3 个前端契约测试；尚未具备真实浏览器自动化测试。

> 本表只列 Claude Code 工具范围内可做的事。GameEngine / Narrator / Judge / Agent 业务逻辑、Playwright 安装、移动端 375 重构、生产部署均不在内。

---

## P0 — 必修

### F-001: 兜底横幅的「继续本局」按钮目前只是 `notify`，无实际行为
- 文件: `web/frontend/app.js` 内 `renderFallbackBanner` 的 `fallbackContinueButton` 监听器
- 改动: 改为调用 `api(\`/api/sessions/${state.session.session_id}/action\`, { method:"POST", body:{ action:"继续本局" } })` 走正常回合；或至少刷新 `state.session`（再 `renderSession`）让 UI 反映当前状态。
- 验证: 手动 / 模型失败路径下点"继续"应推进或刷新回合；纯前端契约测试追加 `assert "/action" 与 "继续本局" in js`。
- 估时: ~10 分钟

### F-002: 后端 `ModelSettingsRequest` 对 `provider / base_url / model / api_key` 无长度上限
- 文件: `web/backend/app.py`（`ModelSettingsRequest`）+ `tests/web/test_web_api.py`
- 改动: 给四个字段统一加 `Field(default="...", max_length=N)` 约束：`provider` 64、`base_url` 512、`model` 128、`api_key` 512；新增 `test_post_model_settings_rejects_oversized_field` 分别发超长字符串期望 422。
- 验证: `pytest tests/web -q`
- 估时: ~10 分钟

### F-003: 前端 `escapeAttr` 与 `escapeHtml` 的 XSS 防护目前无契约锁定
- 文件: `tests/web/test_frontend_contract.py`
- 改动: 新增 `test_frontend_escapes_xss_in_choice_text` 读取 `app.js` 里的 `renderChoices`，手工构造 `choices=["<img src=x onerror=alert(1)>"]`，模拟一次 `renderChoices`，断言 innerHTML 里出现 `&lt;img` 且不含 `alert(1)` 原始串。
- 验证: `pytest tests/web/test_frontend_contract.py -q`
- 估时: ~10 分钟

---

## P1 — 推荐

### F-101: `<dialog>` 缺少"Esc 自动关闭"的契约测试
- 文件: `tests/web/test_frontend_contract.py`
- 改动: 断言 `<dialog id="modal"` 在 HTML 中存在，且 `app.js` 中 `openModal` 用 `modal.showModal()`（浏览器原生支持 Esc 关闭）；加注释说明该行为来自浏览器。
- 验证: `pytest -q`
- 估时: ~5 分钟

### F-102: 主题切换按钮目前只有两处使用，缺少契约锁定
- 文件: `tests/web/test_frontend_contract.py`
- 改动: 新增 `test_frontend_theme_toggle_wired_to_both_buttons`，断言 `#themeToggle` 与 `#themeToggleInline` 都在 HTML 里，且 `app.js` 同时引用两者（`THEME_CYCLE`、`applyTheme`、`THEME_KEY="agens.theme"`）。
- 验证: `pytest -q`
- 估时: ~5 分钟

### F-103: 属性滑杆的键盘支持说明
- 文件: `web/frontend/app.js`（`#attributeInputs input[type='range']` 监听器，约 113 行）
- 改动: 在现有 `input` 监听后追加 `keydown` 监听：Home/End 跳到 0/100、PageUp/PageDown ±10；显式同步 `<output>` 并 `refreshCharacterPreview()`；浏览器原生已支持 ArrowLeft/Right ±1，可写 JSDoc 注释说明。
- 验证: 手动 + 现有契约测试不破坏
- 估时: ~10 分钟

### F-104: `#narrativeLog` 缺少键盘滚动说明
- 文件: `web/frontend/index.html`（`#narrativeLog` 段落）
- 改动: 紧邻 `<div id="narrativeLog">` 加 `<p id="narrativeLogHint" class="sr-only">使用 Page Down 滚动。</p>`，并在 `narrativeLog` 上加 `aria-describedby="narrativeLogHint"`。
- 验证: 手动 / 契约测试断言 `narrativeLogHint` id 存在
- 估时: ~5 分钟

### F-105: 给现有色彩对比度写一份独立审计记录
- 文件: `docs/CONTRAST_AUDIT.md`（新文件）
- 改动: 用 Claude 内置知识列出每对前景/背景（`--color-primary #0e7c7b` on `#f5efe1`、深色模式 `#3aa39e` on `#15171a`、`--color-accent #b5453b` on `#f5efe1`），并给出 WCAG AA 大致通过/失败标注。无需运行 a11y 工具（无 axe-core）。
- 验证: 文档 review
- 估时: ~15 分钟

### F-106: 后端 `StaticFiles` 挂载的契约测试
- 文件: `tests/web/test_web_api.py`
- 改动: 新增 `test_static_serves_index_html` 通过 `TestClient` 访问 `/`，断言 `Content-Type` 含 `text/html` 且 body 含 `id="app"`；再加 `test_static_serves_png_asset` 断言 `/assets/ink_home_bg.png` 返回 `200` 且 `content-type` 以 `image/` 开头。
- 验证: `pytest tests/web/test_web_api.py -q`
- 估时: ~10 分钟

### F-107: ~~给 `web/backend/database.py` 的几个函数补返回类型注解~~（已无意义）
- 状态: 经核查，`web/backend/database.py` **已**含完整 type hints（`upsert_user`、`save_session`、`load_session` 等均带 `-> dict[str, Any]` / `-> dict[str, Any] | None` 注解），无需修改。
- 此条从清单中删除。

### F-108: 新建 `docs/API.md`，描述全部 `/api/*` endpoint 的请求/响应 schema
- 文件: `docs/API.md`（新文件）
- 改动: 从 `web/backend/app.py` 的 Pydantic 模型枚举所有路由、字段类型、默认值、错误码（404/400/422）。
- 验证: 文档 review
- 估时: ~20 分钟

### F-109: 给 `notify` 吐司加错误级 `aria-live="assertive"`
- 文件: `web/frontend/app.js`（`notify` 函数）
- 改动: 新增 `#toastError` 节点用于 error；`api()` 内的 `notify(detail)` 改为调用 `notifyError(detail)`。当前 `#toast` 全部是 `aria-live="polite"`，错误信息会被普通提示淹没。
- 验证: 契约测试断言两个 toast 节点 id 存在
- 估时: ~15 分钟

---

## P2 — 锦上添花

### F-201: 给 skip-link 的可见焦点态加测试断言
- 文件: `tests/web/test_frontend_contract.py`
- 改动: 断言 `.skip-link` 在 `styles.css` 中含 `:focus` 规则且 `transform: translateY(...)` 出现。
- 验证: `pytest -q`
- 估时: ~5 分钟

### F-202: 把主题切换的契约文档化
- 文件: `docs/THEME.md`（新文件）
- 改动: 解释三态（auto / light / dark）与系统 `prefers-color-scheme` 的关系、`localStorage.agens.theme` key、`aria-pressed` 语义、Win/Edge 字体回退栈。
- 验证: 文档 review
- 估时: ~10 分钟

### F-203: 新建 `docs/FRONTEND_ARCHITECTURE.md`
- 文件: `docs/FRONTEND_ARCHITECTURE.md`（新文件）
- 改动: 4 views 路由图、`state.user/session/theme/prevCharacter` 字段、`<dialog>` 生命周期、`setBusy` 全局锁定模型。
- 验证: 文档 review
- 估时: ~20 分钟

### F-204: 给 `escapeAttr` 写一行 JSDoc 注释
- 文件: `web/frontend/app.js`
- 改动: 在 `escapeAttr` 上方加 2 行注释，说明反引号转义用于模板字符串内（即使浏览器实际不会解析，但保留以防未来模板场景）。
- 验证: 无
- 估时: ~3 分钟

### F-205: 把 `EVENT_BADGES` 在测试中加契约锁定
- 文件: `tests/web/test_frontend_contract.py`
- 改动: 断言已知事件类型 `narrative / status / info / error / loading / stream / combat / character_created / model_failure / game_over / finale` 在 `app.js` 的 `EVENT_BADGES` 中都出现，防止误删 key。
- 验证: `pytest -q`
- 估时: ~5 分钟

### F-206: 给 `web/backend/__main__.py` 写一段模块 docstring
- 文件: `web/backend/__main__.py`
- 改动: 在文件顶部加 docstring：`python -m web.backend` 等价 `uvicorn web.backend.app:app --reload`，端口 8000。
- 验证: `pytest -q` + 文档 review
- 估时: ~3 分钟

### F-207: `docs/security.md` 引用 `test_model_settings_never_returns_raw_api_key`
- 文件: `docs/security.md`
- 改动: 该测试已存在于 `tests/web/test_web_api.py:181`。在 `docs/security.md` 的 Verify 一节加一条 `.\.venv\Scripts\python.exe -m pytest tests/web/test_web_api.py::test_model_settings_never_returns_raw_api_key -q`。
- 验证: 跑一遍
- 估时: ~3 分钟

### F-208: 在 `WEB_ITERATION_PLAN.md` 与 `PROJECT_AUDIT.md` 的"技术债队列"加一列「Claude Code 可做？」
- 文件: 两个 doc
- 改动: 表头加一列；6 行债务全部填"否 — 后端/引擎范围"作为单一说明，避免后续误派给 Claude Code。
- 验证: 文档 review
- 估时: ~5 分钟

---

## 已确认 Claude Code 可做范围

- 仅 `web/frontend/{index.html, styles.css, app.js}` 三个文件编辑。
- 仅在 `tests/web/` 新增 Python 测试（FastAPI `TestClient` + 文件契约测试）。
- 仅后端的小范围安全/卫生改进：`max_length` 校验、`type hints`、静态资源契约测试。
- 在 `docs/` 新增或修订 Markdown 文档（API、ADR、a11y/contrast audit、架构图）。
- 验证命令：`.\.venv\Scripts\python.exe -m compileall -q src tests web` 与 `.\.venv\Scripts\python.exe -m pytest -q`。

## 明确不可做

- 生成新背景 PNG（图像生成不在 Claude Code 工具范围）。
- 真实浏览器自动化（无 Playwright / Selenium / Puppeteer 安装，离线环境无法 `pip install` 浏览器二进制；见下节）。
- 移动端 375 重构（用户已确认延后）。
- 修改 GameEngine / Agent / Narrator / Judge 提示词或业务逻辑（CLAUDE.md 禁止项）。
- 跨端密钥同步、生产部署、PostgreSQL 迁移。

---

## 关于"真实页面 e2e 测试"

**结论：Claude Code 在当前环境无法做真实浏览器 e2e。**

证据：
1. `requirements*.txt` 只列 `pytest / pytest-asyncio / pytest-xdist / ruff / mypy / beautifulsoup4`；`pip list` 中无 `playwright / selenium / pyppeteer`。
2. 项目无 `package.json`，纯 Python 仓库，无 JS 端 Playwright。
3. 可用 MCP 服务器仅有 `codegraph`（代码智能），无任何浏览器 MCP（无 playwright-mcp / puppeteer-mcp）。
4. 现有 30+ 测试全部用 `pytest` fixtures 或 FastAPI `TestClient`，唯一的"前端测试"是 `tests/web/test_frontend_contract.py` 的纯字符串匹配。

**Claude Code 可以做的"近似 e2e"覆盖：**
- FastAPI `TestClient` HTTP e2e：完整链路 `login → /sessions → /start → /choice → /action → /save → /load`，校验状态码 + JSON schema。已有 `tests/web/test_web_api.py`；可继续扩展。
- 静态 HTML/CSS/JS 契约测试：断言关键 id、selector、token、字面量存在。
- `<dialog>` 等原生元素行为：依赖浏览器实现，Claude Code 不能断言，但可写契约注释说明依赖关系。

**Claude Code 不能做的：**
- 点击按钮 → 读取 DOM → 截图 → 检查像素颜色。
- 在 375 / 768 / 1280 视口宽度下测响应式布局。
- 跑 `npx playwright test` / `pytest-playwright`。
- 用 axe-core / pa11y / Lighthouse 等真 a11y 工具测对比度（只能静态推理）。

**若用户硬性要求真实浏览器 e2e，需要用户手动完成的事：**
```bash
.\.venv\Scripts\pip.exe install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```
之后 Claude Code 可以撰写 `tests/e2e_browser/test_play_page.py`，但不能安装浏览器二进制或跑有头浏览器。
