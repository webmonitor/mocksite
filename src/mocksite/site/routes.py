"""Site listener: the pages a monitoring platform collects (port 9000).

Rules that matter for verification:

* every business response carries ``X-Mocksite-Revision`` and ``no-store``;
* faults (500 / delay) apply to business routes only — ``/health`` and local
  assets keep working so a failed run is always recoverable and diagnosable;
* ``/static/product`` serves the page rendered at the last commit, while
  ``/ssr/product`` renders from the current snapshot on every request.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mocksite.site.render import render_deals, render_list, render_product
from mocksite.state.models import State
from mocksite.state.store import StateStore

STATIC_DIR = Path(__file__).parent / "static"

ASSET_PREFIXES = ("/static/assets/", "/static/vendor/")

REVISION_HEADER = "X-Mocksite-Revision"
NO_STORE = {"Cache-Control": "no-store"}
OUTAGE_STATUS = 500
PAGE_SIZE_HEADER = "X-Mocksite-Page-Size"


def _json(state: State) -> dict[str, Any]:
    return state.business.model_dump(mode="json")


def create_site_app(store: StateStore) -> FastAPI:
    app = FastAPI(
        title="mocksite",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def _faults(request: Request, call_next: Any) -> Response:
        path = request.url.path
        # Health and the mounted asset trees stay up during a fault so the
        # failure is diagnosable and the admin can still recover the instance.
        # `/static/product` is a business page, not an asset, so it must NOT be
        # exempt — the prefix alone would wrongly let it through.
        if path == "/health" or path.startswith(ASSET_PREFIXES):
            return await call_next(request)

        faults = store.state.faults
        if faults.kind == "outage":
            return JSONResponse(
                {"error": "outage"},
                status_code=OUTAGE_STATUS,
                headers={REVISION_HEADER: str(store.state.revision), **NO_STORE},
            )
        if faults.delay_ms:
            await asyncio.sleep(faults.delay_ms / 1000)
        return await call_next(request)

    def _headers(state: State) -> dict[str, str]:
        return {REVISION_HEADER: str(state.revision), **NO_STORE}

    # Vendored runtimes and page scripts live under /static/assets and
    # /static/vendor; /static/product stays a real route. Mounted rather than
    # proxied so the target pages work with no network egress at all.
    app.mount("/static/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    app.mount("/static/vendor", StaticFiles(directory=STATIC_DIR / "vendor"), name="vendor")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers=NO_STORE)

    @app.get("/static/product", response_class=HTMLResponse)
    async def static_product() -> HTMLResponse:
        state, html = store.snapshot()
        return HTMLResponse(html, headers=_headers(state))

    @app.get("/ssr/product", response_class=HTMLResponse)
    async def ssr_product() -> HTMLResponse:
        state = store.state
        return HTMLResponse(render_product(state), headers=_headers(state))

    @app.get("/react/list", response_class=HTMLResponse)
    async def react_list() -> HTMLResponse:
        state = store.state
        return HTMLResponse(render_list(state, "react"), headers=_headers(state))

    @app.get("/vue/list", response_class=HTMLResponse)
    async def vue_list() -> HTMLResponse:
        state = store.state
        return HTMLResponse(render_list(state, "vue"), headers=_headers(state))

    @app.get("/dynamic/deals", response_class=HTMLResponse)
    async def dynamic_deals() -> HTMLResponse:
        state = store.state
        return HTMLResponse(render_deals(state), headers=_headers(state))

    @app.get("/api/data")
    async def api_data() -> JSONResponse:
        state = store.state
        payload = _json(state)
        payload["revision"] = state.revision
        payload["page_count"] = state.business.page_count
        return JSONResponse(payload, headers=_headers(state))

    return app
