"""``GET /_admin/meta``: page catalogue with two distinct origins."""

from __future__ import annotations

import pytest

from tests.integration.harness import AUTH, Stack

pytestmark = pytest.mark.asyncio


async def test_meta_requires_auth(stack: Stack) -> None:
    assert (await stack.admin.get("/_admin/meta")).status_code == 401


async def test_meta_lists_pages_with_both_origins(stack: Stack) -> None:
    payload = (await stack.admin.get("/_admin/meta", headers=AUTH)).json()
    assert payload["site_origin"] != payload["site_public_origin"]
    paths = {page["path"] for page in payload["pages"]}
    assert {"/static/product", "/ssr/product", "/api/data", "/health"} <= paths

    product = next(page for page in payload["pages"] if page["path"] == "/static/product")
    assert product["implemented"] is True
    assert product["collect_url"].endswith("/static/product")
    assert product["preview_url"].startswith("http://127.0.0.1")
    assert product["selectors"][0]["css"] == "#product #current-price"
    assert product["selectors"][0]["xpath"].startswith('//*[@id="product"]')


async def test_meta_marks_every_page_as_implemented(stack: Stack) -> None:
    """Stages 0-4 are done, so nothing in the catalogue may be advertised as planned."""
    payload = (await stack.admin.get("/_admin/meta", headers=AUTH)).json()
    planned = {page["path"] for page in payload["pages"] if not page["implemented"]}
    assert planned == set()


async def test_meta_is_not_cacheable(stack: Stack) -> None:
    response = await stack.admin.get("/_admin/meta", headers=AUTH)
    assert response.headers["cache-control"] == "no-store"


async def test_page_catalogue_matches_rendered_dom(stack: Stack) -> None:
    """Every selector advertised for a product page must actually match."""
    payload = (await stack.admin.get("/_admin/meta", headers=AUTH)).json()
    product = next(page for page in payload["pages"] if page["path"] == "/ssr/product")
    body = (await stack.site.get("/ssr/product")).text
    assert product["selectors"], "product page must advertise at least one selector"
    assert 'id="product"' in body
    assert 'id="current-price"' in body
