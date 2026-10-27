"""The site listener: the page a collector actually fetches.

Design notes that must not drift:

* every business response carries ``X-Mocksite-Revision`` and ``no-store``;
* ``/static/notice`` serves the HTML pre-rendered at the last commit, while
  ``/ssr/notice`` renders per request from current state. The pair exists so a
  collector can be tested against both a cached page and a live one;
* ``/api/views`` is a separate request on purpose: the static HTML ships an
  empty ``#view-count``, so the counter is only observable once the page script
  has run — exactly like the portal's ``_showDynClicks``.

There is deliberately **no fault injection**. How a collector retries, times out
or reports a 500 is that collector's own contract; mocksite owns the *input*
(content and its revisions), never the transport misbehaviour.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mocksite.site.render import render_notice
from mocksite.state.models import State
from mocksite.state.store import StateStore

REVISION_HEADER = "X-Mocksite-Revision"
NO_STORE = {"Cache-Control": "no-store"}


#: Where the wheel puts the target page's assets (see pyproject
#: ``[tool.hatch.build.targets.wheel.force-include]``, which maps the subtree to
#: ``mocksite/_static/shared`` — the package root, not ``mocksite/site/``).
#: The repo keeps the files under ``web/targets`` because they are frontend
#: code, not Python.
PACKAGED_ASSETS = Path(__file__).parent.parent / "_static"
#: Repo checkout location, used when running from an editable install.
REPO_ASSETS = Path(__file__).resolve().parents[3] / "web" / "targets"


def resolve_asset_dir(explicit: Path | None = None) -> Path:
    """Locate the ``shared/`` asset directory.

    Order: explicit config, then the packaged copy inside the wheel, then the
    repo checkout. The order matters — an installed package must never depend
    on a sibling ``web/`` directory that the image deletes.
    """
    candidates = [explicit, PACKAGED_ASSETS, REPO_ASSETS]
    for candidate in candidates:
        if candidate is not None and (candidate / "shared").is_dir():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates if candidate is not None)
    raise RuntimeError(f"target page assets not found; searched: {searched}")


def create_site_app(store: StateStore, assets_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="mocksite",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def _headers(state: State) -> dict[str, str]:
        return {REVISION_HEADER: str(state.revision), **NO_STORE}

    # The page script, its stylesheet and the attachment icons live under
    # /static/shared; /static/notice stays a real route. Mounted rather than
    # proxied so the target page works with no network egress at all.
    static_dir = resolve_asset_dir(assets_dir)
    app.mount("/static/shared", StaticFiles(directory=static_dir / "shared"), name="shared")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers=NO_STORE)

    @app.get("/static/notice", response_class=HTMLResponse)
    async def static_notice() -> HTMLResponse:
        state, html = store.snapshot()
        return HTMLResponse(html, headers=_headers(state))

    @app.get("/ssr/notice", response_class=HTMLResponse)
    async def ssr_notice() -> HTMLResponse:
        state = store.state
        return HTMLResponse(render_notice(state), headers=_headers(state))

    @app.get("/api/views")
    async def api_views() -> JSONResponse:
        """The click counter, fetched by the page script like ``_showDynClicks``.

        Deliberately a separate request: the static HTML ships an empty
        ``#view-count``, so a collector reading the page before this resolves
        sees no number at all. That is the behaviour a real portal has.
        """
        state = store.state
        return JSONResponse(
            {
                "views": state.business.notice.view_count,
                "revision": state.revision,
            },
            headers=_headers(state),
        )

    return app
