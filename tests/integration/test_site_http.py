"""Site listener contract: headers, revisions, rendering, fault isolation."""

from __future__ import annotations

import asyncio
import time

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


@pytest.mark.parametrize("path", ["/static/product", "/ssr/product"])
async def test_product_pages_expose_contract_selectors(stack: Stack, path: str) -> None:
    response = await stack.site.get(path)
    assert response.status_code == 200
    body = response.text
    assert 'id="product"' in body
    assert 'id="current-price">128.50<' in body
    assert 'id="original-price">199.00<' in body
    assert 'id="currency">USD<' in body
    assert response.headers["x-mocksite-revision"] == "0"
    assert response.headers["cache-control"] == "no-store"


async def test_static_page_is_pre_rendered_and_updates_with_state(stack: Stack) -> None:
    await _set(stack, {"business": {"product": {"current_price": "96.00"}}})
    static = await stack.site.get("/static/product")
    assert "96.00" in static.text
    assert static.headers["x-mocksite-revision"] == "1"


async def test_ssr_page_reflects_current_state(stack: Stack) -> None:
    await _set(stack, {"business": {"product": {"name": "Renamed Coffee"}}})
    response = await stack.site.get("/ssr/product")
    assert "Renamed Coffee" in response.text


async def test_presentation_section_is_rejected(stack: Stack) -> None:
    """Structural breakage is out of scope: the section no longer exists."""
    response = await stack.admin.patch(
        "/_admin/state", json={"presentation": {"product_price": "missing"}}, headers=AUTH
    )
    assert response.status_code == 400
    assert (await stack.site.get("/ssr/product")).status_code == 200


async def test_page_structure_is_identical_across_data_scenarios(stack: Stack) -> None:
    """Every scenario must keep the same DOM skeleton; only values move."""
    markers = ('id="current-price"', 'id="rating-value"', "gallery-image", "reviews-list")
    seen: dict[str, list[str]] = {}
    for name in ("baseline", "price_change", "stock_out", "rating_change", "reviews_empty"):
        await stack.admin.post(f"/_admin/scenario/{name}", headers=AUTH)
        body = (await stack.site.get("/ssr/product")).text
        seen[name] = [marker for marker in markers if marker in body]
    baseline = seen["baseline"]
    assert all(present == baseline for present in seen.values()), seen


async def test_api_data_matches_state(stack: Stack) -> None:
    response = await stack.site.get("/api/data")
    payload = response.json()
    assert payload["revision"] == 0
    assert payload["page_size"] == 2
    assert payload["page_count"] == 2
    assert [row["id"] for row in payload["items"]] == ["A", "B", "C"]
    assert payload["items"][0]["price"] == "10.00"
    assert payload["product"]["current_price"] == "128.50"


async def test_prices_are_json_strings_never_numbers(stack: Stack) -> None:
    payload = (await stack.site.get("/api/data")).json()
    assert isinstance(payload["product"]["current_price"], str)
    assert isinstance(payload["items"][0]["price"], str)


async def test_outage_fails_business_routes_but_not_health(stack: Stack) -> None:
    await _set(stack, {"faults": {"kind": "outage"}})
    for path in ("/static/product", "/ssr/product", "/api/data"):
        response = await stack.site.get(path)
        assert response.status_code == 500, path
        assert response.headers["cache-control"] == "no-store"
    assert (await stack.site.get("/health")).status_code == 200


async def test_outage_does_not_affect_admin(stack: Stack) -> None:
    await _set(stack, {"faults": {"kind": "outage"}})
    assert (await stack.admin.get("/_admin/state", headers=AUTH)).status_code == 200


async def test_recovery_after_outage_restores_pages(stack: Stack) -> None:
    await _set(stack, {"faults": {"kind": "outage"}})
    assert (await stack.site.get("/ssr/product")).status_code == 500
    await stack.admin.post("/_admin/scenario/baseline", headers=AUTH)
    assert (await stack.site.get("/ssr/product")).status_code == 200


async def test_delay_is_applied_to_business_routes(stack: Stack) -> None:
    await _set(stack, {"faults": {"delay_ms": 300}})
    started = time.monotonic()
    response = await stack.site.get("/api/data")
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert elapsed >= 0.28


async def test_delay_does_not_affect_health_or_admin(stack: Stack) -> None:
    await _set(stack, {"faults": {"delay_ms": 2000}})
    started = time.monotonic()
    assert (await stack.site.get("/health")).status_code == 200
    assert (await stack.admin.get("/_admin/state", headers=AUTH)).status_code == 200
    assert time.monotonic() - started < 1.0


async def test_outage_takes_precedence_over_delay(stack: Stack) -> None:
    await _set(stack, {"faults": {"kind": "outage", "delay_ms": 2000}})
    started = time.monotonic()
    assert (await stack.site.get("/api/data")).status_code == 500
    assert time.monotonic() - started < 1.0


async def test_revision_advances_with_each_write(stack: Stack) -> None:
    for expected in (1, 2, 3):
        await _set(stack, {"business": {"page_size": expected + 1}})
        response = await stack.site.get("/api/data")
        assert response.headers["x-mocksite-revision"] == str(expected)


async def test_empty_list_is_distinguishable_from_failure(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/empty_list", headers=AUTH)
    response = await stack.site.get("/api/data")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["page_count"] == 0


async def test_html_is_escaped(stack: Stack) -> None:
    await _set(stack, {"business": {"product": {"name": "<script>x</script>"}}})
    body = (await stack.site.get("/ssr/product")).text
    assert "<script>x</script>" not in body
    assert "&lt;script&gt;" in body


async def test_duplicate_rows_survive_round_trip(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/duplicate_rows", headers=AUTH)
    rows = (await stack.site.get("/api/data")).json()["items"]
    assert [row["id"] for row in rows] == ["A", "B", "C", "A"]


async def test_concurrent_reads_see_one_revision(stack: Stack) -> None:
    await _set(stack, {"business": {"page_size": 3}})

    async def read() -> tuple[str, str]:
        response = await stack.site.get("/api/data")
        return response.headers["x-mocksite-revision"], str(response.json()["revision"])

    results = await asyncio.gather(*(read() for _ in range(20)))
    assert len(set(results)) == 1


@pytest.mark.parametrize("path", ["/react/list", "/vue/list", "/dynamic/deals"])
async def test_list_pages_are_served_without_rows(stack: Stack, path: str) -> None:
    response = await stack.site.get(path)
    assert response.status_code == 200
    assert response.headers["x-mocksite-revision"] == "0"
    assert response.headers["cache-control"] == "no-store"
    # Rows arrive from the browser; the shell must not fake them.
    assert "Alpha" not in response.text


@pytest.mark.parametrize("path", ["/static/assets/list.js", "/static/vendor/vue-3.5.43.min.js"])
async def test_assets_are_served_and_survive_outage(stack: Stack, path: str) -> None:
    await _set(stack, {"faults": {"kind": "outage"}})
    response = await stack.site.get(path)
    assert response.status_code == 200, path


async def test_assets_are_not_business_pages(stack: Stack) -> None:
    """/static/product is a page and must fail during an outage; assets must not."""
    await _set(stack, {"faults": {"kind": "outage"}})
    assert (await stack.site.get("/static/product")).status_code == 500
    assert (await stack.site.get("/static/assets/deals.js")).status_code == 200


async def test_list_pages_expose_revision_for_csrf_free_checks(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/pagination_grow", headers=AUTH)
    response = await stack.site.get("/dynamic/deals")
    assert response.headers["x-mocksite-revision"] == "1"
