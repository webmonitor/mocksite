"""Shared harness for the browser acceptance suites.

These suites are **not** pytest tests: they drive a real Chromium against a
running stack and need a live admin token, so they live outside `testpaths`
and are run explicitly (see `tests/acceptance/README.md`).

What lives here is the plumbing every suite would otherwise duplicate:

* :class:`Results` — PASS/FAIL lines plus an exit code;
* :func:`admin_request` — admin API calls that bypass `*_proxy`;
* :func:`read_token` — token from `--token` or `$MOCKSITE_TOKEN`;
* :func:`console_collector` — captures console errors and uncaught exceptions;
* :func:`parse_common_args` — the shared `--admin-origin` / `--site-origin`.

Anything that encodes *what the product should do* belongs in the suite, not
here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Page

#: Loopback must bypass ``*_proxy``; otherwise urllib sends the bearer token to
#: the machine's proxy and every admin call fails with 502 while curl works.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

DEFAULT_ADMIN_ORIGIN = "http://127.0.0.1:9001"
DEFAULT_SITE_ORIGIN = "http://127.0.0.1:9000"
MIN_TOKEN_LENGTH = 32


@dataclass
class Results:
    """Collects PASS/FAIL lines and turns them into an exit code."""

    failures: list[str] = field(default_factory=list)
    checks: int = 0

    def check(self, name: str, condition: object, detail: object = "") -> None:
        """Record one behavioural assertion.

        ``condition`` is truthy-tested rather than typed as ``bool`` so callers
        can pass a locator count or an expression result directly.
        """
        self.checks += 1
        if condition:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name} :: {detail}")
            self.failures.append(name)

    @property
    def passed(self) -> int:
        return self.checks - len(self.failures)

    def report(self) -> int:
        """Print the summary and return a process exit code."""
        print(f"\n{self.passed}/{self.checks} checks passed")
        if self.failures:
            print("failed:", ", ".join(self.failures))
            return 1
        return 0


def admin_request(
    base: str, path: str, token: str, method: str = "GET", body: Any = None
) -> tuple[int, dict]:
    """Call the admin API, returning ``(status, payload)``.

    HTTP errors are returned rather than raised, because several suites assert
    on 4xx responses.
    """
    headers = {"Authorization": f"Bearer {token}"}
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()

    request = urllib.request.Request(f"{base}{path}", method=method, headers=headers, data=data)
    try:
        with _OPENER.open(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except (ValueError, OSError):
            return exc.code, {}


def reset_server(admin_origin: str, token: str) -> int:
    """Reset to defaults so a run starts from a known state; returns revision."""
    status, payload = admin_request(admin_origin, "/_admin/reset", token, "POST")
    if status != 200:  # pragma: no cover - setup failure
        raise SystemExit(f"cannot reset server: HTTP {status}")
    return int(payload.get("after", {}).get("revision", 0))


def apply_scenario(admin_origin: str, token: str, name: str) -> dict:
    status, payload = admin_request(admin_origin, f"/_admin/scenario/{name}", token, "POST")
    if status != 200:  # pragma: no cover - setup failure
        raise SystemExit(f"cannot apply scenario {name}: HTTP {status}")
    return payload


@dataclass
class ConsoleLog:
    """Console errors and uncaught JS exceptions seen during a run."""

    errors: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)

    def attach(self, page: Page) -> None:
        def on_console(message: Any) -> None:
            if message.type == "error":
                self.errors.append(f"{message.type}:{message.text}")

        page.on("console", on_console)
        page.on("pageerror", lambda error: self.exceptions.append(str(error)))

    def unexpected(self, *, allowed_statuses: tuple[str, ...] = ()) -> list[str]:
        """Console errors excluding the status codes a suite produces on purpose."""
        return [
            line
            for line in self.errors
            if not any(f"status of {code}" in line for code in allowed_statuses)
        ]


def read_token(explicit: str | None = None) -> str:
    """Token from ``--token`` or ``$MOCKSITE_TOKEN``; exits with a clear message."""
    token = (explicit or os.environ.get("MOCKSITE_TOKEN", "")).strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise SystemExit(
            "set MOCKSITE_TOKEN (or pass --token) to the server's admin token "
            f"(at least {MIN_TOKEN_LENGTH} characters)"
        )
    return token


def parse_common_args(description: str) -> argparse.Namespace:
    """The arguments every acceptance suite accepts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--admin-origin", default=DEFAULT_ADMIN_ORIGIN)
    parser.add_argument("--site-origin", default=DEFAULT_SITE_ORIGIN)
    parser.add_argument(
        "--token",
        default=os.environ.get("MOCKSITE_TOKEN", ""),
        help="admin token (defaults to $MOCKSITE_TOKEN)",
    )
    args = parser.parse_args()
    args.admin_origin = args.admin_origin.rstrip("/")
    args.site_origin = args.site_origin.rstrip("/")
    return args


def main_guard(run) -> int:
    """Wrap a suite's ``run(args, token) -> Results`` as a script entrypoint."""
    args = parse_common_args(run.__doc__ or "")
    token = read_token(args.token)
    return run(args, token).report()


def run_as_script(run) -> None:
    sys.exit(main_guard(run))
