"""Admin API (port 9001): state inspection, PATCH, reset, scenarios.

Contract (README §5.2):

* every route requires ``Authorization: Bearer <MOCKSITE_TOKEN>``;
* writes accept ``application/json`` only (415 otherwise), at most 64 KiB
  (413), and invalid payloads leave state untouched (400);
* responses are ``no-store`` and carry the full state, including ``revision``;
* unknown scenario -> 404;
* the SPA shell at ``/`` is served from ``MOCKSITE_ADMIN_DIST`` and is
  unaffected by site faults.

Logs record method, route template, status and revision only — never the
Authorization header or the request body.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from mocksite.admin.auth import BearerAuth
from mocksite.site.pages import pages_document
from mocksite.state.errors import StateValidationError, UnknownScenario
from mocksite.state.models import State
from mocksite.state.store import StateStore

logger = logging.getLogger("mocksite.admin")

MAX_BODY_BYTES = 64 * 1024
NO_STORE = {"Cache-Control": "no-store"}
JSON_TYPE = "application/json"
ADMIN_PREFIX = "/_admin"


def state_document(state: State) -> dict[str, Any]:
    """Wire representation: business + controls + revision, nothing else."""
    return {
        "revision": state.revision,
        "business": state.business.model_dump(mode="json"),
        "faults": state.faults.model_dump(mode="json"),
    }


def _error(status: int, code: str, errors: list[dict[str, str]] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": code}
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, headers=NO_STORE)


def _media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


async def _read_json_body(request: Request) -> Any:
    """Enforce media type and size, then parse. Raises ``_BodyError``."""
    if _media_type(request) != JSON_TYPE:
        raise _BodyError(415, "unsupported_media_type")

    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_BODY_BYTES:
                raise _BodyError(413, "body_too_large")
        except ValueError:
            raise _BodyError(400, "invalid_content_length") from None

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _BodyError(413, "body_too_large")
        chunks.append(chunk)

    raw = b"".join(chunks)
    if not raw.strip():
        raise _BodyError(400, "empty_body")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _BodyError(400, "invalid_json", str(exc)) from None


class _BodyError(Exception):
    def __init__(self, status: int, code: str, detail: str | None = None) -> None:
        self.status = status
        self.code = code
        self.detail = detail
        super().__init__(code)


def create_admin_app(
    store: StateStore,
    token: str,
    admin_dist: Path,
    *,
    site_origin: str = "http://site:9000",
    site_public_origin: str = "http://127.0.0.1:9000",
) -> FastAPI:
    app = FastAPI(
        title="mocksite admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(BearerAuth, token=token)  # type: ignore[arg-type]

    @app.middleware("http")
    async def _log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(ADMIN_PREFIX):
            route = request.scope.get("route")
            template = getattr(route, "path", "unmatched")
            logger.info(
                "%s %s -> %s revision=%s",
                request.method,
                template,
                response.status_code,
                store.state.revision,
            )
        return response

    @app.get(f"{ADMIN_PREFIX}/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(state_document(store.state), headers=NO_STORE)

    @app.patch(f"{ADMIN_PREFIX}/state")
    async def patch_state(request: Request) -> Response:
        try:
            payload = await _read_json_body(request)
        except _BodyError as exc:
            return _error(exc.status, exc.code)
        try:
            state = store.patch(payload)
        except StateValidationError as exc:
            return _error(400, "invalid_state", list(exc.errors))
        return JSONResponse(state_document(state), headers=NO_STORE)

    @app.post(f"{ADMIN_PREFIX}/reset")
    async def reset(request: Request) -> Response:
        # Bodyless POSTs are normal for reset; anything that *does* carry a body
        # must still be JSON (README §5.2), so a stray form post is a 415.
        if _media_type(request) not in ("", JSON_TYPE):
            return _error(415, "unsupported_media_type")
        before, after = store.reset()
        return JSONResponse(
            {"before": state_document(before), "after": state_document(after)},
            headers=NO_STORE,
        )

    @app.get(f"{ADMIN_PREFIX}/meta")
    async def meta() -> JSONResponse:
        """Everything the UI needs that is not state: pages, selectors, URLs."""
        return JSONResponse(
            {
                "site_origin": site_origin,
                "site_public_origin": site_public_origin,
                "pages": pages_document(site_origin, site_public_origin),
            },
            headers=NO_STORE,
        )

    @app.get(f"{ADMIN_PREFIX}/scenarios")
    async def list_scenarios() -> JSONResponse:
        return JSONResponse(
            {
                "scenarios": [
                    {
                        "name": scenario.name,
                        "description": scenario.description,
                        "affects": list(scenario.affects),
                        "pages": list(scenario.pages),
                        "title": scenario.title,
                        "outcome": scenario.outcome,
                        "data_impact": scenario.data_impact,
                        "group": scenario.group,
                        "compare_with_baseline": scenario.compare_with_baseline,
                    }
                    for scenario in store.scenarios()
                ]
            },
            headers=NO_STORE,
        )

    @app.post(f"{ADMIN_PREFIX}/scenario/{{name}}")
    async def apply_scenario(name: str) -> Response:
        try:
            before, after = store.apply_scenario(name)
        except UnknownScenario:
            return _error(404, "unknown_scenario")
        return JSONResponse(
            {"before": state_document(before), "after": state_document(after)},
            headers=NO_STORE,
        )

    _mount_spa(app, admin_dist)
    return app


def _mount_spa(app: FastAPI, admin_dist: Path) -> None:
    """Serve the built admin SPA; the shell must work even during an outage."""
    index = admin_dist / "index.html"
    assets = admin_dist / "assets"

    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    async def shell() -> Response:
        if index.is_file():
            return FileResponse(index, headers=NO_STORE)
        return _error(503, "admin_build_missing")
