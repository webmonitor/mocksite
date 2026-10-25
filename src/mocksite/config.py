"""Runtime configuration.

The admin token is the only secret. It is read once at startup and never
logged; a token shorter than 32 non-whitespace characters is a startup error,
not a warning (README §5.2).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_CHARS = 32
DEFAULT_SITE_PORT = 9000
DEFAULT_ADMIN_PORT = 9001
DEFAULT_ADMIN_DIST = "web/dist"
#: Where the target pages' vendored bundles and page scripts live.
#:
#: In the repo that is ``web/targets`` (frontend code belongs under ``web/``).
#: The wheel force-includes those files to ``mocksite/_static``, so an installed
#: package resolves to the packaged copy with no env var set. ``routes.py``
#: falls back to ``web/targets`` when the packaged directory is absent, which is
#: what makes an editable install work without configuration.
DEFAULT_TARGET_ASSETS = "web/targets"
LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})


class ConfigError(RuntimeError):
    """Invalid or missing environment configuration; the process must not start."""


def _port(source: Mapping[str, str], name: str, default: int) -> int:
    raw = source.get(name)
    if raw is None or raw == "":
        return default
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535, got {port}")
    return port


def _host(source: Mapping[str, str], name: str, default: str) -> str:
    raw = source.get(name)
    return default if raw is None or raw == "" else raw


@dataclass(frozen=True, slots=True)
class Settings:
    # repr=False keeps the secret out of tracebacks and log lines that format
    # the settings object.
    token: str = field(repr=False)
    site_host: str
    site_port: int
    admin_host: str
    admin_port: int
    admin_dist: Path
    log_level: str
    #: Vendored target-page assets (``assets/`` and ``vendor/`` subdirectories).
    target_assets: Path | None = None
    #: Origin a monitoring platform should collect from (container DNS name in
    #: compose). Never assume it equals the origin a human can open.
    collect_origin: str | None = None
    #: Origin a developer's browser can open.
    public_origin: str | None = None

    @property
    def site_origin(self) -> str:
        return f"http://{self.site_host}:{self.site_port}"

    @property
    def resolved_collect_origin(self) -> str:
        return self.collect_origin or f"http://site:{self.site_port}"

    @property
    def resolved_public_origin(self) -> str:
        return self.public_origin or f"http://127.0.0.1:{self.site_port}"

    @property
    def admin_origin(self) -> str:
        return f"http://{self.admin_host}:{self.admin_port}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env

        token = source.get("MOCKSITE_TOKEN", "")
        if len("".join(token.split())) < MIN_TOKEN_CHARS:
            raise ConfigError(
                f"MOCKSITE_TOKEN must be set to at least {MIN_TOKEN_CHARS} "
                "non-whitespace characters"
            )

        site_port = _port(source, "MOCKSITE_SITE_PORT", DEFAULT_SITE_PORT)
        admin_port = _port(source, "MOCKSITE_ADMIN_PORT", DEFAULT_ADMIN_PORT)
        if site_port == admin_port:
            raise ConfigError("MOCKSITE_SITE_PORT and MOCKSITE_ADMIN_PORT must differ")

        level = source.get("MOCKSITE_LOG_LEVEL", "info").lower()
        if level not in LOG_LEVELS:
            raise ConfigError(f"MOCKSITE_LOG_LEVEL is invalid: {level!r}")

        return cls(
            token=token,
            site_host=_host(source, "MOCKSITE_SITE_HOST", "0.0.0.0"),
            site_port=site_port,
            admin_host=_host(source, "MOCKSITE_ADMIN_HOST", "0.0.0.0"),
            admin_port=admin_port,
            admin_dist=Path(source.get("MOCKSITE_ADMIN_DIST") or DEFAULT_ADMIN_DIST),
            log_level=level,
            target_assets=Path(source["MOCKSITE_TARGET_ASSETS"])
            if source.get("MOCKSITE_TARGET_ASSETS")
            else None,
            collect_origin=source.get("MOCKSITE_COLLECT_ORIGIN") or None,
            public_origin=source.get("MOCKSITE_PUBLIC_ORIGIN") or None,
        )
