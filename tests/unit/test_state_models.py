"""State model invariants: decimal strings, bounds, immutability.

Wire values are strings, so most assertions go through ``model_validate`` —
that is exactly the path the admin API uses. In-process builders pass
``Decimal`` directly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from mocksite.state.models import DEFAULT_BUSINESS, DEFAULT_STATE, BusinessData, Notice, State

NOTICE_DOC: dict[str, Any] = {
    "id": "notice-54493",
    "title": "关于调整校园停车收费标准的通知",
    "department": "后勤保障部",
    "doc_no": "校后保〔2026〕42 号",
    "category": "学校通知",
    "current_fee": "128.50",
    "previous_fee": "199.00",
    "currency": "CNY",
    "published_at": "2026-10-20 14:32",
    "effective_date": "2026-11-01",
    "body": ["用于模型测试的通知正文。"],
}


def _notice_doc(**overrides: Any) -> dict[str, Any]:
    return {**NOTICE_DOC, **overrides}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", "0"),
        ("128.50", "128.50"),
        ("000128.50", "128.50"),
        ("+12.5", "12.5"),
        ("9" * 64, "9" * 64),
    ],
)
def test_fee_accepts_plain_decimal_strings(raw: str, expected: str) -> None:
    notice = Notice.model_validate(_notice_doc(current_fee=raw))
    assert isinstance(notice.current_fee, Decimal)
    assert str(notice.current_fee) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "-1",
        "1e2",
        "1E2",
        "1.2.3",
        "12.",
        ".5",
        " 12",
        "12 ",
        "12,5",
        "Infinity",
        "NaN",
        "sNaN",
        "9" * 65,
    ],
)
def test_fee_rejects_malformed_strings(raw: str) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(current_fee=raw))


@pytest.mark.parametrize("raw", [12.5, 12, True, None, ["1.00"]])
def test_fee_rejects_non_string_json_values(raw: Any) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(current_fee=raw))


def test_fee_accepts_decimal_for_in_process_builders() -> None:
    notice = Notice.model_validate(_notice_doc(current_fee=Decimal("7.25")))
    assert notice.current_fee == Decimal("7.25")


@pytest.mark.parametrize("bad", [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")])
def test_decimal_fees_are_still_validated(bad: Decimal) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(current_fee=bad))


def test_fee_is_serialized_as_string() -> None:
    dumped = Notice.model_validate(NOTICE_DOC).model_dump(mode="json")
    assert dumped["current_fee"] == "128.50"
    assert isinstance(dumped["current_fee"], str)


@pytest.mark.parametrize("bad", ["2026-11", "2026/11/01", "20261101", ""])
def test_effective_date_must_be_iso(bad: str) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(effective_date=bad))


@pytest.mark.parametrize("bad", ["2026-10-20", "2026-10-20T14:32", "2026-10-20 14:32:05", ""])
def test_published_at_must_be_minute_precision(bad: str) -> None:
    """Portals emit `YYYY-MM-DD HH:MM`; RFC 3339 would not match the real pages."""
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(published_at=bad))


@pytest.mark.parametrize("bad", ["", "x" * 257])
def test_text_length_bounds(bad: str) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(title=bad))


@pytest.mark.parametrize("bad", [-1, 10_000_001, True, "12", 1.5])
def test_view_count_is_a_bounded_integer(bad: Any) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(view_count=bad))


def test_business_data_has_only_the_notice() -> None:
    """The site is one notice; a stale client sending list data must be rejected."""
    assert set(DEFAULT_BUSINESS.model_dump(mode="json")) == {"notice"}
    with pytest.raises(ValidationError):
        BusinessData.model_validate(
            {**DEFAULT_BUSINESS.model_dump(mode="json"), "entries": []}
        )


@pytest.mark.parametrize("bad", ["cny", "CN", "CNYY", "C5Y", ""])
def test_currency_must_be_three_upper_case_letters(bad: str) -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(currency=bad))


@pytest.mark.parametrize("status", ["published", "withdrawn"])
def test_every_notice_status_is_accepted(status: str) -> None:
    assert Notice.model_validate(_notice_doc(status=status)).status == status


def test_unknown_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(status="expired"))


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        Notice.model_validate(_notice_doc(extra=1))


def test_state_is_immutable() -> None:
    state = State(business=DEFAULT_BUSINESS)
    with pytest.raises(ValidationError):
        state.revision = 5  # type: ignore[misc]


def test_state_copy_updates_only_requested_field() -> None:
    state = State(business=DEFAULT_BUSINESS)
    bumped = state.model_copy(update={"revision": 9})
    assert bumped.revision == 9
    assert bumped.business is state.business


def test_state_rejects_a_presentation_section() -> None:
    """`presentation` was removed on purpose: page shape is fixed."""
    document = DEFAULT_STATE.model_dump(mode="json")
    document["presentation"] = {"notice_fee": "missing"}
    with pytest.raises(ValidationError):
        State.model_validate(document)


def test_state_rejects_a_faults_section() -> None:
    """Fault injection was removed: transport faults are not an input property."""
    document = DEFAULT_STATE.model_dump(mode="json")
    document["faults"] = {"kind": "outage"}
    with pytest.raises(ValidationError):
        State.model_validate(document)


def test_state_has_exactly_two_top_level_keys() -> None:
    assert set(DEFAULT_STATE.model_dump(mode="json")) == {"revision", "business"}


def test_state_json_round_trip_is_stable() -> None:
    state = State(business=DEFAULT_BUSINESS, revision=3)
    dumped = state.model_dump(mode="json")
    assert State.model_validate(dumped).model_dump(mode="json") == dumped
