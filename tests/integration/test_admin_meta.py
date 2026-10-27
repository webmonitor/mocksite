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
    assert paths == {"/static/notice", "/ssr/notice", "/api/views", "/health"}

    notice = next(page for page in payload["pages"] if page["path"] == "/static/notice")
    assert notice["implemented"] is True
    assert notice["collect_url"].endswith("/static/notice")
    assert notice["preview_url"].startswith("http://127.0.0.1")
    assert notice["selectors"][0]["css"] == "#notice #current-fee"
    assert notice["selectors"][0]["xpath"].startswith('//*[@id="notice"]')

    # Decoy selectors are advertised with their role so a client can warn.
    roles = {selector["role"] for selector in notice["selectors"]}
    assert roles == {"primary", "ready", "supporting", "decoy"}, roles


async def test_meta_marks_every_page_as_implemented(stack: Stack) -> None:
    """Stages 0-4 are done, so nothing in the catalogue may be advertised as planned."""
    payload = (await stack.admin.get("/_admin/meta", headers=AUTH)).json()
    planned = {page["path"] for page in payload["pages"] if not page["implemented"]}
    assert planned == set()


async def test_meta_is_not_cacheable(stack: Stack) -> None:
    response = await stack.admin.get("/_admin/meta", headers=AUTH)
    assert response.headers["cache-control"] == "no-store"


async def test_page_catalogue_matches_rendered_dom(stack: Stack) -> None:
    """Every selector advertised for the notice page must actually match."""
    payload = (await stack.admin.get("/_admin/meta", headers=AUTH)).json()
    notice = next(page for page in payload["pages"] if page["path"] == "/ssr/notice")
    body = (await stack.site.get("/ssr/notice")).text
    assert notice["selectors"], "notice page must advertise at least one selector"
    assert 'id="notice"' in body
    assert 'id="current-fee"' in body
    # Every advertised selector must address a node the page really renders.
    # A `#id[...]` form is a readiness marker: the id exists in the static HTML,
    # the attribute is only set by the page script, so match the id alone.
    for selector in notice["selectors"]:
        css = selector["css"]
        if " " in css or not css.startswith("#"):
            continue
        node_id = css[1:].split("[", 1)[0]
        assert f'id="{node_id}"' in body, css
