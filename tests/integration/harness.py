"""Shared harness for integration tests: the two-listener stack on loopback.

Each test starts the app pair in-process on ephemeral ports (``uvicorn`` on the
same event loop) and talks to it with ``httpx``. No database, no egress beyond
loopback.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn

from mocksite.admin.api import create_admin_app
from mocksite.scenarios.registry import build_default_store
from mocksite.site.render import render_product
from mocksite.site.routes import create_site_app
from mocksite.state.store import StateStore

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Stack:
    store: StateStore
    site: httpx.AsyncClient
    admin: httpx.AsyncClient


def _server(app: object, port: int) -> uvicorn.Server:
    return uvicorn.Server(
        uvicorn.Config(
            app,  # type: ignore[arg-type]
            host="127.0.0.1",
            port=port,
            log_config=None,
            access_log=False,
            lifespan="off",
            timeout_graceful_shutdown=1,
        )
    )


@contextlib.asynccontextmanager
async def running_stack(stack_builder=None) -> AsyncGenerator[Stack]:
    store, site_app, admin_app = (stack_builder or _builder())()
    site_port, admin_port = _free_port(), _free_port()
    site = _server(site_app, site_port)
    admin = _server(admin_app, admin_port)

    tasks = [
        asyncio.create_task(site.serve(), name="site"),
        asyncio.create_task(admin.serve(), name="admin"),
    ]
    for _ in range(200):
        if site.started and admin.started:
            break
        await asyncio.sleep(0.02)
    else:  # pragma: no cover - startup failure
        raise RuntimeError("servers did not start")

    try:
        async with (
            httpx.AsyncClient(base_url=f"http://127.0.0.1:{site_port}", timeout=10) as site_client,
            httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{admin_port}", timeout=10
            ) as admin_client,
        ):
            yield Stack(store=store, site=site_client, admin=admin_client)
    finally:
        site.should_exit = True
        admin.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)


def _builder(token: str = TOKEN, dist: Path | None = None):
    def build() -> tuple[StateStore, object, object]:
        store = build_default_store()
        store.set_renderer(render_product)
        site_app = create_site_app(store)
        admin_app = create_admin_app(store, token, dist or Path("does-not-exist"))
        return store, site_app, admin_app

    return build
