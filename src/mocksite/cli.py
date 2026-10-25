"""Process entrypoint: one process, two listeners, one shared ``StateStore``.

``python -m mocksite.cli`` (or the ``mocksite`` console script) starts the site
app on 9000 and the admin app on 9001 inside a single event loop and a single
process. State is in memory, so multiple workers would produce divergent copies
— the config forbids that by construction (README §6.1).

Only the site server installs signal handlers (``capture_signals`` is a no-op
off the main thread); it owns shutdown, and when it stops the admin server is
asked to stop as well.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

import uvicorn

from mocksite.admin.api import create_admin_app
from mocksite.config import ConfigError, Settings
from mocksite.scenarios.registry import build_default_store
from mocksite.site.render import render_product
from mocksite.site.routes import create_site_app
from mocksite.state.store import StateStore

LOG_FORMAT = "%(levelname)s %(name)s %(message)s"


def _build_store() -> StateStore:
    store = build_default_store()
    store.set_renderer(render_product)
    return store


def _server(app: object, host: str, port: int, level: str, *, signals: bool) -> uvicorn.Server:
    config = uvicorn.Config(
        app,  # type: ignore[arg-type]
        host=host,
        port=port,
        log_level=level,
        log_config=None,
        access_log=False,
        server_header=False,
        date_header=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    if not signals:
        # uvicorn 0.54 installs handlers from ``capture_signals``; the second
        # listener must not overwrite the first one's, or SIGTERM would stop
        # only one of the two servers. It is driven by ``serve`` instead.
        server.capture_signals = contextlib.nullcontext  # type: ignore[assignment]
    return server


async def serve(settings: Settings) -> None:
    store = _build_store()
    site_app = create_site_app(store)
    admin_app = create_admin_app(store, settings.token, settings.admin_dist)

    site = _server(
        site_app, settings.site_host, settings.site_port, settings.log_level, signals=True
    )
    admin = _server(
        admin_app, settings.admin_host, settings.admin_port, settings.log_level, signals=False
    )

    logging.getLogger("mocksite").info(
        "site %s admin %s", settings.site_origin, settings.admin_origin
    )

    site_task = asyncio.create_task(site.serve(), name="site")
    admin_task = asyncio.create_task(admin.serve(), name="admin")

    done, pending = await asyncio.wait({site_task, admin_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        with contextlib.suppress(asyncio.CancelledError):
            task.result()
    # Whichever listener stopped (signal or failure), take the other down.
    for task in pending:
        task.cancel()
    for task in pending:
        with contextlib.suppress(asyncio.CancelledError):
            await task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mocksite", description="Controllable mock target site")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate configuration and exit without binding ports",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stderr)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        logging.getLogger("mocksite").error("configuration error: %s", exc)
        return 2

    if args.check:
        logging.getLogger("mocksite").info(
            "configuration ok: site %s admin %s", settings.site_origin, settings.admin_origin
        )
        return 0

    logging.getLogger().setLevel(settings.log_level.upper())
    try:
        asyncio.run(serve(settings))
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
