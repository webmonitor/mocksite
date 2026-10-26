"""Reviews API and the product page over real HTTP."""

from __future__ import annotations

import pytest

from tests.integration.harness import AUTH, Stack

pytestmark = pytest.mark.asyncio


async def test_reviews_endpoint_pages_reviews(stack: Stack) -> None:
    first = (await stack.site.get("/api/reviews")).json()
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert first["total"] == 5
    assert first["page_count"] == 3
    assert [review["id"] for review in first["reviews"]] == ["rev-1", "rev-2"]

    last = (await stack.site.get("/api/reviews?page=3")).json()
    assert [review["id"] for review in last["reviews"]] == ["rev-5"]


async def test_reviews_endpoint_returns_empty_past_the_end(stack: Stack) -> None:
    response = await stack.site.get("/api/reviews?page=99")
    assert response.status_code == 200
    payload = response.json()
    assert payload["reviews"] == []
    assert payload["total"] == 5


async def test_reviews_endpoint_carries_revision_and_no_store(stack: Stack) -> None:
    response = await stack.site.get("/api/reviews")
    assert response.headers["x-mocksite-revision"] == "0"
    assert response.headers["cache-control"] == "no-store"


async def test_reviews_follow_the_applied_scenario(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/reviews_empty", headers=AUTH)
    payload = (await stack.site.get("/api/reviews")).json()
    assert payload["reviews"] == []
    assert payload["total"] == 0


async def test_data_endpoint_exposes_reviews_and_product_detail(stack: Stack) -> None:
    payload = (await stack.site.get("/api/data")).json()
    assert payload["review_page_count"] == 3
    assert len(payload["reviews"]) == 5
    product = payload["product"]
    assert product["brand"] == "Fixture Roasters"
    assert product["sku"] == "FX-COF-GUJI-1KG"
    assert product["stock_status"] == "in_stock"
    assert product["rating"] == "4.6"
    assert len(product["specs"]) == 7
    assert len(product["variants"]) == 7
    assert len(product["images"]) == 4


async def test_product_page_serves_local_assets_only(stack: Stack) -> None:
    """No CDN: every referenced asset is same-origin and reachable."""
    body = (await stack.site.get("/static/product")).text
    for path in (
        "/static/shared/shop.css",
        "/static/shared/product.js",
        "/static/shared/img/coffee-natural.svg",
    ):
        assert path in body
        response = await stack.site.get(path)
        assert response.status_code == 200, path
    assert "http://" not in body.replace("http://www.w3.org", "")
    assert "https://" not in body


async def test_outage_fails_the_page_but_not_the_health_check(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/outage", headers=AUTH)
    assert (await stack.site.get("/static/product")).status_code == 500
    assert (await stack.site.get("/api/reviews")).status_code == 500
    assert (await stack.site.get("/health")).status_code == 200
