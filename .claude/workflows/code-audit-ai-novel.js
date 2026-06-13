export const meta = {
  name: 'code-audit-ai-novel',
  description: 'Exhaustive code quality, framework, and architecture audit of D:\\2917\\ai-novel',
  phases: [
    { title: 'Recon' },
    { title: 'Backend Deep Dive' },
    { title: 'AI / Pipeline' },
    { title: 'Frontend Deep Dive' },
    { title: 'Code Quality Audit' },
    { title: 'Adversarial Verify' },
    { title: 'Synthesis' },
  ],
}

phase('Recon')

const reconStructure = await agent(`Perform a structural recon of D:\\2917\\ai-novel. Use Glob and Bash to:

1. List the top-level directory tree to depth 3 (exclude node_modules, __pycache__, .git, dist, build, .venv, .pytest_cache, .next, runtime, frontend/node_modules).
2. Count source files by extension (.py, .ts, .tsx, .js, .jsx, .css, .md, .yaml, .yml, .json, .toml, .sh, .ps1, .sql, .html).
3. Identify the main source folders and their purpose (1 line each).
4. Locate the entry points: backend (main.py / app.py / asgi), frontend (main.tsx / App.tsx / index.html), scripts.
5. List all top-level README*.md, AGENTS.md, PRD.md, CONTRIBUTING.md, LICENSE files and a one-line summary of what each contains.
6. Identify any Dockerfile, docker-compose.*, .github/workflows/, Makefile, or CI configs.

Output a single JSON object. Do not write prose, return JSON only.`, {
  label: 'recon:structure',
  phase: 'Recon',
  schema: {
    type: 'object',
    properties: {
      tree: { type: 'string' },
      fileCounts: { type: 'object', additionalProperties: { type: 'integer' } },
      sourceFolders: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, purpose: { type: 'string' } } } },
      entryPoints: { type: 'object', additionalProperties: { type: 'string' } },
      topLevelDocs: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, summary: { type: 'string' } } } },
      devops: { type: 'array', items: { type: 'string' } },
    },
    required: ['tree', 'fileCounts', 'sourceFolders', 'entryPoints', 'topLevelDocs', 'devops'],
  },
})

const reconBackendDeps = await agent(`Read the following files in D:\\2917\\ai-novel and report their contents summarized:

1. backend/requirements.txt OR backend/pyproject.toml (whichever exists)
2. backend/requirements-dev.txt OR backend/requirements-test.txt (if exists)
3. backend/alembic.ini (if exists)
4. backend/app/core/config.py (settings definitions)
5. config/*.yaml OR backend/config/*.yaml (model registry, prompts, anything YAML)
6. backend/app/main.py (FastAPI app bootstrap)
7. Any pytest.ini, pyproject.toml [tool.pytest] section
8. Any .env.example or config.example

For each, extract: dependencies with version pins (just name + version), settings keys, route mount list, middleware. Return JSON.`, {
  label: 'recon:backend-deps',
  phase: 'Recon',
  schema: {
    type: 'object',
    properties: {
      pythonDeps: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, version: { type: 'string' }, group: { type: 'string' } } } },
      settings: { type: 'array', items: { type: 'object', properties: { key: { type: 'string' }, type: { type: 'string' }, default: { type: 'string' } } } },
      routesMounted: { type: 'array', items: { type: 'string' } },
      middlewares: { type: 'array', items: { type: 'string' } },
      yamlConfigs: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, summary: { type: 'string' } } } },
      testConfig: { type: 'string' },
    },
    required: ['pythonDeps', 'settings', 'routesMounted', 'middlewares', 'yamlConfigs', 'testConfig'],
  },
})

const reconFrontendDeps = await agent(`Read and report on the frontend stack of D:\\2917\\ai-novel. Specifically:

1. frontend/package.json (dependencies, devDependencies, scripts)
2. frontend/tsconfig.json
3. frontend/vite.config.* OR frontend/webpack.config.* OR next.config.* (whichever exists)
4. frontend/index.html
5. frontend/src/main.tsx or frontend/src/index.tsx (whichever exists)
6. Any .eslintrc.* , .prettierrc.*, frontend/jest.config.*, frontend/vitest.config.*
7. frontend/playwright.config.* or frontend/e2e/* config

Extract: dependency name + version, tsconfig compilerOptions.strict, scripts list, build tool + version, test framework + version. Return JSON.`, {
  label: 'recon:frontend-deps',
  phase: 'Recon',
  schema: {
    type: 'object',
    properties: {
      deps: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, version: { type: 'string' }, group: { type: 'string' } } } },
      tsConfig: { type: 'object', additionalProperties: true },
      scripts: { type: 'array', items: { type: 'string' } },
      buildTool: { type: 'string' },
      testFrameworks: { type: 'array', items: { type: 'string' } },
      lintFormat: { type: 'array', items: { type: 'string' } },
    },
    required: ['deps', 'tsConfig', 'scripts', 'buildTool', 'testFrameworks', 'lintFormat'],
  },
})

const reconTests = await agent(`Survey the test setup of D:\\2917\\ai-novel:

1. Find all test_*.py and *_test.py under backend/. List each file with line count (use Bash: wc -l).
2. Find all *.test.ts, *.test.tsx, *.spec.ts, *.spec.tsx under frontend/. List each file with line count.
3. Find any e2e/, tests/e2e/, or integration test directories and list files.
4. Look for fixtures/, conftest.py files and list them.
5. Read the contents of any pytest.ini, pyproject.toml [tool.pytest], frontend/vitest.config.*, frontend/playwright.config.* — return their full text.
6. List what appears to be covered: routers, services, repositories, pipeline, model_client, budget, state_machine, etc. Note modules under backend/app that have NO test file (potential gaps).
7. Note: any coverage.py config, coverage threshold, codecov badge in README.

Return JSON.`, {
  label: 'recon:tests',
  phase: 'Recon',
  schema: {
    type: 'object',
    properties: {
      backendTests: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, lines: { type: 'integer' } } } },
      frontendTests: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, lines: { type: 'integer' } } } },
      e2eTests: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, lines: { type: 'integer' } } } },
      conftestFiles: { type: 'array', items: { type: 'string' } },
      testConfigs: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, content: { type: 'string' } } } },
      backendTestGaps: { type: 'array', items: { type: 'string' } },
      frontendTestGaps: { type: 'array', items: { type: 'string' } },
    },
    required: ['backendTests', 'frontendTests', 'e2eTests', 'conftestFiles', 'testConfigs', 'backendTestGaps', 'frontendTestGaps'],
  },
})

log('Recon complete. Beginning parallel deep dives.')

const backendArch = await agent(`You are auditing the BACKEND architecture of D:\\2917\\ai-novel. Use Read/Grep/Glob (do NOT modify files).

Investigate these layers in order, and for each produce concrete findings with file paths and line numbers:

A. Web layer (FastAPI):
   - backend/app/main.py — app construction, CORS, middleware order, exception handlers
   - backend/app/api/ or backend/app/routers/ — list every router file, count endpoints, identify auth dependencies, look for missing auth on admin/internal routes

B. Service layer:
   - backend/app/services/ — list all service files with line counts
   - Identify any "God Class" service files (>500 lines) — for each, give top 5 most complex methods
   - For each service, note: how does it get DB session? (Depends injection? global?), how does it call other services?

C. Data layer:
   - backend/app/db/ — list model files
   - backend/app/db/models.py — count models, list them, identify Mapped[] typed columns, check for relationships
   - backend/app/repositories.py — identify the Repository pattern: is it generic? typed?
   - Alembic migrations: list versions, note if any are destructive
   - Identify N+1 query risks: look for lazy-loaded relationships accessed in loops

D. Core / utils:
   - backend/app/core/ — list files
   - Look for utility modules that raise HTTPException directly (boundary leak)
   - Look for: config.py (pydantic-settings), file_utils.py (path safety), security.py (key storage)

E. Error handling:
   - How are exceptions propagated from service to router?
   - Are there domain-specific exception classes? (e.g. BudgetExceeded, PipelineError)
   - Is string-matching used to classify errors anywhere? (smell)

F. Configuration and secrets:
   - How are API keys stored? (env / DPAPI / file?)
   - Are secrets committed to repo? (search for sk-, ghp_, hardcoded keys)

For each finding, give: severity (high/med/low), file:line, what it is, recommendation. Return JSON.`, {
  label: 'backend:arch',
  phase: 'Backend Deep Dive',
  schema: {
    type: 'object',
    properties: {
      webLayer: { type: 'object', properties: { routerFiles: { type: 'array', items: { type: 'string' } }, endpointCount: { type: 'integer' }, middlewareOrder: { type: 'array', items: { type: 'string' } }, missingAuthRoutes: { type: 'array', items: { type: 'string' } } } },
      serviceLayer: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, lines: { type: 'integer' }, topMethods: { type: 'array', items: { type: 'string' } } } } },
      dataLayer: { type: 'object', properties: { modelFiles: { type: 'array', items: { type: 'string' } }, modelCount: { type: 'integer' }, models: { type: 'array', items: { type: 'string' } }, migrations: { type: 'array', items: { type: 'string' } }, nPlus1Risks: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } } } },
      coreUtils: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, purpose: { type: 'string' }, boundaryLeaks: { type: 'array', items: { type: 'string' } } } } },
      errorHandling: { type: 'object', properties: { domainExceptions: { type: 'array', items: { type: 'string' } }, stringMatchedErrors: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } } } },
      secrets: { type: 'object', properties: { storageApproach: { type: 'string' }, leakedKeys: { type: 'array', items: { type: 'string' } } } },
      findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string' }, area: { type: 'string' }, desc: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, recommendation: { type: 'string' } } } },
    },
    required: ['webLayer', 'serviceLayer', 'dataLayer', 'coreUtils', 'errorHandling', 'secrets', 'findings'],
  },
})

const aiPipeline = await agent(`You are auditing the AI / LLM integration and pipeline of D:\\2917\\ai-novel. Use Read/Grep/Glob (no modifications).

Investigate:

A. Model client (backend/app/services/model_client.py and related):
   - Read the entire file(s). List:
     - Supported providers and how endpoints are configured
     - Retry policy (exponential backoff? max attempts? jitter?)
     - Timeout handling
     - Prompt caching mechanism (where is cache key derived? SHA256? how is it invalidated?)
     - JSON mode / structured output handling
     - "thinking mode" support if any
     - How streaming is handled (if at all)
     - Token accounting — input/output, per-call cost calculation
   - Find any obvious bugs: race conditions on cache, leaked exceptions, swallowed errors, missing timeouts

B. Model router (backend/app/services/model_router.py and YAML):
   - List all 9+ roles (writer, reviewer, fixer, etc.) with their fallback chain
   - Note if priority ordering is per-role or global
   - Find any place where the router is bypassed and a provider is hardcoded

C. Budget / concurrency:
   - backend/app/services/budget.py — read fully
   - Identify: is guard process-level (threading.Lock) or cross-process? (RDB / file lock?)
   - Concurrency limiter — semaphore? where?
   - Note any type-safety issues (e.g. "route: Any")

D. Pipeline (backend/app/services/pipeline/):
   - List all pipeline files
   - Read state_machine.py — extract ALLOWED_TRANSITIONS dict exactly
   - Read runs.py if it exists — note line count, top methods
   - Read planner.py, writer.py, reviewer.py, fixer.py, summarizer.py — 2-line summary of each
   - Identify the flow: Planner -> Writer -> Reviewer -> Fixer -> Summarizer (or similar)
   - Find any "RuntimeError raised to control flow" pattern

E. Audit trail:
   - ModelCall table — what does it capture? (provider, model, prompt hash, tokens, cost, latency, status)
   - Is the audit thread-safe? Atomic?

F. Prompt management:
   - Where are prompts stored? (inline strings / files / DB?)
   - Any prompt versioning?

Return JSON with: file paths, line refs, findings (severity + recommendation), and a 1-paragraph assessment of how professional the AI integration is (1-5 scale with reasoning).`, {
  label: 'ai:pipeline',
  phase: 'AI / Pipeline',
  schema: {
    type: 'object',
    properties: {
      modelClient: { type: 'object', properties: { providers: { type: 'array', items: { type: 'string' } }, retryPolicy: { type: 'string' }, promptCache: { type: 'string' }, jsonMode: { type: 'boolean' }, thinkingMode: { type: 'boolean' }, streaming: { type: 'string' }, tokenAccounting: { type: 'string' }, bugs: { type: 'array', items: { type: 'string' } } } },
      modelRouter: { type: 'object', properties: { roles: { type: 'array', items: { type: 'object', properties: { role: { type: 'string' }, providers: { type: 'array', items: { type: 'string' } } } } }, bypasses: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } } } },
      budget: { type: 'object', properties: { guardMechanism: { type: 'string' }, processSafe: { type: 'boolean' }, concurrencyLimiter: { type: 'string' }, typeIssues: { type: 'array', items: { type: 'string' } } } },
      pipeline: { type: 'object', properties: { files: { type: 'array', items: { type: 'string' } }, stateCount: { type: 'integer' }, allowedTransitions: { type: 'array', items: { type: 'string' } }, flowSummary: { type: 'string' }, godClass: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, lines: { type: 'integer' } } } }, runtimeErrorControlFlow: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } } } },
      audit: { type: 'object', properties: { capturedFields: { type: 'array', items: { type: 'string' } }, threadSafe: { type: 'boolean' } } },
      promptMgmt: { type: 'object', properties: { storage: { type: 'string' }, versioning: { type: 'boolean' } } },
      assessment: { type: 'object', properties: { score: { type: 'integer' }, reasoning: { type: 'string' } } },
      findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string' }, area: { type: 'string' }, desc: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, recommendation: { type: 'string' } } } },
    },
    required: ['modelClient', 'modelRouter', 'budget', 'pipeline', 'audit', 'promptMgmt', 'assessment', 'findings'],
  },
})

const frontendArch = await agent(`You are auditing the FRONTEND of D:\\2917\\ai-novel. Use Read/Grep/Glob (no modifications).

Investigate:

A. State management:
   - Read frontend/src/store.ts and any storeSlices.ts
   - Count slices. For each slice, summarize state shape and main actions
   - Find any duplicated state-reset logic across slices
   - Identify if slices are properly typed (no "any")

B. Data fetching:
   - Read frontend/src/hooks.ts (or wherever useQuery calls are)
   - Count useQuery hooks, count useMutation hooks
   - Identify polling: which queries poll, at what interval, are they aggressive?
   - Note any missing staleTime / gcTime that would cause refetch storms
   - Cache invalidation strategy

C. API client:
   - Read frontend/src/api.ts (or equivalent)
   - Identify the fetch wrapper: error class? retry? timeout? abort signal?
   - Note error localization (i18n on errors?)
   - Note the network-error fallback UX

D. Type safety:
   - Read frontend/src/types.ts (or wherever the central types are). Count lines, list top-level types
   - Search for ": any" and "as any" — count occurrences and list the top 5 file:line locations
   - Check tsconfig.json strict settings

E. Component structure:
   - List top-level components in frontend/src/components/ (or pages/)
   - Note if there is a routing library (react-router, etc.) or custom conditional rendering
   - Read App.tsx — how does navigation work?
   - Note any CodeMirror / Monaco / Lexical editor integration and how it's wired

F. Styling:
   - frontend/src/styles.css line count
   - Identify the theming mechanism (CSS variables? data-theme? styled-components?)
   - Note any inline styles, style props, or CSS-in-JS

G. Build and dev:
   - Read vite.config.* (or equivalent). Note: HMR setup, proxy to backend, source maps, chunk splitting
   - Any path aliases?

H. Tests:
   - frontend/src/__tests__/, src/**/*.test.tsx, e2e/ — list what exists
   - Note: any vitest / jest config, any component tests, any hook tests
   - Playwright e2e: list spec files and approximate scenario coverage

Return JSON. For each finding, give: severity, area, file, line, desc, recommendation.`, {
  label: 'frontend:arch',
  phase: 'Frontend Deep Dive',
  schema: {
    type: 'object',
    properties: {
      stateMgmt: { type: 'object', properties: { slices: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, stateShape: { type: 'string' } } } }, resetDuplication: { type: 'array', items: { type: 'string' } } } },
      dataFetching: { type: 'object', properties: { useQueryCount: { type: 'integer' }, useMutationCount: { type: 'integer' }, pollingQueries: { type: 'array', items: { type: 'object', properties: { hook: { type: 'string' }, intervalMs: { type: 'integer' } } } } } },
      apiClient: { type: 'object', properties: { wrapper: { type: 'string' }, errorClass: { type: 'string' }, retry: { type: 'string' }, timeout: { type: 'string' }, i18nErrors: { type: 'boolean' } } },
      typeSafety: { type: 'object', properties: { anyCount: { type: 'integer' }, anyTopSites: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } }, strictMode: { type: 'boolean' } } },
      componentStructure: { type: 'object', properties: { routerLibrary: { type: 'string' }, topComponents: { type: 'array', items: { type: 'string' } }, editorIntegration: { type: 'string' } } },
      styling: { type: 'object', properties: { cssFile: { type: 'string' }, cssLines: { type: 'integer' }, themingMechanism: { type: 'string' } } },
      build: { type: 'object', properties: { bundler: { type: 'string' }, hmr: { type: 'boolean' }, backendProxy: { type: 'boolean' }, pathAliases: { type: 'array', items: { type: 'string' } } } },
      tests: { type: 'object', properties: { unit: { type: 'array', items: { type: 'string' } }, e2e: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, lines: { type: 'integer' } } } }, missingCategories: { type: 'array', items: { type: 'string' } } } },
      findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string' }, area: { type: 'string' }, desc: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, recommendation: { type: 'string' } } } },
    },
    required: ['stateMgmt', 'dataFetching', 'apiClient', 'typeSafety', 'componentStructure', 'styling', 'build', 'tests', 'findings'],
  },
})

const codeQuality = await agent(`You are auditing the CODE QUALITY of D:\\2917\\ai-novel. Use Read/Grep/Glob (no modifications).

Run these specific checks and report findings with file:line:

A. Path traversal:
   - Grep for: os.path.join, Path(, open( under backend/app/
   - For each file I/O call, check if the path is validated against an allowed root
   - Identify any caller that takes user input and feeds to open()/Path() without validation
   - Look for filename sanitization (Windows reserved names, forbidden chars)

B. SQL injection / unsafe DB:
   - Grep for: text(, execute(, raw SQL
   - Check if any router uses raw SQL strings

C. Secret leakage:
   - Grep backend/ and frontend/ for: sk-, ghp_, api_key =, token =, password = (literal assignments in code)
   - Check .gitignore: is key.txt excluded? .env excluded?

D. Type safety (backend):
   - Grep for ": Any" in backend/app/*.py — count
   - Grep for "typing.Any" imports — list files
   - Grep for "# type: ignore" — count and top sites

E. Type safety (frontend):
   - Grep for ": any" and "as any" in frontend/src — count
   - List top 10 sites with file:line:reason

F. Performance:
   - Identify any N+1: look for "for" loops with .query. / select( / await session.execute inside
   - Look for: streaming without backpressure, full file read into memory, missing pagination on list endpoints
   - Look for: sha256_file / hashlib on large files (memory risk)

G. Duplication:
   - Identify repeated patterns: child_task_ids parsing, error.try/except chains, prompt template assembly
   - For each, list the file:line sites

H. God classes:
   - Use Bash: find backend/app -name "*.py" -exec wc -l {} + | sort -rn | head -20
   - List top 10 longest files. For files >500 lines, name the file and the number of methods.

I. Error handling:
   - Grep for "except Exception" and bare "except:" — count
   - Look for places that use string-matching on error messages to classify errors
   - Look for "raise RuntimeError(...)" followed by "except RuntimeError" (control flow via exception)

J. Docstrings:
   - Pick 10 random functions in backend/app/services/ — how many have docstrings?
   - Are docstrings consistent (Google / NumPy / reST)?

K. Logging:
   - Identify the logger setup (logging.config? loguru? structlog?)
   - Are sensitive values (prompts, API keys) ever logged?

Return JSON with: counts, top sites, and findings.`, {
  label: 'quality:audit',
  phase: 'Code Quality Audit',
  schema: {
    type: 'object',
    properties: {
      pathTraversal: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' }, safe: { type: 'boolean' } } } },
      sqlInjection: { type: 'array', items: { type: 'string' } },
      secretLeakage: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } },
      gitignoreCoverage: { type: 'array', items: { type: 'string' } },
      typeSafetyBackend: { type: 'object', properties: { anyCount: { type: 'integer' }, ignoreCount: { type: 'integer' }, topSites: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } } } },
      typeSafetyFrontend: { type: 'object', properties: { anyCount: { type: 'integer' }, topSites: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } } } },
      perf: { type: 'array', items: { type: 'object', properties: { kind: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } },
      duplication: { type: 'array', items: { type: 'object', properties: { pattern: { type: 'string' }, sites: { type: 'array', items: { type: 'string' } } } } },
      godClasses: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, lines: { type: 'integer' }, methodCount: { type: 'integer' } } } },
      errorHandling: { type: 'object', properties: { bareExcept: { type: 'integer' }, stringClassifiedErrors: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, snippet: { type: 'string' } } } }, controlFlowExceptions: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } } } },
      docstrings: { type: 'object', properties: { sampledCoverage: { type: 'number' }, style: { type: 'string' } } },
      logging: { type: 'object', properties: { setup: { type: 'string' }, sensitiveLogging: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, desc: { type: 'string' } } } } } },
      findings: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string' }, category: { type: 'string' }, desc: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, recommendation: { type: 'string' } } } },
    },
    required: ['pathTraversal', 'sqlInjection', 'secretLeakage', 'gitignoreCoverage', 'typeSafetyBackend', 'typeSafetyFrontend', 'perf', 'duplication', 'godClasses', 'errorHandling', 'docstrings', 'logging', 'findings'],
  },
})

log('Deep dives complete. Beginning adversarial verification of top issues.')

const allFindings = [
  ...(backendArch.findings || []).map(f => Object.assign({}, f, { source: 'backend-arch' })),
  ...(aiPipeline.findings || []).map(f => Object.assign({}, f, { source: 'ai-pipeline' })),
  ...(frontendArch.findings || []).map(f => Object.assign({}, f, { source: 'frontend-arch' })),
  ...(codeQuality.findings || []).map(f => Object.assign({}, f, { source: 'code-quality' })),
]

const highSeverity = allFindings
  .filter(f => f.severity === 'high' || f.severity === 'critical')
  .map((f, i) => Object.assign({}, f, { idx: i }))

log('Verifying ' + highSeverity.length + ' high-severity findings with adversarial skeptics...')

const HALF = Math.ceil(highSeverity.length / 2)
const slice1 = highSeverity.slice(0, HALF)
const slice2 = highSeverity.slice(HALF)

const verify1 = await agent('You are an adversarial reviewer. For each claim below, READ the cited file:line in D:\\\\2917\\\\ai-novel and judge whether the claim is REAL (well-founded) or REFUTED (the code is actually fine, or the issue is overblown).\n\nIf REFUTED, explain what the code actually does that mitigates the concern. If REAL, confirm and add 1 concrete fix proposal.\n\nClaims to verify:\n' + JSON.stringify(slice1, null, 2) + '\n\nReturn JSON with verdict (real | refuted), reasoning, and (if real) concreteFix.', {
  label: 'verify:slice-1',
  phase: 'Adversarial Verify',
  schema: {
    type: 'object',
    properties: {
      verdicts: { type: 'array', items: { type: 'object', properties: { idx: { type: 'integer' }, verdict: { type: 'string' }, reasoning: { type: 'string' }, concreteFix: { type: 'string' } }, required: ['idx', 'verdict', 'reasoning'] } },
    },
    required: ['verdicts'],
  },
})

const verify2 = await agent('You are an adversarial reviewer. For each claim below, READ the cited file:line in D:\\\\2917\\\\ai-novel and judge whether the claim is REAL (well-founded) or REFUTED (the code is actually fine, or the issue is overblown).\n\nIf REFUTED, explain what the code actually does that mitigates the concern. If REAL, confirm and add 1 concrete fix proposal.\n\nClaims to verify:\n' + JSON.stringify(slice2, null, 2) + '\n\nReturn JSON with verdict (real | refuted), reasoning, and (if real) concreteFix.', {
  label: 'verify:slice-2',
  phase: 'Adversarial Verify',
  schema: {
    type: 'object',
    properties: {
      verdicts: { type: 'array', items: { type: 'object', properties: { idx: { type: 'integer' }, verdict: { type: 'string' }, reasoning: { type: 'string' }, concreteFix: { type: 'string' } }, required: ['idx', 'verdict', 'reasoning'] } },
    },
    required: ['verdicts'],
  },
})

const allVerdicts = [].concat(verify1.verdicts || [], verify2.verdicts || [])
const confirmedHigh = allVerdicts
  .filter(v => v.verdict === 'real')
  .map(v => {
    const f = highSeverity.find(h => h.idx === v.idx)
    return f ? Object.assign({}, f, { concreteFix: v.concreteFix, verification: v.reasoning }) : null
  })
  .filter(Boolean)

log('Adversarial verify done. ' + confirmedHigh.length + '/' + highSeverity.length + ' high-severity findings confirmed.')

phase('Synthesis')

return {
  project: 'D:\\2917\\ai-novel',
  recon: {
    structure: reconStructure,
    backendDeps: reconBackendDeps,
    frontendDeps: reconFrontendDeps,
    tests: reconTests,
  },
  backend: backendArch,
  ai: aiPipeline,
  frontend: frontendArch,
  quality: codeQuality,
  verifiedHigh: confirmedHigh,
  totalFindings: {
    high: confirmedHigh.length,
    medium: allFindings.filter(f => f.severity === 'medium').length,
    low: allFindings.filter(f => f.severity === 'low').length,
  },
}
