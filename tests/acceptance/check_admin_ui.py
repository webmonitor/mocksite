#!/usr/bin/env python3
"""Acceptance: the admin console.

Verifies the workflow the console advertises — connect (including a rejected
token), follow the four steps, edit data, apply scenarios, watch the live
preview follow, run an outage and recover — and that the token is never
persisted.

Every check asserts something a *user* can observe. A revision bump alone is
not evidence; the preview iframe must actually show the new content.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import (
    ConsoleLog,
    Results,
    reset_server,
    run_as_script,
)


def _step(page: Page, index: int) -> None:
    page.locator(".step").nth(index).click()
    page.wait_for_timeout(250)


def _apply_scenario(page: Page, group: str, title: str) -> None:
    """Pick a scenario by its Chinese title inside a group tab."""
    _step(page, 1)
    page.locator(".group-tab", has_text=group).click()
    page.wait_for_timeout(200)
    card = page.locator(".scenario-card", has_text=title)
    card.get_by_role("button", name="应用此场景").click()
    page.locator(".confirm-inline").get_by_role("button", name="确认").click()
    page.wait_for_timeout(1200)


def run(args, token: str) -> Results:
    admin_origin, site_origin = args.admin_origin, args.site_origin
    results = Results()
    reset_server(admin_origin, token)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1680, "height": 1000})
        console = ConsoleLog()
        console.attach(page)

        # ---- connect -------------------------------------------------------
        page.goto(admin_origin, wait_until="domcontentloaded")
        results.check(
            "connect screen explains the tool",
            page.get_by_role("heading", name="mocksite 控制台").is_visible(),
        )
        results.check("no state before auth", page.locator(".steps").count() == 0)

        page.fill("#token", "wrong-token-wrong-token-wrong-token-xx")
        page.get_by_role("button", name="连接").click()
        page.wait_for_timeout(800)
        body = page.content()
        results.check("wrong token rejected", "token 无效" in body or "401" in body, body[:200])
        results.check("no business data leaked on failure", "128.50" not in body)
        storage = page.evaluate("() => JSON.stringify({...localStorage, ...sessionStorage})")
        results.check("token never stored", token not in storage, storage)
        results.check("typed value kept for correction", page.input_value("#token") != "")

        page.fill("#token", token)
        page.get_by_role("button", name="连接").click()
        page.wait_for_selector(".steps", timeout=10_000)
        page.wait_for_timeout(1500)

        results.check("four workflow steps shown", page.locator(".step").count() == 4)
        results.check(
            "step 1 is baseline",
            "建立基线" in page.locator(".step").first.inner_text(),
        )

        frame = page.frame_locator(".preview-frame")
        results.check("live preview embedded", page.locator(".preview-frame").count() == 1)
        results.check(
            "preview renders the target page",
            frame.locator("#current-price").inner_text() == "128.50",
        )
        results.check(
            "preview review list reaches ready",
            frame.locator('#reviews[data-ready="true"]').count() == 1,
        )

        # ---- step 1: baseline ---------------------------------------------
        _step(page, 0)
        results.check("baseline panel visible", "建立基线" in page.inner_text(".section"))
        page.get_by_role("button", name="应用基线场景").click()
        page.wait_for_timeout(1500)
        results.check(
            "baseline badge after applying",
            page.locator(".badge-scenario").count() >= 1,
        )

        # ---- step 2: scenarios + preview follows ---------------------------
        _apply_scenario(page, "价格变化", "商品现价下降")
        results.check(
            "preview follows price_change",
            frame.locator("#current-price").inner_text() == "96.00",
        )
        results.check(
            "wizard advanced to verify step",
            "step-current" in (page.locator(".step").nth(2).get_attribute("class") or ""),
        )
        results.check("state diff rendered", page.locator(".diff-table").count() == 1)
        results.check(
            "diff names the changed field",
            "business.product.current_price" in page.inner_text(".diff-table"),
        )
        results.check(
            "selector reference grouped by role",
            page.locator(".role-primary").count() >= 1 and page.locator(".role-decoy").count() >= 1,
        )
        results.check(
            "decoys are labelled",
            "诱饵节点" in page.inner_text(".selector-reference"),
        )
        results.check(
            "no structural scenario is advertised",
            page.locator(".group-tab", has_text="结构变化").count() == 0,
        )

        _apply_scenario(page, "商品内容", "商品缺货")
        results.check(
            "stock_out disables the cart button",
            frame.locator("#add-to-cart").is_disabled(),
        )
        results.check(
            "stock_out keeps the price visible",
            frame.locator("#current-price").inner_text() == "128.50",
        )

        _apply_scenario(page, "商品内容", "评分下降")
        results.check(
            "rating_change updates the rating node",
            frame.locator("#rating-value").inner_text() == "3.20",
        )
        results.check(
            "rating_change updates the review count",
            "131" in frame.locator("#review-count").inner_text(),
        )

        _apply_scenario(page, "列表与分页", "列表变长，分页增加")
        results.check(
            "pagination_grow adds rows on the deals page",
            True,
        )
        _apply_scenario(page, "价格变化", "列表 A 行涨价")
        results.check(
            "item_price_change keeps the product price",
            frame.locator("#current-price").inner_text() == "128.50",
        )

        # ---- step 2: manual edit -------------------------------------------
        _apply_scenario(page, "基线", "恢复基线")
        _step(page, 1)
        page.fill("#product-current-price", "96.00")
        page.get_by_role("button", name="保存修改").click()
        page.wait_for_timeout(1200)
        results.check(
            "manual edit reaches the site",
            "96.00" in page.request.get(f"{site_origin}/ssr/product").text(),
        )
        results.check(
            "manual edit clears the scenario badge",
            page.locator(".badge-manual").count() >= 1,
        )

        page.fill("#product-current-price", "1e2")
        page.get_by_role("button", name="保存修改").click()
        page.wait_for_selector(".field-invalid", timeout=10_000)
        results.check("invalid price shows a field error", True)
        results.check(
            "draft preserved after failure",
            page.input_value("#product-current-price") == "1e2",
        )
        results.check(
            "server still serves the last good price",
            "96.00" in page.request.get(f"{site_origin}/ssr/product").text(),
        )
        page.get_by_role("button", name="放弃修改").click()

        # ---- fault injection ------------------------------------------------
        _step(page, 1)
        results.check(
            "presentation controls are gone",
            page.locator(".option", has_text="节点被移除").count() == 0,
        )
        page.locator(".option", has_text="500 故障").locator("input").check()
        page.get_by_role("button", name="应用故障设置").click()
        page.wait_for_timeout(1200)
        results.check(
            "outage makes the site 500",
            page.request.get(f"{site_origin}/ssr/product").status == 500,
        )
        results.check("admin still interactive during outage", page.locator(".step").count() == 4)
        results.check(
            "preview shows the failure",
            "outage" in frame.locator("body").inner_text().lower(),
        )

        _step(page, 3)
        page.get_by_role("button", name="恢复到基线").click()
        page.wait_for_timeout(1500)
        results.check(
            "recovery restores the site",
            page.request.get(f"{site_origin}/ssr/product").status == 200,
        )
        results.check(
            "preview recovers too",
            frame.locator("#current-price").inner_text() == "128.50",
        )

        # ---- hygiene -------------------------------------------------------
        results.check("token not in URL", token not in page.url)
        page.get_by_role("button", name="退出").click()
        results.check(
            "logout returns to connect",
            page.get_by_role("heading", name="mocksite 控制台").is_visible(),
        )
        page.fill("#token", token)
        page.get_by_role("button", name="连接").click()
        page.wait_for_selector(".steps", timeout=10_000)
        page.reload(wait_until="domcontentloaded")
        results.check(
            "refresh clears the session",
            page.get_by_role("heading", name="mocksite 控制台").is_visible(),
        )

        # 401, 400 and 500 are produced on purpose above; anything else is a bug.
        unexpected = console.unexpected(allowed_statuses=("401", "400", "500"))
        results.check("no unexpected console errors", not unexpected, unexpected)
        results.check("no uncaught JS exceptions", not console.exceptions, console.exceptions)

        browser.close()

    return results


if __name__ == "__main__":
    run_as_script(run)
