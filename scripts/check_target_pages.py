#!/usr/bin/env python3
"""Browser acceptance for the client-rendered target pages (stage 4).

Requires a running stack (see `check_admin_ui.py` for the launch command) and
real Chromium. Every external origin is aborted, so a passing run also proves
the pages work with no CDN and no egress.

Covers what a collector depends on:
  * readiness only after rows exist (`#app[data-ready="true"]` + `data-revision`)
  * React and Vue rendering the same data
  * pagination: one page per click, disabled while loading, hidden at the end
  * empty list vs load failure vs missing field vs duplicate rows
  * outage leaves the page unready
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from playwright.sync_api import Page, sync_playwright

ROWS = "#inventory tbody tr.item"


@dataclass
class Results:
    failures: list[str] = field(default_factory=list)
    checks: int = 0

    def check(self, name: str, condition: bool, detail: object = "") -> None:
        self.checks += 1
        if condition:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name} :: {detail}")
            self.failures.append(name)


def _admin(origin: str, token: str, path: str, method: str = "GET") -> dict:
    request = urllib.request.Request(
        f"{origin}{path}", method=method, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:  # pragma: no cover - setup failure
        raise SystemExit(f"{method} {path} failed: HTTP {exc.code}") from None


def _rows(page: Page) -> list[tuple[str, str]]:
    return page.eval_on_selector_all(
        ROWS,
        """els => els.map(el => [
            el.dataset.id,
            (el.querySelector('td.price') ?? el.querySelector('td.cost'))?.textContent ?? ''
        ])""",
    )


def _open(page: Page, site: str, path: str) -> None:
    page.goto(f"{site}{path}", wait_until="domcontentloaded")
    page.wait_for_selector('#app[data-ready="true"]', timeout=15_000)


def run(admin: str, site: str, token: str) -> Results:
    results = Results()

    def scenario(name: str) -> None:
        _admin(admin, token, f"/_admin/scenario/{name}", "POST")

    _admin(admin, token, "/_admin/reset", "POST")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        blocked: list[str] = []
        console: list[str] = []

        def route(handler) -> None:
            url = handler.request.url
            if url.startswith((site, "data:", "about:")):
                handler.continue_()
            else:
                blocked.append(url)
                handler.abort()

        page.route("**/*", route)
        page.on(
            "console",
            lambda message: (
                console.append(f"{message.type}:{message.text}")
                if message.type == "error"
                else None
            ),
        )

        # --- React and Vue render the same rows -------------------------
        for path in ("/react/list", "/vue/list"):
            _open(page, site, path)
            results.check(
                f"{path} exposes revision", page.get_attribute("#app", "data-revision") is not None
            )
            results.check(
                f"{path} rows in order",
                [row[0] for row in _rows(page)] == ["A", "B", "C"],
                _rows(page),
            )
            results.check(
                f"{path} renders prices in td.price",
                [row[1] for row in _rows(page)] == ["10.00", "20.00", "30.00"],
                _rows(page),
            )
            results.check(
                f"{path} no data-ready before load",
                page.get_attribute("#app", "data-ready") == "true",
            )

        # --- pagination ------------------------------------------------
        _admin(admin, token, "/_admin/reset", "POST")
        _open(page, site, "/dynamic/deals")
        results.check(
            "deals first screen is one page", [r[0] for r in _rows(page)] == ["A", "B"], _rows(page)
        )
        results.check("load-more visible while more pages", page.locator("#load-more").is_visible())
        page.locator("#load-more").click()
        page.wait_for_function(f"() => document.querySelectorAll('{ROWS}').length === 3")
        results.check("one click appends one page", [r[0] for r in _rows(page)] == ["A", "B", "C"])
        results.check("load-more hidden at end", page.locator("#load-more").is_hidden())

        scenario("pagination_grow")
        _open(page, site, "/dynamic/deals")
        clicks = 0
        while page.locator("#load-more").is_visible():
            before = len(_rows(page))
            page.locator("#load-more").click()
            page.wait_for_function(f"() => document.querySelectorAll('{ROWS}').length > {before}")
            clicks += 1
            if clicks > 10:  # pragma: no cover - guard against a stuck button
                break
        results.check("growth adds a third page", clicks == 2, clicks)
        results.check(
            "complete ordered ids after pagination",
            [r[0] for r in _rows(page)] == ["A", "B", "C", "D", "E"],
            _rows(page),
        )

        # --- empty list is not a failure -------------------------------
        scenario("empty_list")
        _open(page, site, "/dynamic/deals")
        results.check("empty list still ready", page.get_attribute("#app", "data-ready") == "true")
        results.check("empty list has no rows", _rows(page) == [])
        results.check("empty list hides load-more", page.locator("#load-more").is_hidden())

        # --- item price change ----------------------------------------
        scenario("item_price_change")
        for path in ("/react/list", "/vue/list"):
            _open(page, site, path)
            prices = dict(_rows(page))
            results.check(f"{path} row A price updated", prices["A"] == "12.50", prices)
            results.check(
                f"{path} other rows unchanged", prices["B"] == "20.00" and prices["C"] == "30.00"
            )

        # --- field rename breaks only the field selector ---------------
        scenario("field_rename")
        for path in ("/react/list", "/vue/list"):
            _open(page, site, path)
            results.check(
                f"{path} rows still present after rename",
                page.locator(ROWS).count() == 3,
            )
            results.check(
                f"{path} td.price gone, td.cost present",
                page.locator(f"{ROWS} td.price").count() == 0
                and page.locator(f"{ROWS} td.cost").count() == 3,
            )

        # --- duplicate rows -------------------------------------------
        scenario("duplicate_rows")
        _open(page, site, "/react/list")
        results.check(
            "duplicate id visible", [r[0] for r in _rows(page)] == ["A", "B", "C", "A"], _rows(page)
        )

        # --- outage leaves the page unready ---------------------------
        scenario("outage")
        response = page.goto(f"{site}/react/list", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        results.check("outage returns 500", response is not None and response.status == 500)
        results.check(
            "outage sets no ready marker", page.locator('#app[data-ready="true"]').count() == 0
        )

        # assets stay reachable during an outage so the failure is diagnosable
        asset = page.request.get(f"{site}/static/assets/list.js")
        results.check("assets survive outage", asset.status == 200)

        _admin(admin, token, "/_admin/reset", "POST")
        _open(page, site, "/react/list")
        results.check(
            "recovery makes the page ready again",
            page.locator('#app[data-ready="true"]').count() == 1,
        )

        results.check("no external requests", blocked == [], blocked[:5])
        # The outage step deliberately produces one 500; any other console error
        # would mean a broken page.
        unexpected = [line for line in console if "status of 500" not in line]
        results.check("no unexpected console errors", unexpected == [], unexpected[:5])

        browser.close()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-origin", default="http://127.0.0.1:19001")
    parser.add_argument("--site-origin", default="http://127.0.0.1:19000")
    parser.add_argument("--token", default=os.environ.get("MOCKSITE_TOKEN", ""))
    args = parser.parse_args()

    if not args.token:
        parser.error("--token or MOCKSITE_TOKEN is required")

    results = run(args.admin_origin.rstrip("/"), args.site_origin.rstrip("/"), args.token)
    print(f"\n{results.checks - len(results.failures)}/{results.checks} checks passed")
    return 1 if results.failures else 0


if __name__ == "__main__":
    sys.exit(main())
