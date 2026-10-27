#!/usr/bin/env python3
"""Acceptance: the target page a collector fetches.

Every external origin is aborted, so a passing run also proves the page works
with no CDN and no egress.

Covers what a collector depends on:
  * the notice page's fixed skeleton, decoy fee nodes, the one instant rendered
    three ways, the script-filled click counter and the real body paragraphs
  * data scenarios moving values while the DOM skeleton stays identical
  * the list pages, their assets and the JSON data endpoint being gone
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import (
    ConsoleLog,
    Results,
    apply_scenario,
    reset_server,
    run_as_script,
)

REMOVED_PATHS = (
    "/react/list",
    "/vue/list",
    "/dynamic/archive",
    "/api/data",
    "/static/shared/list.js",
    "/static/shared/list.css",
    "/static/shared/archive.js",
    "/static/react/react-list.js",
    "/static/vue/vue-list.js",
)


def _open_notice(page: Page, site: str, path: str = "/static/notice") -> None:
    """Notice pages are server-rendered; only the click counter waits on JS."""
    page.goto(f"{site}{path}", wait_until="domcontentloaded")
    page.wait_for_selector('#view-count[data-loaded="true"]', timeout=15_000)


def run(args, token: str) -> Results:
    admin, site = args.admin_origin, args.site_origin
    results = Results()

    def scenario(name: str) -> None:
        apply_scenario(admin, token, name)

    reset_server(admin, token)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        blocked: list[str] = []
        console = ConsoleLog()

        def route(handler) -> None:
            url = handler.request.url
            if url.startswith((site, "data:", "about:")):
                handler.continue_()
            else:
                blocked.append(url)
                handler.abort()

        page.route("**/*", route)
        console.attach(page)

        # --- realistic notice-detail page -------------------------------
        _open_notice(page, site)
        results.check(
            "notice page fee is unique",
            page.locator("#current-fee").count() == 1,
        )
        results.check(
            "notice page fee text",
            page.inner_text("#current-fee") == "128.50",
            page.inner_text("#current-fee"),
        )
        results.check(
            "notice page carries a revision",
            page.get_attribute("#notice", "data-revision") is not None,
        )
        # The decoys must be selectable, otherwise they are not decoys.
        for label, selector in (
            ("previous fee", "#previous-fee"),
            ("unit fee", ".unit-fee strong"),
            ("cap fee", ".cap-fee strong"),
            ("previous note", ".previous-fee-note"),
            ("date badge", "#date-badge"),
            ("chinese publication date", "#published-date-cn"),
            ("publication timestamp", "#published-at"),
            ("prev notice title", "#prev-notice"),
        ):
            results.check(f"decoy present: {label}", page.locator(selector).count() == 1)
        results.check(
            "money-shaped values are plentiful",
            len(page.locator(".fee-block").inner_text().split(".")) >= 4,
        )

        # One publication instant, three renderings, plus the execution date.
        badge = page.inner_text("#date-badge").replace("\n", "").strip()
        full = page.inner_text("#published-date-cn")
        stamp = page.inner_text("#published-at")
        results.check(
            "one instant rendered three ways",
            badge.startswith("10月20日") and full == "2026年10月20日" and stamp == "2026-10-20 14:32",
            (badge, full, stamp),
        )
        results.check(
            "effective date is a different date entirely",
            page.inner_text("#effective-date") == "2026-11-01",
            page.inner_text("#effective-date"),
        )
        results.check(
            "click counter is filled by the script",
            page.get_attribute("#view-count", "data-loaded") == "true"
            and page.inner_text("#view-count") == "128",
            page.inner_text("#view-count"),
        )
        results.check(
            "body is real paragraphs",
            page.locator("#notice-body p").count() >= 5,
            page.locator("#notice-body p").count(),
        )
        results.check(
            "attachments carry kind",
            page.locator("#attachments .attachment-item").count() == 4
            and page.locator('#attachments .attachment-item[data-kind="pdf"]').count() == 2,
        )
        results.check(
            "prev/next navigation is present",
            page.locator("#prev-notice").count() == 1 and page.locator("#next-notice").count() == 1,
        )
        results.check(
            "status is machine-readable",
            page.get_attribute(".status-line", "data-status") == "published",
        )

        # SSR must produce the same skeleton as the pre-rendered page.
        _open_notice(page, site, "/ssr/notice")
        results.check(
            "ssr page exposes the same fee",
            page.inner_text("#current-fee") == "128.50",
        )
        results.check(
            "ssr page fills the counter too",
            page.get_attribute("#view-count", "data-loaded") == "true",
        )

        # Data scenarios: values move, the DOM skeleton never does.
        scenario("fee_change")
        _open_notice(page, site)
        results.check(
            "fee_change moves the fee value",
            page.inner_text("#current-fee") == "96.00",
        )
        results.check(
            "fee_change keeps every structural node",
            page.locator("#previous-fee").count() == 1
            and page.locator("#notice-body").count() == 1
            and page.locator("#effective-date").count() == 1
            and page.locator("#attachments").count() == 1,
        )

        scenario("fee_increase")
        _open_notice(page, site)
        results.check(
            "fee_increase moves the fee upward",
            page.inner_text("#current-fee") == "158.00",
        )

        scenario("notice_withdrawn")
        _open_notice(page, site)
        results.check(
            "notice_withdrawn shows the withdrawn state",
            page.get_attribute(".status-line", "data-status") == "withdrawn",
        )
        results.check(
            "notice_withdrawn shows a banner",
            page.locator("#withdrawn-banner").count() == 1,
        )
        results.check(
            "notice_withdrawn keeps the fee value",
            page.inner_text("#current-fee") == "128.50",
        )

        scenario("effective_date_shift")
        _open_notice(page, site)
        results.check(
            "effective_date_shift moves the effective date",
            page.inner_text("#effective-date") == "2026-12-01",
        )
        results.check(
            "effective_date_shift leaves the publication alone",
            page.inner_text("#published-at") == "2026-10-20 14:32"
            and page.inner_text("#published-date-cn") == "2026年10月20日",
        )

        scenario("title_change")
        _open_notice(page, site)
        results.check(
            "title_change moves only the heading",
            page.inner_text("#notice-title").endswith("补充通知")
            and page.inner_text("#current-fee") == "128.50",
        )

        scenario("view_count_grow")
        _open_notice(page, site)
        results.check(
            "view_count_grow changes only the counter",
            page.inner_text("#view-count") == "1531"
            and page.inner_text("#current-fee") == "128.50",
        )
        results.check(
            "view_count_grow leaves the publication alone",
            page.inner_text("#published-at") == "2026-10-20 14:32",
        )

        # Every scenario must leave the same DOM skeleton behind. This is the
        # contract that replaced the old structural-breakage scenarios.
        markers = (
            "#current-fee",
            "#previous-fee",
            "#effective-date",
            "#notice-body",
            "#attachments",
        )
        shapes = {}
        for name in (
            "baseline",
            "fee_change",
            "fee_increase",
            "notice_withdrawn",
            "effective_date_shift",
            "title_change",
            "view_count_grow",
        ):
            scenario(name)
            _open_notice(page, site)
            shapes[name] = [marker for marker in markers if page.locator(marker).count() == 1]
        baseline_shape = shapes["baseline"]
        results.check(
            "structure is identical across all data scenarios",
            all(shape == baseline_shape for shape in shapes.values()),
            shapes,
        )
        reset_server(admin, token)

        # --- the list pages are gone ------------------------------------
        for path in REMOVED_PATHS:
            response = page.request.get(f"{site}{path}")
            results.check(f"removed: {path}", response.status == 404, response.status)

        # --- assets are served locally, with no egress ------------------
        for asset_path in ("/static/shared/notice.css", "/static/shared/notice.js"):
            asset = page.request.get(f"{site}{asset_path}")
            results.check(f"asset served: {asset_path}", asset.status == 200)

        # --- the counter follows a reset --------------------------------
        reset_server(admin, token)
        _open_notice(page, site)
        results.check(
            "recovery restores the counter",
            page.inner_text("#view-count") == "128",
        )

        results.check("no external requests", blocked == [], blocked[:5])
        unexpected = console.unexpected()
        results.check("no unexpected console errors", not unexpected, unexpected[:5])

        browser.close()

    return results


if __name__ == "__main__":
    run_as_script(run)
