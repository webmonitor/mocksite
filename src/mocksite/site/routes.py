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

#: Where the wheel puts the vendored target-page assets (see pyproject
#: ``[tool.hatch.build.targets.wheel.force-include]``, which maps the three
#: subtrees to ``mocksite/_static/{shared,react,vue}`` — the package root, not
#: ``mocksite/site/``).
#: The repo keeps the files under ``web/targets`` because they are frontend
#: code, not Python. ``shared/`` holds framework-agnostic page assets,
#: ``react/`` and ``vue/`` each hold one page script plus that framework's
#: vendored UMD bundles and licenses.
PACKAGED_ASSETS = Path(__file__).parent.parent / "_static"
#: Repo checkout location, used when running from an editable install.
REPO_ASSETS = Path(__file__).resolve().parents[3] / "web" / "targets"

ASSET_PREFIXES = ("/static/shared/", "/static/react/", "/static/vue/")


def resolve_asset_dir(explicit: Path | None = None) -> Path:
    """Locate ``shared/``, ``react/`` and ``vue/``.

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


REVISION_HEADER = "X-Mocksite-Revision"
NO_STORE = {"Cache-Control": "no-store"}
OUTAGE_STATUS = 500
PAGE_SIZE_HEADER = "X-Mocksite-Page-Size"


def _json(state: State) -> dict[str, Any]:
    return state.business.model_dump(mode="json")


def create_site_app(store: StateStore, assets_dir: Path | None = None) -> FastAPI:
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

    # Vendored runtimes and page scripts live under /static/{shared,react,vue};
    # /static/product stays a real route. Mounted rather than proxied so the
    # target pages work with no network egress at all. The files themselves
    # live in web/targets (frontend code) and are force-included into the
    # wheel at build time.
    static_dir = resolve_asset_dir(assets_dir)
    app.mount("/static/shared", StaticFiles(directory=static_dir / "shared"), name="shared")
    app.mount("/static/react", StaticFiles(directory=static_dir / "react"), name="react")
    app.mount("/static/vue", StaticFiles(directory=static_dir / "vue"), name="vue")

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
        payload["review_page_count"] = state.business.review_page_count
        return JSONResponse(payload, headers=_headers(state))

    @app.get("/api/reviews")
    async def api_reviews(page: int = 1) -> JSONResponse:
        """One page of reviews, so a collector can page them without the DOM.

        ``page`` is 1-based; out-of-range pages return an empty ``reviews``
        list rather than an error, which is what a real shop does.
        """
        state = store.state
        business = state.business
        size = business.review_page_size
        index = max(page, 1) - 1
        chunk = business.reviews[index * size : (index + 1) * size]
        return JSONResponse(
            {
                "reviews": [review.model_dump(mode="json") for review in chunk],
                "page": index + 1,
                "page_size": size,
                "page_count": business.review_page_count,
                "total": len(business.reviews),
                "revision": state.revision,
            },
            headers=_headers(state),
        )

    return app
