"""Scenario registry: absolute states, one field of change, no stacking."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from mocksite.scenarios.registry import BY_NAME, SCENARIOS, PresetScenario
from mocksite.state.models import DEFAULT_STATE, State


def _document(state: State) -> dict[str, Any]:
    """State without the revision, which always moves."""
    return {key: value for key, value in state.model_dump(mode="json").items() if key != "revision"}


def _build(name: str) -> State:
    return BY_NAME[name].build(revision=0)


def test_every_scenario_is_registered_by_its_own_name() -> None:
    assert all(scenario.name == key for key, scenario in BY_NAME.items())


def test_every_scenario_builds_a_valid_state() -> None:
    for scenario in SCENARIOS:
        assert isinstance(scenario.build(revision=3), State)


def test_scenario_names_are_unique() -> None:
    names = [scenario.name for scenario in SCENARIOS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    "name",
    [
        "baseline",
        "no_change",
        "price_change",
        "price_increase",
        "item_price_change",
        "stock_out",
        "rating_change",
        "reviews_empty",
        "reviews_grow",
        "empty_list",
        "duplicate_rows",
        "pagination_grow",
        "outage",
        "slow_site",
    ],
)
def test_expected_scenarios_exist(name: str) -> None:
    assert name in BY_NAME


@pytest.mark.parametrize("name", ["baseline", "no_change"])
def test_baseline_scenarios_match_defaults(name: str) -> None:
    assert _document(_build(name)) == _document(DEFAULT_STATE)


def test_price_change_moves_only_the_product_price() -> None:
    state = _build("price_change")
    assert state.business.product.current_price == Decimal("96.00")
    assert state.business.product.original_price == DEFAULT_STATE.business.product.original_price
    assert state.business.items == DEFAULT_STATE.business.items
    assert state.faults == DEFAULT_STATE.faults


def test_item_price_change_moves_only_row_a() -> None:
    state = _build("item_price_change")
    prices = {row.id: row.price for row in state.business.items}
    assert prices["A"] == Decimal("12.50")
    assert prices["B"] == DEFAULT_STATE.business.items[1].price
    assert state.business.product == DEFAULT_STATE.business.product


def test_empty_list_keeps_product_and_page_size() -> None:
    state = _build("empty_list")
    assert state.business.items == ()
    assert state.business.product == DEFAULT_STATE.business.product
    assert state.business.page_size == 2


def test_duplicate_rows_repeat_row_a_at_the_end() -> None:
    state = _build("duplicate_rows")
    ids = [row.id for row in state.business.items]
    assert ids == ["A", "B", "C", "A"]
    assert state.business.items[-1] == state.business.items[0]


def test_pagination_grow_adds_two_rows_and_keeps_page_size() -> None:
    state = _build("pagination_grow")
    assert [row.id for row in state.business.items] == ["A", "B", "C", "D", "E"]
    assert state.business.page_size == 2
    assert state.business.page_count == 3


def test_price_increase_moves_only_the_product_price() -> None:
    state = _build("price_increase")
    assert state.business.product.current_price == Decimal("158.00")
    assert state.business.items == DEFAULT_STATE.business.items


def test_stock_out_moves_only_stock_fields() -> None:
    state = _build("stock_out")
    assert state.business.product.stock_status == "out_of_stock"
    assert state.business.product.stock_count == 0
    # Price and lists must be untouched: this is a data scenario, not a shape one.
    assert state.business.product.current_price == DEFAULT_STATE.business.product.current_price
    assert state.business.items == DEFAULT_STATE.business.items


def test_rating_change_moves_only_rating_fields() -> None:
    state = _build("rating_change")
    assert state.business.product.rating == Decimal("3.2")
    assert state.business.product.review_count == 131
    assert state.business.product.current_price == DEFAULT_STATE.business.product.current_price


def test_reviews_empty_clears_reviews_but_keeps_the_product() -> None:
    state = _build("reviews_empty")
    assert state.business.reviews == ()
    assert state.business.product == DEFAULT_STATE.business.product


def test_reviews_grow_appends_without_touching_the_product() -> None:
    state = _build("reviews_grow")
    assert len(state.business.reviews) == len(DEFAULT_STATE.business.reviews) + 2
    assert state.business.reviews[: len(DEFAULT_STATE.business.reviews)] == (
        DEFAULT_STATE.business.reviews
    )
    assert state.business.product == DEFAULT_STATE.business.product


def test_outage_sets_fault_only() -> None:
    state = _build("outage")
    assert state.faults.kind == "outage"
    assert state.faults.delay_ms == 0
    assert state.business == DEFAULT_STATE.business


def test_slow_site_sets_delay_only() -> None:
    state = _build("slow_site")
    assert state.faults.delay_ms == 8000
    assert state.faults.kind == "none"


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_scenarios_are_deterministic(name: str) -> None:
    assert _document(_build(name)) == _document(_build(name))


def test_baseline_clears_previous_faults() -> None:
    assert _build("outage").faults.kind == "outage"
    assert _build("baseline").faults.kind == "none"


def test_build_carries_the_given_revision() -> None:
    assert _build("price_change").revision == 0
    assert BY_NAME["price_change"].build(revision=42).revision == 42


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_scenario_metadata_is_present(name: str) -> None:
    scenario: PresetScenario = BY_NAME[name]
    assert scenario.description
    assert scenario.affects
    assert scenario.pages
    assert all(page.startswith("/") for page in scenario.pages)


def test_scenario_builds_are_immutable_snapshots() -> None:
    """Presets may reuse the shared default objects, but nothing can mutate them."""
    first = _build("duplicate_rows")
    with pytest.raises(ValidationError):
        first.business.items[0].price = Decimal("1.00")  # type: ignore[misc]
    assert _build("duplicate_rows").business.items == first.business.items
