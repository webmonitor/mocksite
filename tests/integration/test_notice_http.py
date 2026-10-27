"""``/api/views``: the JSON side of the notice portal."""

from __future__ import annotations

import pytest

from tests.integration.harness import AUTH, Stack


@pytest.mark.asyncio
async def test_views_endpoint_serves_the_counter(stack: Stack) -> None:
    """The page script fetches this to fill #view-count, like `_showDynClicks`."""
    response = await stack.site.get("/api/views")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"views": 128, "revision": 0}
    assert response.headers["x-mocksite-revision"] == "0"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_views_endpoint_follows_the_scenario(stack: Stack) -> None:
    await stack.admin.post("/_admin/scenario/view_count_grow", headers=AUTH)
    payload = (await stack.site.get("/api/views")).json()
    assert payload["views"] == 1531
    assert payload["revision"] == 1


@pytest.mark.asyncio
async def test_views_endpoint_tracks_a_manual_edit(stack: Stack) -> None:
    await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"view_count": 9}}}, headers=AUTH
    )
    payload = (await stack.site.get("/api/views")).json()
    assert payload["views"] == 9


@pytest.mark.asyncio
async def test_views_endpoint_is_site_only(stack: Stack) -> None:
    response = await stack.admin.get("/api/views")
    assert response.status_code == 404
