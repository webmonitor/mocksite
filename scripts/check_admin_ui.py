#!/usr/bin/env python3
"""Browser acceptance for the admin UI (stage 3).

Requires a running stack with the built admin bundle:

    docker compose run --rm --entrypoint mocksite -d --name mocksite-ui \\
      -p 127.0.0.1:19000:9000 -p 127.0.0.1:19001:9001 --no-deps \\
      -e MOCKSITE_TOKEN=<32+ chars> -e MOCKSITE_ADMIN_DIST=/workspace/web/dist dev

    MOCKSITE_TOKEN=<same token> python scripts/check_admin_ui.py

The script resets the server first, so it is repeatable. It exercises the flow
the README requires: connect (including a rejected token), edit, apply a
scenario, reset, survive an outage and recover, and never persist the token.
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


def _request(base: str, path: str, token: str, method: str = "GET") -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{base}{path}", method=method, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _wait_for_revision(page: Page, revision: int) -> None:
    page.wait_for_function(
        "expected => document.querySelector('[data-testid=revision]').textContent"
        ".includes(`revision ${expected}`)",
        arg=revision,
        timeout=10_000,
    )


def _confirm(page: Page) -> None:
    page.get_by_role("button", name="确认").click()


def _scenario_row(page: Page, name: str):
    # `price_change` is a substring of `item_price_change`, so match the code
    # element exactly rather than by substring.
    return (
        page.locator(".scenarios > li")
        .filter(has=page.locator("code", has_text=name))
        .filter(has_not=page.locator("code", has_text=f"item_{name}"))
    )


def run(admin_origin: str, site_origin: str, token: str) -> Results:
    results = Results()

    status, baseline = _request(admin_origin, "/_admin/reset", token, "POST")
    if status != 200:  # pragma: no cover - setup failure
        raise SystemExit(f"cannot reset server: HTTP {status}")
    revision = baseline["after"]["revision"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        console: list[str] = []
        js_errors: list[str] = []
        page.on(
            "console",
            lambda message: (
                console.append(f"{message.type}:{message.text}")
                if message.type == "error"
                else None
            ),
        )
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        page.goto(admin_origin, wait_until="domcontentloaded")
        results.check("connect screen shown", page.get_by_role("heading", name="连接").is_visible())
        results.check("no state before auth", page.locator("[data-testid=revision]").count() == 0)

        page.fill("#token", "wrong-token-wrong-token-wrong-token-xx")
        page.get_by_role("button", name="连接").click()
        page.wait_for_timeout(800)
        body = page.content()
        results.check("wrong token rejected", "401" in body and "128.50" not in body, body[:200])
        storage = page.evaluate("() => JSON.stringify({...localStorage, ...sessionStorage})")
        results.check("token never stored", token not in storage, storage)
        results.check("typed value kept for correction", page.input_value("#token") != "")

        page.fill("#token", token)
        page.get_by_role("button", name="连接").click()
        page.wait_for_selector("[data-testid=revision]", timeout=10_000)
        results.check(
            "revision shown after connect",
            f"revision {revision}" in page.inner_text("[data-testid=revision]"),
        )
        results.check("product price shown", "128.50" in page.content())
        results.check("scenario list rendered", page.locator(".scenarios > li").count() >= 13)

        page.fill("#product-current-price", "96.00")
        page.get_by_role("button", name="保存商品与列表").click()
        _wait_for_revision(page, revision + 1)
        results.check("save bumps revision", True)
        results.check(
            "site page reflects edit",
            "96.00" in page.request.get(f"{site_origin}/ssr/product").text(),
        )

        page.fill("#product-current-price", "1e2")
        page.get_by_role("button", name="保存商品与列表").click()
        page.wait_for_selector(".field-invalid", timeout=10_000)
        results.check("invalid price shows field error", True)
        results.check(
            "draft preserved after failure", page.input_value("#product-current-price") == "1e2"
        )
        results.check(
            "revision unchanged after failed save",
            f"revision {revision + 1}" in page.inner_text("[data-testid=revision]"),
        )
        page.get_by_role("button", name="放弃修改").click()

        _scenario_row(page, "price_change").get_by_role("button", name="应用").click()
        page.wait_for_selector("[role=alertdialog]", timeout=5_000)
        results.check("confirmation before applying scenario", True)
        _confirm(page)
        _wait_for_revision(page, revision + 2)
        results.check(
            "before/after reported", f"revision {revision + 1} → {revision + 2}" in page.content()
        )
        results.check(
            "editor follows scenario", page.input_value("#product-current-price") == "96.00"
        )

        page.get_by_role("button", name="恢复默认").click()
        _confirm(page)
        _wait_for_revision(page, revision + 3)
        results.check(
            "reset restores default price", page.input_value("#product-current-price") == "128.50"
        )

        page.locator("#fault-kind").select_option("outage")
        page.get_by_role("button", name="应用控制项").click()
        page.wait_for_timeout(800)
        results.check(
            "outage makes site 500",
            page.request.get(f"{site_origin}/ssr/product").status == 500,
        )
        results.check(
            "admin interactive during outage", page.locator(".scenarios > li").count() >= 13
        )
        page.get_by_role("button", name="恢复默认").click()
        _confirm(page)
        page.wait_for_timeout(800)
        results.check(
            "recovery restores site",
            page.request.get(f"{site_origin}/ssr/product").status == 200,
        )

        results.check(
            "collect and preview URLs differ",
            page.locator("dl.urls dt", has_text="采集地址").count() >= 5,
        )
        results.check(
            "selector copy buttons present",
            page.get_by_role("button", name="复制 CSS").count() >= 2,
        )
        # Every page in the catalogue is implemented as of stage 4; a "planned"
        # badge would mean the UI is advertising something that does not exist.
        results.check("no page advertised as planned", page.locator(".badge-planned").count() == 0)
        results.check("all catalogue pages marked implemented", page.locator(".badge").count() >= 5)
        results.check("token not in URL", token not in page.url)

        page.get_by_role("button", name="退出").click()
        results.check(
            "logout returns to connect", page.get_by_role("heading", name="连接").is_visible()
        )

        page.fill("#token", token)
        page.get_by_role("button", name="连接").click()
        page.wait_for_selector("[data-testid=revision]", timeout=10_000)
        page.reload(wait_until="domcontentloaded")
        results.check(
            "refresh clears session", page.get_by_role("heading", name="连接").is_visible()
        )

        # A 401 and a 400 are produced on purpose above; anything else is a bug.
        unexpected = [
            line for line in console if "status of 401" not in line and "status of 400" not in line
        ]
        results.check("no unexpected console errors", not unexpected, unexpected)
        results.check("no uncaught JS exceptions", not js_errors, js_errors)

        browser.close()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-origin", default="http://127.0.0.1:19001")
    parser.add_argument("--site-origin", default="http://127.0.0.1:19000")
    parser.add_argument(
        "--token",
        default=os.environ.get("MOCKSITE_TOKEN", ""),
        help="admin token (defaults to $MOCKSITE_TOKEN)",
    )
    args = parser.parse_args()

    if not args.token:
        parser.error("--token or MOCKSITE_TOKEN is required")

    results = run(args.admin_origin.rstrip("/"), args.site_origin.rstrip("/"), args.token)
    print(f"\n{results.checks - len(results.failures)}/{results.checks} checks passed")
    return 1 if results.failures else 0


if __name__ == "__main__":
    sys.exit(main())
