#!/usr/bin/env python3
"""Command-line control for a running mocksite instance.

Wraps the same `/_admin/*` API the browser admin uses, so a verification script
and a human take exactly the same path.

    export MOCKSITE_TOKEN=$(openssl rand -hex 32)
    python scripts/control.py state
    python scripts/control.py scenario price_change
    python scripts/control.py patch '{"business": {"product": {"current_price": "96.00"}}}'
    python scripts/control.py reset
    python scripts/control.py scenarios
    python scripts/control.py pages

Every command prints JSON. Exit codes: 0 ok, 1 request failed, 2 usage/config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ADMIN = "http://127.0.0.1:9001"

# Never route loopback through an HTTP proxy: on machines with *_proxy set,
# urllib would otherwise send admin requests (and the bearer token) to it.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(
    admin: str, token: str, path: str, method: str = "GET", body: Any = None
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{admin}{path}", method=method, data=data)
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with _OPENER.open(request, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"error": payload}
    except urllib.error.URLError as exc:
        return 0, {"error": f"cannot reach {admin}: {exc.reason}"}


def _emit(status: int, payload: Any) -> int:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        # `control.py state | head` closes the pipe early; that is not an error.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0 if 200 <= status < 300 else 1
    return 0 if 200 <= status < 300 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="control", description=__doc__)
    parser.add_argument("--admin", default=os.environ.get("MOCKSITE_ADMIN_ORIGIN", DEFAULT_ADMIN))
    parser.add_argument(
        "--token",
        default=os.environ.get("MOCKSITE_TOKEN", ""),
        help="defaults to $MOCKSITE_TOKEN",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("state", help="print the current state")
    sub.add_parser("scenarios", help="list available scenarios")
    sub.add_parser("pages", help="list target pages with URLs and selectors")
    sub.add_parser("reset", help="restore defaults, clearing faults")
    scenario = sub.add_parser("scenario", help="apply a preset scenario")
    scenario.add_argument("name")
    patch = sub.add_parser("patch", help="PATCH state from a JSON object")
    patch.add_argument("json", help='JSON object, e.g. \'{"business": {"page_size": 3}}\'')

    args = parser.parse_args(argv)
    admin = args.admin.rstrip("/")

    if not args.token:
        parser.error("--token or MOCKSITE_TOKEN is required")

    if args.command == "state":
        return _emit(*_request(admin, args.token, "/_admin/state"))
    if args.command == "scenarios":
        return _emit(*_request(admin, args.token, "/_admin/scenarios"))
    if args.command == "pages":
        return _emit(*_request(admin, args.token, "/_admin/meta"))
    if args.command == "reset":
        return _emit(*_request(admin, args.token, "/_admin/reset", "POST"))
    if args.command == "scenario":
        return _emit(*_request(admin, args.token, f"/_admin/scenario/{args.name}", "POST"))

    try:
        body = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        return 2
    return _emit(*_request(admin, args.token, "/_admin/state", "PATCH", body))


if __name__ == "__main__":
    sys.exit(main())
