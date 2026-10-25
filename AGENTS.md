# Repository Guidelines

A controllable, reproducible mock website for developing, regression-testing and demoing **any** content-monitoring or scraping system. It is deliberately platform-agnostic: stable CSS and XPath selectors, state driven over HTTP. mocksite owns *inputs* (pages, data, deterministic faults); the consuming system owns collection, extraction, diffing, scheduling and notification.

> **Status: stages 0–4 done.** Toolchain, state kernel, two-port HTTP service, admin SPA, and all target pages (product, React/Vue lists, paginated deals) exist. Still missing: deployment image and platform integration (stage 5). Never describe planned behavior as implemented.

Docs are Chinese (`README.md`, `plan/README.md`, `changelog/`); write doc edits in Chinese and keep the three in sync.

## Architecture & Data Flow

Target design (from `README.md`, not yet built):

```
                ┌──────────── one process, one StateStore ────────────┐
admin browser ──► :9001  /_admin/*  (Bearer MOCKSITE_TOKEN)            │
                       admin SPA (web/dist) + management API          │
monitor agent ──► :9000  /static/product, /ssr/product,                │
(egress)                 /react/list, /vue/list, /dynamic/deals,       │
                         /api/data, /health                            │
                └─────────────────────────────────────────────────────┘
write path: validate → render static page → commit → revision++   (one lock)
read path:  immutable state snapshot + X-Mocksite-Revision + Cache-Control: no-store
```

- **Single process, two uvicorn listeners sharing one `StateStore`.** No multiple workers — state is in-process and resets on restart.
- **Port split is the security boundary:** `9000` site, `9001` admin. `9001` is never published by base compose and must be unreachable from collection egress. Fault injection must not affect `/_admin/*`, `/health` or local assets.
- **Versioning:** every successful write increments `revision`; invalid input changes nothing and does not advance it. Admin responses return full before/after state.
- **Scenarios are absolute, not cumulative:** each preset builds a complete target state from defaults and commits atomically. Faults never auto-recover; recovery is an explicit `baseline`/reset.
- **Frontend split:** admin SPA is built by Vite from `web/admin`; React/Vue target pages are vendored UMD assets served by the site process (`web/targets/{shared,react,vue}`), never CDN.
- Data crosses the boundary as **decimal strings** (`Decimal` server-side, never floats); prices are non-negative, finite, ≤64 chars. Missing ≠ empty string.

## Key Directories

| Path | Purpose |
|---|---|
| `src/mocksite/state/` | **Implemented** kernel: `models.py` (frozen pydantic state, price parsing), `patch.py` (PATCH merge rules), `store.py` (`StateStore` lock + commit), `errors.py` (`StateValidationError`, `UnknownScenario`). No HTTP imports |
| `src/mocksite/scenarios/` | **Implemented** `registry.py`: 13 presets + `build_default_store()` |
| `src/mocksite/site/` | **Implemented** site listener: `routes.py` (routes + fault middleware), `render.py` (Jinja2), `templates/{product,list,deals}.html`, `pages.py` (page/selector catalogue behind `/_admin/meta`) |
| `src/mocksite/site/static/` | `vendor/` = vendored UMD React 18.3.1 + Vue 3.5.43 with licenses and `manifest.json` (sha512); `assets/` = page scripts (`list.js` shared, `react-list.js`, `vue-list.js`, `deals.js`) |
| `src/mocksite/admin/` | **Implemented** admin listener: `auth.py` (constant-time bearer), `api.py` (state/reset/scenarios + SPA mount) |
| `src/mocksite/config.py`, `cli.py` | **Implemented** `Settings.from_env()` and the dual-listener entrypoint (`mocksite` console script) |
| `tests/unit/`, `tests/integration/` | Only pytest-discovered dirs. `tests/browser/` exists but is **not** in `testpaths` |
| `web/admin/` | **Implemented** admin SPA: `src/lib/api.ts` (typed client, in-memory token), `src/components/ui.tsx`, `src/features/{connection,state,scenarios,targets}`, `src/App.tsx`, `src/styles.css` |
| `web/targets/` | Vendored React/Vue target-page assets (`shared`, `react`, `vue`) — outside the Vite build |
| `deploy/` | `dev.Dockerfile` (toolchain only); deployment image is stage 5 |
| `scripts/` | `check_admin_ui.py` (29 checks) and `check_target_pages.py` (32 checks) — real-Chromium acceptance. Planned: `control.py` wrapper for `/_admin/*` |
| `plan/` | Stage 0–6 task checklists, P1–P4 acceptance groups, known blockers |
| `changelog/` | Dated records of work actually done |

## Development Commands

Everything runs in Docker; no host `.venv`, no host `pnpm install`.

```sh
# dev container (repo root, mounted at /workspace; publishes no ports)
docker compose build dev
docker compose run --rm dev python -c "import mocksite"
docker compose run --rm dev pytest -q

# frontend, inside the dev container
docker compose run --rm dev sh -lc 'cd web && pnpm install --frozen-lockfile'
docker compose run --rm dev sh -lc 'cd web && pnpm dev'        # vite 127.0.0.1:5173, root=web/admin
docker compose run --rm dev sh -lc 'cd web && pnpm typecheck'  # tsc --noEmit
docker compose run --rm dev sh -lc 'cd web && pnpm build'      # -> web/dist
```

Browser acceptance of the admin UI (needs the built bundle and a running stack):

```sh
docker compose run --rm --entrypoint mocksite -d --name mocksite-ui \
  -p 127.0.0.1:19000:9000 -p 127.0.0.1:19001:9001 --no-deps \
  -e MOCKSITE_TOKEN=<32+ chars> -e MOCKSITE_ADMIN_DIST=/workspace/web/dist dev
conda run -n webmonitor python scripts/check_admin_ui.py --token <same token>
conda run -n webmonitor python scripts/check_target_pages.py --token <same token>
docker rm -f mocksite-ui
```

`pnpm dev` binds `127.0.0.1` *inside* the container, and `compose.yaml` publishes no ports, so reaching it from the host needs both `--host 0.0.0.0` and an explicit mapping (`-p 127.0.0.1:5174:5173`); the planned `compose.dev.yaml` will map admin `9001`.

Lint/format and dependency generation are **not** in the dev image (`requirements.txt` has no `ruff`/`uv`); run them from the shared conda env:

```sh
conda activate webmonitor            # ../.github/environment.yml
ruff check src tests && ruff format --check src tests
# regenerate hash-pinned requirements — do not hand-edit requirements.txt
uv pip compile pyproject.toml --group dev --generate-hashes \
  --python-version 3.12 --universal -o requirements.txt
```

Docker stays authoritative for runtime/tests; the conda env exists for editing, linting and fast test runs, and its pins must match `pyproject.toml`.

## Code Conventions & Common Patterns

- **Python:** 3.12 only (`>=3.12,<3.13`), ruff `line-length = 100`, `target-version = "py312"`. Type hints on all new code. Async FastAPI; `asyncio_mode = "strict"` so mark async tests explicitly.
- **Exact pins, no lock file:** every dependency in `pyproject.toml` is `==`; shared package versions must match `../.github/requirements-workspace.txt`. `requirements.txt` is generated, hash-pinned, installed with `--require-hashes`.
- **Frontend:** TypeScript 7 `strict` plus `noUncheckedIndexedAccess`, `noUnusedLocals/Parameters`, `verbatimModuleSyntax`. React 19 function components, hand-written CSS, no component library. Path alias `@/*` → `web/admin/src/*` is declared in **both** `web/tsconfig.json` (`paths`, relative form — TS7 removed `baseUrl`) and `web/vite.config.ts` (`resolve.alias`); keep them in sync.
- **Admin UI rules:** the server is the only source of truth — a mutation replaces the cached document with the response body, and a failed mutation keeps the previous one. Prices are edited and submitted as strings, never numbers. Drafts survive a failed submit and are only cleared by a confirmed response. The token lives in `lib/api.ts` module memory only (never `localStorage`, URL, or logs); 401 clears it and returns to the connect screen. Never fetch `/_admin/*` before a token exists.
- **Layering (follow the plan's module names):** pure logic in `state/` and `scenarios/` (no HTTP imports — enforced today, keep it), thin routes in `site/`/`admin/`, assembly in `app.py`, process entry in `cli.py`. Tests must be able to import state/scenario logic without starting a server.
- **State kernel patterns:** pydantic models are `frozen` + `extra="forbid"`. Wire prices are decimal strings; in-process builders may pass `Decimal`; floats are rejected. Rejections raise `StateValidationError` carrying `{"loc", "msg"}` entries (never a bare `ValueError`) and report every error in one payload. Mutate only through `StateStore.patch` / `apply_scenario` / `reset`; `_commit_locked` bumps `revision`, renders, then swaps state *and* `static_html` under one lock — keep that order so a render failure cannot publish a revision. Scenarios are absolute (`build(revision)` returns a whole `State`) and never stack.
- **Validation and failure:** reject unknown keys, `null`, wrong types and out-of-range values with 400 while leaving state untouched; 401 bad token, 404 unknown scenario, 413 body >64 KiB, 415 non-`application/json`. No silent coercion, no partial commits, no fake success.
- **PATCH semantics:** objects merge recursively, arrays replace wholesale, `revision` read-only.
- **Determinism over realism:** fixed data, fixed row IDs, fixed failure sequences. No random failure rates, no background timers that recover faults.
- **Selectors are a contract** (`README.md` §3.3): `#product #current-price`, `#inventory tbody tr.item`, `td.price`, `#load-more`, `#app[data-ready="true"]`. Lists must be real `<table>` markup; normal state keeps selectors stable, and only structure-breaking scenarios may move nodes.
- **No CDN, no external fonts/scripts.** Admin and target assets ship locally; admin token lives only in page memory (never URL, `localStorage`, or logs).
- **Logging:** method, route template, status, revision only — never `Authorization`, request bodies or full query strings. `Settings.token` is `repr=False` for the same reason.
- **Fault injection is site-only:** the middleware in `site/routes.py` exempts `/health` and the asset prefixes `/static/assets/` + `/static/vendor/` only — `/static/product` is a business page and must fail during an outage. Never exempt bare `/static/`; doing so silently breaks the outage contract. `kind="outage"` wins over `delay_ms`.
- **CSR pages must not pre-render rows:** `list.html`/`deals.html` ship an empty `#app`; `data-ready="true"` and `data-revision` are set by the page script only after rows exist. Server-rendering rows would hide a broken `/api/data` path. Rows are real `<table>` markup (`#inventory tbody tr.item`, `td.price`) because the selector contract depends on it; `field_rename` swaps the cell class to `cost`.
- **Asset URLs:** `/static/assets/*` for page scripts, `/static/vendor/*` for UMD bundles. Both are mounted directories, so adding a new script means adding it to `templates/` *and* to the wheel `include` list in `pyproject.toml`.
- **Two listeners, one store:** only the site server installs signal handlers (`capture_signals` is nulled on the admin server); whichever server exits first cancels the other. Never add a second worker or process — state is in memory.

## Important Files

| File | Role |
|---|---|
| `README.md` | **Authoritative target contract**: pages, default data, selectors, state/scenario semantics, admin UI/API, ports, acceptance |
| `plan/README.md` | Implementation order (0–6), checklists, P1–P4 mapping, two blocking prerequisites |
| `changelog/README.md` + `changelog/YYYY-MM-DD.md` | What has actually shipped, with verification evidence |
| `pyproject.toml` | Build (hatchling), pins, ruff, pytest config; no entry points yet |
| `compose.yaml` | Dev-only `dev` service; publishes nothing; site/admin services arrive in stage 5 |
| `deploy/dev.Dockerfile` | Python 3.12 + Node 22 + pnpm 12.15.0, non-root UID 10001, no Chromium |
| `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json` | pnpm 12.15.0 / Node ≥22.12, Vite root `admin`, outDir `../dist`, strict TS |
| `tests/unit/test_package.py` | Only existing test: installed metadata version == `mocksite.__version__` |

## Runtime/Tooling Preferences

- **Python 3.12 / Node 22 / pnpm 12.15.0** exactly; versions are pinned in `pyproject.toml`, `web/package.json` (`packageManager`), and the dev image.
- **pnpm only** — one `web/package.json` + committed `web/pnpm-lock.yaml` for admin *and* target pages. Never add `package-lock.json`, Yarn, or a second frontend workspace.
- **Docker-first**; host needs only Docker + Compose. Frontend install/build and Python dependency install happen in the container.
- **Running the service today:** `docker compose run --rm --entrypoint mocksite -e MOCKSITE_TOKEN=<32+ chars> -p 127.0.0.1:9000:9000 -p 127.0.0.1:9001:9001 dev`. `mocksite --check` validates config without binding ports; exit code 2 means bad config.
- **Admin UI needs a build:** `MOCKSITE_ADMIN_DIST` (default `web/dist`) must contain `index.html` + `assets/`, otherwise `/` returns 503 `admin_build_missing`. Build it with `pnpm build` inside the dev container. `MOCKSITE_COLLECT_ORIGIN` / `MOCKSITE_PUBLIC_ORIGIN` control the two URLs shown in the admin's target-page panel — never assume the container hostname is browser-reachable.
- **No deployment image yet**; base compose intentionally publishes no ports. When adding it: non-root, read-only rootfs, no database/external storage.
- **Egress exceptions are the consumer's job, not this repo's.** mocksite only promises to listen on 9000 (site) and 9001 (admin) and to keep the admin port unpublished. Any allowlist entry for a monitoring platform's egress proxy belongs to that platform's deployment config; do not add per-platform integration folders here.

## Testing & QA

- pytest 9.1.1 + pytest-asyncio 1.4.0 + httpx 0.28.1 (dev group). `testpaths = ["tests/unit", "tests/integration"]` — browser tests need an explicit path or a `testpaths` change.
- **Unit:** pure in-process — validation boundaries (price strings, 0–100 rows, page size 1–100), PATCH merge semantics, revision behavior, render-then-swap atomicity, scenario absoluteness/idempotence. No server, no I/O. Current suite: 171 tests in `tests/unit/`.
- **Integration:** drive the real two-listener app with `httpx` via `tests/integration/harness.py` (auth, status codes, headers, `no-store`, fault isolation, log hygiene). `asyncio_mode = "strict"` means async fixtures use `pytest_asyncio.fixture` and async test modules set `pytestmark = pytest.mark.asyncio`. No DB.
- **Browser acceptance:** `scripts/check_admin_ui.py` and `scripts/check_target_pages.py` drive real Chromium against a running stack (see below). Both reset the server first, so they are repeatable. Note `price_change` is a substring of `item_price_change` — match scenario rows by exact `code` text. The target-page script aborts every non-site request, so "no external requests" doubles as the offline proof.
- **Acceptance is behavioral, not status codes:** a 200 proves nothing. Verify rendered HTML for static pages, post-JS DOM for CSR pages, complete ordered pagination IDs, and distinguish empty list vs load failure vs missing field vs duplicate rows. Admin acceptance requires a real browser: wrong token, invalid input, failed request, and recovery while the site returns 500.
- Coverage policy: none declared. Test boundary behavior and invariants; skip tests that only restate wiring or constants.
- Update `plan/README.md` checkboxes only with evidence, and add a `changelog/YYYY-MM-DD.md` entry (Chinese) separating planning changes from implemented work with actual commands/outputs. Never invent version numbers or claim unimplemented capabilities.
