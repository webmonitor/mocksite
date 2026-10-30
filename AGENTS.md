# Repository Guidelines

A controllable, reproducible mock website for developing, regression-testing and demoing **any** content-monitoring or scraping system. It is deliberately platform-agnostic: stable CSS and XPath selectors, state driven over HTTP. mocksite owns *inputs* (pages, data); the consuming system owns collection, extraction, diffing, scheduling and notification.

> **Status: stages 0–3, 5 and 9 done; stage 4 is obsolete, stages 7–8 are historical.** Toolchain, state kernel, two-port HTTP service, single-page admin console, the notice page, a source-built production image and Compose services exist. There is no published GHCR image and no image overlay — every run builds `mocksite:local` from this checkout. Stage 6/P4 (private-network probes, `/flaky`, `/slow`) is not implemented; transport faults are deliberately out of scope. Never describe planned behavior as implemented.

Docs are Chinese (`README.md`, `plan/README.md`, `changelog/`); write doc edits in Chinese and keep the three in sync.

## Architecture & Data Flow

Current design (built; `README.md` is authoritative):

```
                ┌──────────── one process, one StateStore ────────────┐
admin browser ──► :9001  /_admin/*  (Bearer MOCKSITE_TOKEN)            │
                       admin SPA (web/dist) + management API          │
monitor agent ──► :9000  /static/notice, /ssr/notice, /api/views,      │
(egress)                 /health, /static/shared/*                     │
                └─────────────────────────────────────────────────────┘
write path: validate → render static page → commit → revision++   (one lock)
read path:  immutable state snapshot + X-Mocksite-Revision + Cache-Control: no-store
```

- **Single process, two uvicorn listeners sharing one `StateStore`.** No multiple workers — state is in-process and resets on restart.
- **Port split is the security boundary:** `9000` site, `9001` admin. `9001` is never published by base compose and must be unreachable from collection egress. The admin listener must stay independent of site traffic and page data; `/_admin/*`, `/health` and local assets keep working while the site is being exercised.
- **Versioning:** every successful write increments `revision`; invalid input changes nothing and does not advance it. Admin responses return full before/after state.
- **Scenarios are absolute, not cumulative:** each preset builds a complete target state from defaults and commits atomically. Scenarios never auto-revert; recovery is an explicit `baseline`/reset.
- **Frontend split — all frontend code lives under `web/`; `src/` is Python only.** `web/admin/` is built by Vite into `web/dist`. The *target* page assets are **not** built: `web/targets/shared/` holds the page script, stylesheet and attachment icons, and `web/targets/manifest.json` is the (now empty) asset list. They are served directly by the site process, never from a CDN. At wheel-build time hatchling `force-include` copies the `shared` subtree to `mocksite/_static/shared/`, so the production image does not need `web/` at runtime.
- Data crosses the boundary as **decimal strings** (`Decimal` server-side, never floats); amounts are non-negative, finite, ≤64 chars. Missing ≠ empty string.

## Key Directories

| Path | Purpose |
|---|---|
| `src/mocksite/state/` | **Implemented** kernel: `models.py` (frozen pydantic state, amount parsing, minute-precision `published_at`), `patch.py` (PATCH merge rules), `store.py` (`StateStore` lock + commit), `errors.py` (`StateValidationError`, `UnknownScenario`). No HTTP imports |
| `src/mocksite/scenarios/` | **Implemented** `registry.py`: 8 presets in 3 groups (`baseline`/`fee`/`content`), with Chinese `title`/`outcome`/`data_impact` + `build_default_store()` |
| `src/mocksite/site/` | **Implemented** site listener: `routes.py` (`/static/notice`, `/ssr/notice`, `/api/views`, `/health` + the `/static/shared` mount), `render.py` (Jinja2 + `date_parts`), `templates/notice.html`, `pages.py` (page/selector catalogue with `primary`/`ready`/`supporting`/`decoy` roles, behind `/_admin/meta`). Backend only: there is **no** `static/` here — frontend assets live in `web/targets/`. |
| `web/targets/` | Frontend target-page assets: `shared/notice.js`, `shared/notice.css`, `shared/img/attachment-*.svg`; `manifest.json` is the asset list and is empty after the React/Vue runtimes were removed. Not built by Vite. |
| `src/mocksite/admin/` | **Implemented** admin listener: `auth.py` (constant-time bearer), `api.py` (state/reset/scenarios/meta + SPA mount) |
| `src/mocksite/config.py`, `cli.py` | **Implemented** `Settings.from_env()` and the dual-listener entrypoint (`mocksite` console script) |
| `tests/unit/`, `tests/integration/` | The pytest-discovered dirs (`testpaths`). `tests/acceptance/` holds the browser suites and is deliberately **outside** `testpaths`. |
| `web/admin/` | **Implemented** admin SPA, a single-page console with a pinned live preview: `src/lib/api.ts` (typed client, in-memory token), `src/components/ui.tsx`, `src/features/{connection,state,scenarios,preview}`, `src/App.tsx`, `src/styles.css` |
| `deploy/` | `Dockerfile` (production: non-root UID 10001, read-only rootfs friendly, builds the admin bundle in a Node stage) and `dev.Dockerfile` (toolchain) |
| `scripts/` | `control.py` — operational CLI over `/_admin/*`. Acceptance suites are **not** here; they live in `tests/acceptance/`. |
| `compose.yaml`, `compose.dev.yaml`, `.env.example` | Runnable `site` service (publishes only 9000) + `dev` tools profile; overlay adds 9001 for local browsers |
| `plan/` | Current stage checklists (0–3, 5, 6, 9), P1/P3/P4 acceptance groups, known blockers; stage 4/P2 is obsolete and 7–8 are historical |
| `changelog/` | Dated records of work actually done |

## Development Commands

Everything runs in Docker; no host `.venv`, no host `pnpm install`.

```sh
# dev container (repo root, mounted at /workspace; publishes no ports; profile-gated)
docker compose build dev
docker compose run --rm dev python -c "import mocksite"
docker compose run --rm dev pytest -q

# frontend, inside the dev container
docker compose run --rm dev sh -lc 'cd web && pnpm install --frozen-lockfile'
docker compose run --rm dev sh -lc 'cd web && pnpm dev'        # vite 127.0.0.1:5173, root=web/admin
docker compose run --rm dev sh -lc 'cd web && pnpm typecheck'  # tsc --noEmit
docker compose run --rm dev sh -lc 'cd web && pnpm build'      # -> web/dist
```

Browser acceptance (real Chromium against the running stack; the image builds the admin bundle itself):

```sh
cp .env.example .env    # set MOCKSITE_TOKEN
docker compose -f compose.yaml -f compose.dev.yaml up --build -d --wait
export MOCKSITE_TOKEN=$(grep ^MOCKSITE_TOKEN .env | cut -d= -f2)
conda run -n webmonitor python tests/acceptance/check_admin_ui.py      # 38 checks (last recorded 2026-10-26)
conda run -n webmonitor python tests/acceptance/check_target_pages.py  # 47 checks (last recorded 2026-10-26)
docker compose -f compose.yaml -f compose.dev.yaml down -v
```

Both scripts read the token from `$MOCKSITE_TOKEN` and default to ports 9000/9001.

`pnpm dev` binds `127.0.0.1` *inside* the dev container, and `compose.yaml` publishes no ports; the dev container is not the running stack. To reach Vite from the host, run it with `--host 0.0.0.0` and add an explicit mapping, or use `compose.dev.yaml` (which maps admin `9001`, not Vite `5173`).

Lint/format and dependency generation are **not** in the dev image (`requirements.txt` has no `ruff`/`uv`); run them from the shared conda env:

```sh
conda activate webmonitor            # ../.github/env/environment.yml
ruff check src tests && ruff format --check src tests
# regenerate hash-pinned requirements — do not hand-edit requirements.txt
uv pip compile pyproject.toml --group dev --generate-hashes \
  --python-version 3.12 --universal -o requirements.txt
```

Docker stays authoritative for runtime/tests; the conda env exists for editing, linting and fast test runs, and its pins must match `pyproject.toml`.

## Code Conventions & Common Patterns

- **Python:** 3.12 only (`>=3.12,<3.13`), ruff `line-length = 100`, `target-version = "py312"`. Type hints on all new code. Async FastAPI; `asyncio_mode = "strict"` so mark async tests explicitly.
- **Exact pins, no lock file:** every dependency in `pyproject.toml` is `==`; shared package versions must match `../.github/env/requirements-workspace.txt`. `requirements.txt` is generated, hash-pinned, installed with `--require-hashes`.
- **Frontend:** TypeScript 7 `strict` plus `noUncheckedIndexedAccess`, `noUnusedLocals/Parameters`, `verbatimModuleSyntax`. React 19 function components, hand-written CSS, no component library. Path alias `@/*` → `web/admin/src/*` is declared in **both** `web/tsconfig.json` (`paths`, relative form — TS7 removed `baseUrl`) and `web/vite.config.ts` (`resolve.alias`); keep them in sync.
- **Admin UI rules:** the server is the only source of truth — a mutation replaces the cached document with the response body, and a failed mutation keeps the previous one. Prices are edited and submitted as strings, never numbers. Drafts survive a failed submit and are only cleared by a confirmed response. The token lives in `lib/api.ts` module memory only (never `localStorage`, URL, or logs); 401 clears it and returns to the connect screen. Never fetch `/_admin/*` before a token exists.
- **Layering (follow the plan's module names):** pure logic in `state/` and `scenarios/` (no HTTP imports — enforced today, keep it), thin routes in `site/`/`admin/`, assembly in `cli.py` (`create_site_app` / `create_admin_app`), process entry in `main`. Tests must be able to import state/scenario logic without starting a server.
- **State kernel patterns:** pydantic models are `frozen` + `extra="forbid"`. Wire amounts are decimal strings; in-process builders may pass `Decimal`; floats are rejected. Rejections raise `StateValidationError` carrying `{"loc", "msg"}` entries (never a bare `ValueError`) and report every error in one payload. Mutate only through `StateStore.patch` / `apply_scenario` / `reset`; `_commit_locked` bumps `revision`, renders, then swaps state *and* `static_html` under one lock — keep that order so a render failure cannot publish a revision. Scenarios are absolute (`build(revision)` returns a whole `State`) and never stack.
- **Validation and failure:** reject unknown keys, `null`, wrong types and out-of-range values with 400 while leaving state untouched; 401 bad token, 404 unknown scenario, 413 body >64 KiB, 415 non-`application/json`. No silent coercion, no partial commits, no fake success.
- **PATCH semantics:** objects merge recursively, arrays replace wholesale, `revision` read-only.
- **Determinism over realism:** fixed data, fixed row IDs, deterministic scenario output. No random failure rates, no background timers.
- **The target site is Chinese (`zh-CN`).** Templates, page scripts and default data all carry Chinese copy: `lang="zh-CN"`, 通知标题/正文/附件下载/上一篇 headings, 点击次数已加载/点击次数加载失败/已撤回 status strings, and the `DEFAULT_NOTICE` data. `notice.css` carries a CJK font stack (`PingFang SC`, `Hiragino Sans GB`, `Microsoft YaHei`, `Noto Sans CJK SC`) and avoids `text-transform: uppercase`/wide `letter-spacing` on CJK headings. The admin SPA and the repo docs were already Chinese; the target pages now match. Identifiers a collector depends on (`#notice #current-fee`, `#notice #effective-date`, `#notice-title`, `#notice-status`, `#notice-body`, `#attachments .attachment-item`, `#view-count[data-loaded="true"]`, `.status-line[data-status]`) are language-independent and must stay unchanged.
- **Selectors are a contract** (`README.md` §3.3): `#notice #current-fee`, `#notice #effective-date`, `#notice-body p`, `#attachments .attachment-item`, `#view-count[data-loaded="true"]`, plus the decoy nodes. Every selector stays valid in every scenario — no scenario moves a node.
- **Scope: data changes only, never structural breakage.** Every scenario leaves the DOM skeleton identical; only values move. There is **no** `Presentation` layer and no "node missing"/"id renamed"/"cell class renamed" scenario — do not reintroduce one. `State` is `{revision, business}` and `PATCH /_admin/state` accepts only `business`. Extractor robustness (wrong selector, vanished node, redesigned page) is the consumer's own test, not this repo's input contract.
- **The notice page is deliberately rich, and the decoys are deliberate.** `#current-fee` and `#effective-date` are the only nodes worth monitoring; `#previous-fee`, `.unit-fee strong`, `.cap-fee strong` and `.previous-fee-note` are money-shaped traps that return a *number* when selected wrongly. The **publication instant is rendered multiple times** (`#date-badge`, `#published-date-cn`, `#published-at`; `#published-timestamp` repeats the timestamp) and all of them are date-shaped traps beside `#effective-date`; `#prev-notice` is a title-shaped trap holding *another* notice's title. These are **fixed page features, not scenarios** — do not "simplify" the page by deleting them; that removes the test value.
- **The click counter is client-rendered.** Static HTML ships `<span id="view-count" data-loaded="false"></span>` with no number; `notice.js` fetches `/api/views` and only then writes the text and flips `data-loaded`. This mirrors the portal's `_showDynClicks` — `view_count_grow` is a *data* scenario, and a collector that reads the counter before the fetch must see an empty string, not `0`.
- **Scenario copy lives on the server.** Each preset carries `title`/`outcome`/`data_impact`/`group`/`compare_with_baseline`, returned by `GET /_admin/scenarios`. The admin UI renders these; never duplicate the wording in TypeScript.
- **Admin UI is a single-page console, not a wizard or a form dump.** One screen: scenario cards grouped by 基线/收费标准/通知内容, the notice editor, a pinned live preview (`/static/notice`, `/ssr/notice`) and a facts summary (revision, active scenario, current fee, view count). The preview renders at 1180 px and is scaled down, because the notice page's 900 px breakpoint would otherwise stack the fee block below the sidebar and hide the fee. Applying a scenario asks for inline confirmation and shows `revision N → N+1`; a manual save clears the scenario badge.
- **No CDN, no external fonts/scripts.** Admin and target assets ship locally; admin token lives only in page memory (never URL, `localStorage`, or logs).
- **Logging:** method, route template, status, revision only — never `Authorization`, request bodies or full query strings. `Settings.token` is `repr=False` for the same reason.
- **There is no fault injection, and do not add one back.** 500s, delays, retry sequences and timeouts are the *collector's* contract, not an input property: mixing them into mocksite makes "the content changed" indistinguishable from "the network broke". The earlier `outage`/`slow_site` scenarios and the middleware that served them were removed on purpose. A consumer that needs failure paths uses its own fixture or a gateway in front of this one. `PATCH` rejects a `faults` section with 400 so a stale client fails loudly instead of silently doing nothing.
- **The click counter must stay client-filled:** `notice.html` ships `<span id="view-count" data-loaded="false"></span>`; `notice.js` fetches `/api/views` and only then sets the text and `data-loaded="true"`. Pre-rendering the count server-side would delete the one HTTP-vs-browser difference the page exists to demonstrate.
- **Asset URLs:** `/static/shared/*` for the page script, stylesheet and attachment icons. The files live in `web/targets/shared/`; `site/routes.py:resolve_asset_dir` looks for an explicit `MOCKSITE_TARGET_ASSETS`, then the wheel's `mocksite/_static/`, then the repo checkout. Adding a new asset means creating it under `web/targets/shared/` and referencing it from `templates/` — no pyproject change is needed because the whole subtree is force-included, but `tests/unit/test_package.py` pins the resolution order and the force-include entry.
- **Two listeners, one store:** only the site server installs signal handlers (`capture_signals` is nulled on the admin server); whichever server exits first cancels the other. Never add a second worker or process — state is in memory.

## Important Files

| File | Role |
|---|---|
| `README.md` | **Authoritative target contract**: pages, default data, selectors, state/scenario semantics, admin UI/API, ports, acceptance |
| `plan/README.md` | Current implementation order/status (0–3, 5, 6, 9), P1/P3/P4 mapping, known blockers; 4/P2 obsolete, 7–8 historical |
| `changelog/README.md` + `changelog/YYYY-MM-DD.md` | What has actually shipped, with verification evidence; older entries are dated historical records |
| `pyproject.toml` | Build (hatchling), pins, ruff, pytest config, `mocksite` console script |
| `compose.yaml` | Runnable `site` service (source build, publishes `127.0.0.1:9000`) + profile-gated `dev` toolchain; overlay adds admin `9001` |
| `deploy/dev.Dockerfile` | Python 3.12 + Node 22 + pnpm 12.15.0, non-root UID 10001, no Chromium |
| `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json` | pnpm 12.15.0 / Node ≥22.12, Vite root `admin`, outDir `../dist`, strict TS |
| `tests/unit/test_notice_page.py` | Pins the rich notice page: unique fee node among decoys, unique execution date among four date renderings, empty click counter, real body paragraphs, identical structure across all scenarios |

## Runtime/Tooling Preferences

- **Python 3.12 / Node 22 / pnpm 12.15.0** exactly; versions are pinned in `pyproject.toml`, `web/package.json` (`packageManager`), and the dev image.
- **pnpm only** — one `web/package.json` + committed `web/pnpm-lock.yaml` for admin *and* target pages. Never add `package-lock.json`, Yarn, or a second frontend workspace.
- **Docker-first**; host needs only Docker + Compose. Frontend install/build and Python dependency install happen in the container.
- **Running the service:** `cp .env.example .env` (set `MOCKSITE_TOKEN`), then `docker compose up --build -d --wait`. Only `127.0.0.1:9000` is published. For the admin UI add `-f compose.dev.yaml`, which maps `127.0.0.1:9001`. `docker compose down` stops it; state is in memory, so a restart returns to defaults. `mocksite --check` validates config without binding ports (exit code 2 = bad config).
- **Admin UI needs a build:** `MOCKSITE_ADMIN_DIST` (default `web/dist`, `/app/admin` in the image) must contain `index.html` + `assets/`, otherwise `/` returns 503 `admin_build_missing`. Build it with `pnpm build` inside the dev container.
- **Origins are two different things:** `MOCKSITE_COLLECT_ORIGIN` (default `http://site:9000` — the compose **service** name, which resolves on the network) is what a collector uses; `MOCKSITE_PUBLIC_ORIGIN` (default `http://127.0.0.1:9000`) is what a browser opens. The project name `mocksite` is not a hostname and does not resolve — that bug was real once; keep the distinction.
- **Local scripts must bypass `*_proxy` for loopback.** On machines with `http_proxy` set, urllib routes `127.0.0.1` through the proxy and every admin call fails with 502 while `curl` works. `control.py` and both acceptance scripts build an opener with an empty `ProxyHandler`; do the same in any new script.
- **The deployment image is source-built, not published.** `deploy/Dockerfile` produces a non-root (`10001`), read-only-rootfs-friendly image with no database or external storage; `compose.yaml` builds it as `mocksite:local` and publishes only `127.0.0.1:9000`. There is no mocksite GHCR package or image overlay; never document a registry pull for this repo.
- **Egress exceptions and network attachment are the consumer's job, not this repo's.** mocksite only promises to listen on 9000 (site) and 9001 (admin) and to keep the admin port unpublished. A collector joins mocksite's Docker network and allowlists exactly `site:9000` in its own egress and target policy; this repo provides no Agent-specific overlay or dedicated Squid config, and no per-platform integration folders.

## Testing & QA

- pytest 9.1.1 + pytest-asyncio 1.4.0 + httpx 0.28.1 (dev group). `testpaths = ["tests/unit", "tests/integration"]` — browser tests need an explicit path or a `testpaths` change. Run host-side pytest with `env -u no_proxy -u NO_PROXY -u all_proxy -u http_proxy -u https_proxy`: the `[::1]` entry in `no_proxy` makes httpx fail to parse loopback URLs.
- **Unit:** pure in-process — validation boundaries (decimal-string amounts, notice text/body/attachment limits, `published_at`/`effective_date` formats, status enum), PATCH merge semantics, revision behavior, render-then-swap atomicity, scenario absoluteness/idempotence, and that page structure is identical across every scenario. No server, no I/O. Last recorded run (2026-10-26, before the 2026-10-30 doc pass): 266 passed (204 unit + 62 integration). The doc pass did not rerun tests.
- **Integration:** drive the real two-listener app with `httpx` via `tests/integration/harness.py` (auth, status codes, headers, `no-store`, log hygiene). `asyncio_mode = "strict"` means async fixtures use `pytest_asyncio.fixture` and async test modules set `pytestmark = pytest.mark.asyncio`. No DB.
- **Browser acceptance:** `tests/acceptance/check_admin_ui.py` and `tests/acceptance/check_target_pages.py` drive real Chromium against a running stack (see `tests/acceptance/README.md`). They share `tests/acceptance/_harness.py` (Results, proxy-bypassing admin calls, console capture, arg parsing); put plumbing there and assertions in the suite. Both reset the server first, so they are repeatable. Scenario cards are matched by their Chinese `title` inside a group tab, not by the code identifier. The target-page script aborts every non-site request, so "no external requests" doubles as the offline proof.
- **Acceptance is behavioral, not status codes:** a 200 proves nothing. Verify rendered HTML for the notice page and the post-JS DOM for the click counter. Admin acceptance requires a real browser: wrong token, invalid input, failed request, and recovery.
- Coverage policy: none declared. Test boundary behavior and invariants; skip tests that only restate wiring or constants.
- Update `plan/README.md` checkboxes only with evidence, and add a dated Chinese changelog entry separating planning changes from implemented work with actual commands/outputs. A doc-only pass that does not warrant a new file records itself in `changelog/README.md` and states whether anything was run. Never invent version numbers or claim unimplemented capabilities.
