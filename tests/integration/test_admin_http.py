"""Admin listener contract: auth, media type, body limits, revisions, logging."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from mocksite.state.models import DEFAULT_NOTICE
from tests.integration.harness import AUTH, TOKEN, Stack

pytestmark = pytest.mark.asyncio

MAX_BODY = 64 * 1024


async def test_state_requires_bearer_token(stack: Stack) -> None:
    response = await stack.admin.get("/_admin/state")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert "business" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer wrong-token-wrong-token-wrong-token-xx",
        f"Basic {TOKEN}",
        f"Bearer {TOKEN}x",
    ],
)
async def test_wrong_credentials_rejected(stack: Stack, header: str) -> None:
    headers = {"Authorization": header} if header else {}
    response = await stack.admin.get("/_admin/state", headers=headers)
    assert response.status_code == 401


async def test_token_is_accepted_verbatim(stack: Stack) -> None:
    response = await stack.admin.get("/_admin/state", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


async def test_state_document_shape(stack: Stack) -> None:
    payload = (await stack.admin.get("/_admin/state", headers=AUTH)).json()
    assert set(payload) == {"revision", "business"}
    assert payload["revision"] == 0
    assert payload["business"]["notice"]["current_fee"] == "128.50"
    assert set(payload["business"]) == {"notice"}


async def test_patch_returns_full_state_and_bumps_revision(stack: Stack) -> None:
    response = await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"title": "演示公告"}}}, headers=AUTH
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"] == 1
    assert payload["business"]["notice"]["title"] == "演示公告"
    assert payload["business"]["notice"]["current_fee"] == "128.50"


async def test_patch_rejects_null_with_location(stack: Stack) -> None:
    response = await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"title": None}}}, headers=AUTH
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_state"
    assert response.json()["errors"][0]["loc"] == "business.notice.title"


async def test_patch_rejects_unknown_keys(stack: Stack) -> None:
    response = await stack.admin.patch("/_admin/state", json={"nope": {}}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["errors"][0]["loc"] == "nope"


async def test_patch_rejects_revision(stack: Stack) -> None:
    response = await stack.admin.patch("/_admin/state", json={"revision": 9}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["errors"][0]["loc"] == "revision"


async def test_invalid_patch_leaves_state_untouched(stack: Stack) -> None:
    await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"view_count": 7}}}, headers=AUTH
    )
    response = await stack.admin.patch(
        "/_admin/state",
        json={"business": {"notice": {"title": "kept?", "view_count": -1}}},
        headers=AUTH,
    )
    assert response.status_code == 400
    current = (await stack.admin.get("/_admin/state", headers=AUTH)).json()
    assert current["revision"] == 1
    assert current["business"]["notice"]["view_count"] == 7
    assert current["business"]["notice"]["title"] == DEFAULT_NOTICE.title


async def test_patch_requires_json_media_type(stack: Stack) -> None:
    response = await stack.admin.patch(
        "/_admin/state",
        content=b'{"business":{}}',
        headers={**AUTH, "Content-Type": "text/plain"},
    )
    assert response.status_code == 415


async def test_patch_rejects_malformed_json(stack: Stack) -> None:
    response = await stack.admin.patch(
        "/_admin/state",
        content=b"{not json",
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert response.status_code == 400


async def test_patch_rejects_empty_body(stack: Stack) -> None:
    response = await stack.admin.patch(
        "/_admin/state", content=b"", headers={**AUTH, "Content-Type": "application/json"}
    )
    assert response.status_code == 400


async def test_oversized_body_rejected(stack: Stack) -> None:
    padding = "x" * (MAX_BODY + 100)
    response = await stack.admin.patch(
        "/_admin/state",
        content=json.dumps({"business": {"notice": {"title": padding}}}).encode(),
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert response.status_code == 413


async def test_body_below_limit_is_accepted(stack: Stack) -> None:
    """A payload well under the cap must pass, so the limit is not off by a factor."""
    payload = json.dumps({"business": {"notice": {"title": "n" * 200}}}).encode()
    response = await stack.admin.patch(
        "/_admin/state", content=payload, headers={**AUTH, "Content-Type": "application/json"}
    )
    assert response.status_code == 200


async def test_reset_returns_before_and_after(stack: Stack) -> None:
    await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"current_fee": "1.00"}}}, headers=AUTH
    )
    response = await stack.admin.post("/_admin/reset", headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["before"]["revision"] == 1
    assert payload["after"]["revision"] == 2
    assert payload["before"]["business"]["notice"]["current_fee"] == "1.00"
    assert payload["after"]["business"]["notice"]["current_fee"] == "128.50"


async def test_reset_rejects_non_json_body(stack: Stack) -> None:
    response = await stack.admin.post(
        "/_admin/reset",
        content=b"x=1",
        headers={**AUTH, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


async def test_scenarios_list_exposes_metadata(stack: Stack) -> None:
    payload = (await stack.admin.get("/_admin/scenarios", headers=AUTH)).json()
    names = {scenario["name"] for scenario in payload["scenarios"]}
    assert {"baseline", "fee_change", "title_change"} <= names
    entry = next(s for s in payload["scenarios"] if s["name"] == "fee_change")
    assert entry["affects"] == ["business.notice.current_fee"]
    assert entry["description"]
    assert entry["pages"]


async def test_unknown_scenario_is_404(stack: Stack) -> None:
    response = await stack.admin.post("/_admin/scenario/nope", headers=AUTH)
    assert response.status_code == 404
    assert response.json() == {"error": "unknown_scenario"}


async def test_scenario_returns_before_and_after(stack: Stack) -> None:
    response = await stack.admin.post("/_admin/scenario/fee_change", headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["before"]["business"]["notice"]["current_fee"] == "128.50"
    assert payload["after"]["business"]["notice"]["current_fee"] == "96.00"
    assert payload["after"]["revision"] == payload["before"]["revision"] + 1


async def test_scenario_write_requires_auth(stack: Stack) -> None:
    response = await stack.admin.post("/_admin/scenario/fee_change")
    assert response.status_code == 401
    state = (await stack.admin.get("/_admin/state", headers=AUTH)).json()
    assert state["revision"] == 0


async def test_admin_writes_are_not_cacheable(stack: Stack) -> None:
    response = await stack.admin.patch("/_admin/state", json={}, headers=AUTH)
    assert response.headers["cache-control"] == "no-store"


async def test_admin_has_no_openapi_or_docs(stack: Stack) -> None:
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert (await stack.admin.get(path, headers=AUTH)).status_code == 404


async def test_missing_admin_build_is_reported(stack: Stack) -> None:
    response = await stack.admin.get("/")
    assert response.status_code == 503
    assert response.json()["error"] == "admin_build_missing"


async def test_site_listener_exposes_no_admin_routes(stack: Stack) -> None:
    for path in ("/_admin/state", "/_admin/scenarios", "/"):
        assert (await stack.site.get(path)).status_code == 404, path


async def test_admin_logs_never_contain_token_or_body(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="mocksite.admin")
    await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"title": "secret-body-value"}}}, headers=AUTH
    )
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "PATCH" in text
    assert "/_admin/state" in text
    assert TOKEN not in text
    assert "secret-body-value" not in text


async def test_unauthorized_requests_are_logged_without_secrets(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="mocksite.admin")
    await stack.admin.get("/_admin/state", headers={"Authorization": "Bearer leaked-token-value"})
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "leaked-token-value" not in text


async def test_admin_stays_available_after_a_data_change(stack: Stack) -> None:
    await stack.admin.patch(
        "/_admin/state", json={"business": {"notice": {"current_fee": "1.00"}}}, headers=AUTH
    )
    response = await stack.admin.get("/_admin/state", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["business"]["notice"]["current_fee"] == "1.00"


async def test_state_round_trips_through_json(stack: Stack) -> None:
    original = (await stack.admin.get("/_admin/state", headers=AUTH)).json()
    await stack.admin.patch(
        "/_admin/state",
        json={"business": original["business"]},
        headers=AUTH,
    )
    after = (await stack.admin.get("/_admin/state", headers=AUTH)).json()
    assert after["business"] == original["business"]


async def test_client_error_on_unknown_route_does_not_leak(stack: Stack) -> None:
    response = await stack.admin.get("/_admin/nope", headers=AUTH)
    assert response.status_code == 404


async def test_http_client_sees_revision_header_on_site(stack: Stack) -> None:
    async with httpx.AsyncClient(base_url=str(stack.site.base_url)) as client:
        response = await client.get("/api/views")
    assert response.headers["x-mocksite-revision"] == "0"
