"""Admin authentication: one shared bearer token, constant-time compare.

The token comes from ``MOCKSITE_TOKEN`` and is never echoed, logged or included
in an error response. A missing or wrong credential yields 401 with no state
content (README §5.2).
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

BEARER_PREFIX = "bearer "
UNAUTHORIZED = {"error": "unauthorized"}
NO_STORE = {"Cache-Control": "no-store"}


def _presented_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != BEARER_PREFIX.strip() or not value:
        return None
    return value.strip()


class BearerAuth:
    """ASGI-style middleware guarding every admin route except the SPA shell."""

    def __init__(self, app: Callable[..., Awaitable[None]], token: str) -> None:
        self.app = app
        self._token = token.encode()
        self._expected = token

    def _authorized(self, request: Request) -> bool:
        presented = _presented_token(request)
        if presented is None:
            return False
        return secrets.compare_digest(presented.encode(), self._token)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if request.url.path.startswith("/_admin") and not self._authorized(request):
            response = JSONResponse(UNAUTHORIZED, status_code=401, headers=NO_STORE)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def require_bearer(request: Request, token: str) -> Response | None:
    """Dependency-free check usable inside route handlers and tests."""
    presented = _presented_token(request)
    if presented is None or not secrets.compare_digest(presented.encode(), token.encode()):
        return JSONResponse(UNAUTHORIZED, status_code=401, headers=NO_STORE)
    return None
