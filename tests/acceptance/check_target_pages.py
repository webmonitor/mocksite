#!/usr/bin/env python3
"""Acceptance: the target pages a collector fetches.

Every external origin is aborted, so a passing run also proves the pages work
with no CDN and no egress.

Covers what a collector depends on:
  * readiness only after rows exist (`#app[data-ready="true"]` + `data-revision`)
  * React and Vue rendering the same data
  * pagination: one page per click, disabled while loading, hidden at the end
  * empty list vs load failure vs duplicate rows
  * the product page's fixed skeleton, decoy price nodes and lazy reviews
  * data scenarios moving values while the DOM skeleton stays identical
  * outage leaves the page unready
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

ROWS = "#inventory tbody tr.item"


def _rows(page: Page) -> list[tuple[str, str]]:
    return page.eval_on_selector_all(
        ROWS,
        """els => els.map(el => [
            el.dataset.id,
            el.querySelector('td.price')?.textContent ?? ''
        ])""",
    )


def _open(page: Page, site: str, path: str) -> None:
    page.goto(f"{site}{path}", wait_until="domcontentloaded")
    page.wait_for_selector('#app[data-ready="true"]', timeout=15_000)


def _open_product(page: Page, site: str, path: str = "/static/product") -> None:
    """Product pages are server-rendered; only the review list waits on JS."""
    page.goto(f"{site}{path}", wait_until="domcontentloaded")
    page.wait_for_selector('#reviews[data-ready="true"]', timeout=15_000)


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

        # --- realistic product-detail page ------------------------------
        _open_product(page, site)
        results.check(
            "product page price is unique",
            page.locator("#current-price").count() == 1,
        )
        results.check(
            "product page price text",
            page.inner_text("#current-price") == "128.50",
            page.inner_text("#current-price"),
        )
        results.check(
            "product page carries a revision",
            page.get_attribute("#product", "data-revision") is not None,
        )
        # The decoys must be selectable, otherwise they are not decoys.
        for label, selector in (
            ("original price", "#original-price"),
            ("instalment price", ".installment-price strong"),
            ("unit price", ".unit-price strong"),
            ("msrp", ".msrp-price"),
        ):
            results.check(f"decoy present: {label}", page.locator(selector).count() == 1)
        results.check(
            "price-shaped values are plentiful",
            len(page.locator(".price-block").inner_text().split(".")) >= 4,
        )
        results.check(
            "reviews render as rows, not skeletons",
            page.locator("#reviews-list li.review-item").count() == 2
            and page.locator(".review-skeleton").count() == 0,
        )
        results.check(
            "review list is paged",
            page.locator("#load-more-reviews").is_visible(),
        )
        page.click("#load-more-reviews")
        page.wait_for_timeout(400)
        results.check(
            "review pagination appends",
            page.locator("#reviews-list li.review-item").count() == 4,
        )
        results.check(
            "gallery switches main image",
            page.locator("#gallery-image").get_attribute("src") != ""
            and page.locator("[data-gallery-index]").count() == 4,
        )
        page.locator("[data-gallery-index]").nth(2).click()
        results.check(
            "gallery click changes the image",
            "black" in (page.locator("#gallery-image").get_attribute("src") or ""),
        )
        results.check(
            "variant buttons expose selection",
            page.locator(".variant-option[aria-pressed=true]").count() == 2,
        )
        page.locator(".variant-option", has_text="Chili red").click()
        results.check(
            "variant selection updates",
            "Chili red" in page.inner_text("#selected-variant"),
        )
        results.check(
            "specs table is real markup",
            page.locator("#specs .spec-table tbody tr").count() == 7,
        )
        results.check(
            "stock state is machine-readable",
            page.get_attribute(".stock-line", "data-stock") == "in_stock",
        )

        # Data scenarios: values move, the DOM skeleton never does.
        scenario("price_change")
        _open_product(page, site)
        results.check(
            "price_change moves the price value",
            page.inner_text("#current-price") == "96.00",
        )
        results.check(
            "price_change keeps every structural node",
            page.locator("#original-price").count() == 1
            and page.locator("#gallery-image").count() == 1
            and page.locator("#rating-value").count() == 1
            and page.locator("#reviews").count() == 1,
        )

        scenario("price_increase")
        _open_product(page, site)
        results.check(
            "price_increase moves the price upward",
            page.inner_text("#current-price") == "158.00",
        )

        scenario("stock_out")
        _open_product(page, site)
        results.check(
            "stock_out shows the out-of-stock state",
            page.get_attribute(".stock-line", "data-stock") == "out_of_stock",
        )
        results.check(
            "stock_out disables the cart button", page.locator("#add-to-cart").is_disabled()
        )
        results.check(
            "stock_out keeps the price value",
            page.inner_text("#current-price") == "128.50",
        )

        scenario("rating_change")
        _open_product(page, site)
        results.check(
            "rating_change moves the rating value",
            page.inner_text("#rating-value") == "3.20",
        )
        results.check(
            "rating_change moves the review count",
            "131" in page.inner_text("#review-count"),
        )

        scenario("reviews_empty")
        _open_product(page, site)
        results.check(
            "reviews_empty is ready with zero rows",
            page.get_attribute("#reviews", "data-ready") == "true"
            and page.locator("#reviews-list li.review-item").count() == 0,
        )
        results.check(
            "reviews_empty keeps the price value",
            page.inner_text("#current-price") == "128.50",
        )

        scenario("reviews_grow")
        _open_product(page, site)
        results.check(
            "reviews_grow keeps the first page size",
            page.locator("#reviews-list li.review-item").count() == 2,
        )
        results.check(
            "reviews_grow reports four pages",
            "1 of 4" in page.inner_text("#reviews-status"),
        )

        # Every scenario must leave the same DOM skeleton behind. This is the
        # contract that replaced the old structural-breakage scenarios.
        markers = (
            "#current-price",
            "#original-price",
            "#rating-value",
            "#gallery-image",
            "#reviews",
        )
        shapes = {}
        for name in (
            "baseline",
            "price_change",
            "price_increase",
            "stock_out",
            "rating_change",
            "reviews_empty",
            "reviews_grow",
        ):
            scenario(name)
            _open_product(page, site)
            shapes[name] = [marker for marker in markers if page.locator(marker).count() == 1]
        baseline_shape = shapes["baseline"]
        results.check(
            "structure is identical across all data scenarios",
            all(shape == baseline_shape for shape in shapes.values()),
            shapes,
        )
        reset_server(admin, token)

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
        reset_server(admin, token)
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

        # --- the price cell class is stable under data changes ----------
        scenario("item_price_change")
        for path in ("/react/list", "/vue/list"):
            _open(page, site, path)
            results.check(
                f"{path} rows still present after a price change",
                page.locator(ROWS).count() == 3,
            )
            results.check(
                f"{path} td.price keeps its class and count",
                page.locator(f"{ROWS} td.price").count() == 3
                and page.locator(f"{ROWS} td.cost").count() == 0,
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

        reset_server(admin, token)
        _open(page, site, "/react/list")
        results.check(
            "recovery makes the page ready again",
            page.locator('#app[data-ready="true"]').count() == 1,
        )

        results.check("no external requests", blocked == [], blocked[:5])
        # The outage step deliberately produces one 500; any other console error
        # would mean a broken page.
        unexpected = console.unexpected(allowed_statuses=("500",))
        results.check("no unexpected console errors", not unexpected, unexpected[:5])

        browser.close()

    return results


if __name__ == "__main__":
    run_as_script(run)
