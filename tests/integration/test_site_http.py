"""Site listener contract: headers, revisions, rendering, fault isolation."""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.harness import AUTH, Stack

pytestmark = pytest.mark.asyncio


async def _set(stack: Stack, payload: dict) -> None:
    response = await stack.admin.patch("/_admin/state", json=payload, headers=AUTH)
    assert response.status_code == 200, response.text


async def test_health_is_plain_and_uncached(stack: Stack) -> None:
    response = await stack.site.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/static/notice", "/ssr/notice"])
async def test_notice_pages_expose_contract_selectors(stack: Stack, path: str) -> None:
    response = await stack.site.get(path)
    assert response.status_code == 200
    body = response.text
    assert 'id="notice"' in body
    assert 'id="current-fee">128.50<' in body
    assert 'id="previous-fee">199.00<' in body
    assert 'id="currency">CNY<' in body
    assert 'id="effective-date">2026-11-01<' in body
    # The same publication instant appears in three renderings, none of which
    # is the execution date.
    assert "2026年10月20日" in body
    assert 'id="published-at">2026-10-20 14:32<' in body
    assert response.headers["x-mocksite-revision"] == "0"
    assert response.headers["cache-control"] == "no-store"


async def test_static_page_is_pre_rendered_and_updates_with_state(stack: Stack) -> None:
    await _set(stack, {"business": {"notice": {"current_fee": "96.00"}}})
    static = await stack.site.get("/static/notice")
    assert "96.00" in static.text
    assert static.headers["x-mocksite-revision"] == "1"


async def test_ssr_page_reflects_current_state(stack: Stack) -> None:
    await _set(stack, {"business": {"notice": {"title": "关于调整夜间停车收费标准的公告"}}})
    response = await stack.site.get("/ssr/notice")
    assert "关于调整夜间停车收费标准的公告" in response.text


async def test_static_page_is_not_rerendered_per_request(stack: Stack) -> None:
    """The pre-rendered page is a snapshot: only a commit may change it."""
    first = (await stack.site.get("/static/notice")).text
    second = (await stack.site.get("/static/notice")).text
    assert first == second


async def test_presentation_section_is_rejected(stack: Stack) -> None:
    """Structural breakage is out of scope: the section no longer exists."""
    response = await stack.admin.patch(
        "/_admin/state", json={"presentation": {"notice_fee": "missing"}}, headers=AUTH
    )
    assert response.status_code == 400
    assert (await stack.site.get("/ssr/notice")).status_code == 200


async def test_page_structure_is_identical_across_data_scenarios(stack: Stack) -> None:
    """Every scenario must keep the same DOM skeleton; only values move."""
    markers = ('id="current-fee"', 'id="effective-date"', "notice-body", "attachments")
    seen: dict[str, list[str]] = {}
    for name in ("baseline", "fee_change", "notice_withdrawn", "effective_date_shift", "title_change"):
        await stack.admin.post(f"/_admin/scenario/{name}", headers=AUTH)
        body = (await stack.site.get("/ssr/notice")).text
        seen[name] = [marker for marker in markers if marker in body]
    baseline = seen["baseline"]
    assert all(present == baseline for present in seen.values()), seen


async def test_prices_are_rendered_with_two_decimals(stack: Stack) -> None:
    body = (await stack.site.get("/ssr/notice")).text
    assert 'id="current-fee">128.50<' in body
    assert 'id="previous-fee">199.00<' in body


async def test_no_fault_injection_remains(stack: Stack) -> None:
    """A stale client sending `faults` must get a clear 400, not a silent no-op."""
    response = await stack.admin.patch(
        "/_admin/state", json={"faults": {"kind": "outage"}}, headers=AUTH
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["loc"] == "faults"
    # Every business route keeps answering normally.
    for path in ("/static/notice", "/ssr/notice", "/api/views"):
        assert (await stack.site.get(path)).status_code == 200, path


async def test_revision_advances_with_each_write(stack: Stack) -> None:
    for expected in (1, 2, 3):
        await _set(stack, {"business": {"notice": {"view_count": expected}}})
        response = await stack.site.get("/api/views")
        assert response.headers["x-mocksite-revision"] == str(expected)
        assert response.json()["revision"] == expected


async def test_html_is_escaped(stack: Stack) -> None:
    await _set(stack, {"business": {"notice": {"title": "<script>x</script>"}}})
    body = (await stack.site.get("/ssr/notice")).text
    assert "<script>x</script>" not in body
    assert "&lt;script&gt;" in body


async def test_concurrent_reads_see_one_revision(stack: Stack) -> None:
    await _set(stack, {"business": {"notice": {"view_count": 42}}})

    async def read() -> tuple[str, str]:
        response = await stack.site.get("/api/views")
        return response.headers["x-mocksite-revision"], str(response.json()["revision"])

    results = await asyncio.gather(*(read() for _ in range(20)))
    assert len(set(results)) == 1


@pytest.mark.parametrize(
    "path",
    ["/react/list", "/vue/list", "/dynamic/archive", "/api/data", "/static/shared/list.js"],
)
async def test_removed_list_routes_are_gone(stack: Stack, path: str) -> None:
    """The site is one notice; the list pages and their assets no longer exist."""
    assert (await stack.site.get(path)).status_code == 404, path


async def test_view_count_is_empty_in_the_static_html(stack: Stack) -> None:
    """`#view-count` is filled by the page script, exactly like the portal."""
    body = (await stack.site.get("/static/notice")).text
    assert '<span id="view-count" data-loaded="false"></span>' in body
    assert ">128<" not in body
