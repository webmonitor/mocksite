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

from mocksite.state.models import (
    DEFAULT_BUSINESS,
    DEFAULT_STATE,
    MAX_ITEMS,
    BusinessData,
    Faults,
    Item,
    Product,
    State,
)

PRODUCT_DOC: dict[str, Any] = {
    "id": "coffee",
    "name": "Fixture Coffee",
    "brand": "Fixture Roasters",
    "sku": "FX-COF-1KG",
    "current_price": "128.50",
    "original_price": "199.00",
    "currency": "USD",
    "description": "A fixture product used by the model tests.",
}


def _product_doc(**overrides: Any) -> dict[str, Any]:
    return {**PRODUCT_DOC, **overrides}


def _items_doc(count: int) -> list[dict[str, Any]]:
    return [{"id": f"i{index}", "name": f"n{index}", "price": "1.00"} for index in range(count)]


def _business_doc(**overrides: Any) -> dict[str, Any]:
    return {**DEFAULT_BUSINESS.model_dump(mode="json"), **overrides}


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
def test_price_accepts_plain_decimal_strings(raw: str, expected: str) -> None:
    product = Product.model_validate(_product_doc(current_price=raw))
    assert isinstance(product.current_price, Decimal)
    assert str(product.current_price) == expected


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
def test_price_rejects_malformed_strings(raw: str) -> None:
    with pytest.raises(ValidationError):
        Product.model_validate(_product_doc(current_price=raw))


@pytest.mark.parametrize("raw", [12.5, 12, True, None, ["1.00"]])
def test_price_rejects_non_string_json_values(raw: Any) -> None:
    with pytest.raises(ValidationError):
        Product.model_validate(_product_doc(current_price=raw))


def test_price_accepts_decimal_for_in_process_builders() -> None:
    product = Product(
        id="coffee",
        name="Fixture Coffee",
        brand="Fixture Roasters",
        sku="FX-COF-1KG",
        current_price=Decimal("7.25"),
        original_price=Decimal("199.00"),
        currency="USD",
        description="A fixture product used by the model tests.",
    )
    assert product.current_price == Decimal("7.25")


@pytest.mark.parametrize("bad", [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")])
def test_decimal_prices_are_still_validated(bad: Decimal) -> None:
    with pytest.raises(ValidationError):
        Product(
            id="coffee",
            name="Fixture Coffee",
            current_price=bad,
            original_price=Decimal(1),
            currency="USD",
        )


def test_price_is_serialized_as_string() -> None:
    dumped = Product.model_validate(PRODUCT_DOC).model_dump(mode="json")
    assert dumped["current_price"] == "128.50"
    assert isinstance(dumped["current_price"], str)


@pytest.mark.parametrize("size", [1, 2, 100])
def test_page_size_bounds_accepted(size: int) -> None:
    assert BusinessData.model_validate(_business_doc(page_size=size)).page_size == size


@pytest.mark.parametrize("size", [0, 101, -1, True, "2", 2.0])
def test_page_size_bounds_rejected(size: Any) -> None:
    with pytest.raises(ValidationError):
        BusinessData.model_validate(_business_doc(page_size=size))


def test_page_count_is_derived() -> None:
    assert DEFAULT_BUSINESS.page_count == 2  # 3 rows, page size 2
    assert BusinessData.model_validate(_business_doc(items=[])).page_count == 0
    assert BusinessData.model_validate(_business_doc(page_size=100)).page_count == 1


def test_items_upper_bound() -> None:
    BusinessData.model_validate(_business_doc(items=_items_doc(MAX_ITEMS)))
    with pytest.raises(ValidationError):
        BusinessData.model_validate(_business_doc(items=_items_doc(MAX_ITEMS + 1)))


def test_empty_items_allowed() -> None:
    assert BusinessData.model_validate(_business_doc(items=[])).items == ()


@pytest.mark.parametrize("bad", ["", "x" * 257])
def test_text_length_bounds(bad: str) -> None:
    with pytest.raises(ValidationError):
        Item.model_validate({"id": "A", "name": bad, "price": "1.00"})


@pytest.mark.parametrize("bad", ["usd", "US", "USDD", "U5D", ""])
def test_currency_must_be_three_upper_case_letters(bad: str) -> None:
    with pytest.raises(ValidationError):
        Product.model_validate(_product_doc(currency=bad))


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        Product.model_validate(_product_doc(extra=1))


def test_state_is_immutable() -> None:
    state = State(business=DEFAULT_BUSINESS)
    with pytest.raises(ValidationError):
        state.revision = 5  # type: ignore[misc]


def test_state_copy_updates_only_requested_field() -> None:
    state = State(business=DEFAULT_BUSINESS)
    bumped = state.model_copy(update={"revision": 9})
    assert bumped.revision == 9
    assert bumped.business is state.business


@pytest.mark.parametrize("delay", [0, 8000, 30_000])
def test_fault_delay_bounds_accepted(delay: int) -> None:
    assert Faults(delay_ms=delay).delay_ms == delay


@pytest.mark.parametrize("delay", [-1, 30_001, True])
def test_fault_delay_bounds_rejected(delay: Any) -> None:
    with pytest.raises(ValidationError):
        Faults.model_validate({"delay_ms": delay})


def test_state_rejects_a_presentation_section() -> None:
    """`presentation` was removed on purpose: page shape is fixed."""
    document = DEFAULT_STATE.model_dump(mode="json")
    document["presentation"] = {"product_price": "missing"}
    with pytest.raises(ValidationError):
        State.model_validate(document)


def test_state_json_round_trip_is_stable() -> None:
    state = State(business=DEFAULT_BUSINESS, faults=Faults(kind="outage"))
    dumped = state.model_dump(mode="json")
    assert State.model_validate(dumped).model_dump(mode="json") == dumped
