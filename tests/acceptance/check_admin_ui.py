#!/usr/bin/env python3
"""Acceptance: the admin console.

Verifies what the single-page console advertises — connect (including a
rejected token), apply a scenario, edit the notice, watch the live preview
follow, reset — and that the token is never persisted.

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


def _apply_scenario(page: Page, group: str, title: str) -> None:
    """Pick a scenario by its Chinese title inside a group tab."""
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
        results.check("no state before auth", page.locator(".workspace").count() == 0)

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
        page.wait_for_selector(".workspace", timeout=10_000)
        page.wait_for_timeout(1500)

        # ---- one page, no wizard ------------------------------------------
        results.check("no wizard step bar", page.locator(".step").count() == 0)
        results.check("scenario panel present", page.locator(".scenario-cards").count() == 1)
        results.check("editor present", page.locator("#notice-current-fee").count() == 1)
        results.check("no selector reference", page.locator(".selector-reference").count() == 0)
        results.check("no state diff panel", page.locator(".diff-table").count() == 0)
        results.check(
            "only notice pages are previewable",
            page.locator(".preview-tabs .tab").count() == 2,
        )

        frame = page.frame_locator(".preview-frame")
        results.check("live preview embedded", page.locator(".preview-frame").count() == 1)
        results.check(
            "preview renders the target page",
            frame.locator("#current-fee").inner_text() == "128.50",
        )
        results.check(
            "preview click counter is filled",
            frame.locator('#view-count[data-loaded="true"]').count() == 1,
        )

        # ---- scenarios drive the preview -----------------------------------
        _apply_scenario(page, "收费标准", "收费标准下调")
        results.check(
            "preview follows fee_change",
            frame.locator("#current-fee").inner_text() == "96.00",
        )
        results.check(
            "active scenario is badged",
            page.locator(".badge-scenario").count() >= 1,
        )
        results.check(
            "group tabs cover baseline, fee and content",
            page.locator(".group-tab").count() == 3,
        )
        results.check(
            "no list scenario is advertised",
            page.locator(".group-tab", has_text="列表与分页").count() == 0,
        )

        _apply_scenario(page, "通知内容", "通知撤回")
        results.check(
            "notice_withdrawn shows a banner",
            frame.locator("#withdrawn-banner").count() == 1,
        )
        results.check(
            "notice_withdrawn keeps the fee visible",
            frame.locator("#current-fee").inner_text() == "128.50",
        )

        _apply_scenario(page, "通知内容", "执行日期推迟")
        results.check(
            "effective_date_shift updates the effective date",
            frame.locator("#effective-date").inner_text() == "2026-12-01",
        )
        results.check(
            "effective_date_shift leaves the publication alone",
            frame.locator("#published-at").inner_text() == "2026-10-20 14:32",
        )

        # ---- manual edit ---------------------------------------------------
        _apply_scenario(page, "基线", "恢复基线")
        page.fill("#notice-current-fee", "96.00")
        page.get_by_role("button", name="保存修改").click()
        page.wait_for_timeout(1200)
        results.check(
            "manual edit reaches the site",
            "96.00" in page.request.get(f"{site_origin}/ssr/notice").text(),
        )
        results.check(
            "manual edit clears the scenario badge",
            page.locator(".badge-manual").count() >= 1,
        )

        page.fill("#notice-current-fee", "1e2")
        page.get_by_role("button", name="保存修改").click()
        page.wait_for_selector(".field-invalid", timeout=10_000)
        results.check("invalid fee shows a field error", True)
        results.check(
            "draft preserved after failure",
            page.input_value("#notice-current-fee") == "1e2",
        )
        results.check(
            "server still serves the last good fee",
            "96.00" in page.request.get(f"{site_origin}/ssr/notice").text(),
        )
        page.get_by_role("button", name="放弃修改").click()

        # ---- removed controls ----------------------------------------------
        results.check(
            "fault injection panel is gone",
            page.get_by_text("故障注入", exact=False).count() == 0,
        )
        results.check(
            "presentation controls are gone",
            page.locator(".option", has_text="节点被移除").count() == 0,
        )
        results.check(
            "list editor tab is gone",
            page.locator(".editor-tabs").count() == 0,
        )

        # ---- reset ---------------------------------------------------------
        page.get_by_role("button", name="恢复默认（reset）").click()
        page.wait_for_timeout(1500)
        results.check(
            "reset restores the site",
            "128.50" in page.request.get(f"{site_origin}/ssr/notice").text(),
        )
        results.check(
            "preview recovers too",
            frame.locator("#current-fee").inner_text() == "128.50",
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
        page.wait_for_selector(".workspace", timeout=10_000)
        page.reload(wait_until="domcontentloaded")
        results.check(
            "refresh clears the session",
            page.get_by_role("heading", name="mocksite 控制台").is_visible(),
        )

        # 401 and 400 are produced on purpose above; anything else is a bug.
        unexpected = console.unexpected(allowed_statuses=("401", "400"))
        results.check("no unexpected console errors", not unexpected, unexpected)
        results.check("no uncaught JS exceptions", not console.exceptions, console.exceptions)

        browser.close()

    return results


if __name__ == "__main__":
    run_as_script(run)
