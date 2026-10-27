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
        "fee_change",
        "fee_increase",
        "title_change",
        "notice_withdrawn",
        "effective_date_shift",
        "view_count_grow",
    ],
)
def test_expected_scenarios_exist(name: str) -> None:
    assert name in BY_NAME


@pytest.mark.parametrize("name", ["baseline", "no_change"])
def test_baseline_scenarios_match_defaults(name: str) -> None:
    assert _document(_build(name)) == _document(DEFAULT_STATE)


def test_fee_change_moves_only_the_current_fee() -> None:
    state = _build("fee_change")
    assert state.business.notice.current_fee == Decimal("96.00")
    assert state.business.notice.previous_fee == DEFAULT_STATE.business.notice.previous_fee
    assert state.business.notice.body == DEFAULT_STATE.business.notice.body


def test_title_change_moves_only_the_title() -> None:
    state = _build("title_change")
    assert state.business.notice.title.endswith("补充通知")
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee
    assert state.business.notice.published_at == DEFAULT_STATE.business.notice.published_at
    assert state.business.notice.body == DEFAULT_STATE.business.notice.body


def test_fee_increase_moves_only_the_current_fee() -> None:
    state = _build("fee_increase")
    assert state.business.notice.current_fee == Decimal("158.00")
    assert state.business.notice.previous_fee == DEFAULT_STATE.business.notice.previous_fee


def test_notice_withdrawn_moves_only_the_status() -> None:
    state = _build("notice_withdrawn")
    assert state.business.notice.status == "withdrawn"
    # Fee and body must be untouched: this is a data scenario, not a shape one.
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee
    assert state.business.notice.body == DEFAULT_STATE.business.notice.body


def test_effective_date_shift_moves_only_that_date() -> None:
    state = _build("effective_date_shift")
    assert state.business.notice.effective_date == "2026-12-01"
    assert state.business.notice.published_at == DEFAULT_STATE.business.notice.published_at
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee


def test_view_count_grow_moves_only_the_counter() -> None:
    """The counter is page chrome a collector must not read as content."""
    state = _build("view_count_grow")
    assert state.business.notice.view_count == 1531
    assert state.business.notice.body == DEFAULT_STATE.business.notice.body
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee
    assert state.business.notice.published_at == DEFAULT_STATE.business.notice.published_at


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_scenarios_are_deterministic(name: str) -> None:
    assert _document(_build(name)) == _document(_build(name))


def test_baseline_restores_defaults_after_another_scenario() -> None:
    assert _build("fee_change").business != DEFAULT_STATE.business
    assert _build("baseline").business == DEFAULT_STATE.business


def test_build_carries_the_given_revision() -> None:
    assert _build("fee_change").revision == 0
    assert BY_NAME["fee_change"].build(revision=42).revision == 42


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_scenario_metadata_is_present(name: str) -> None:
    scenario: PresetScenario = BY_NAME[name]
    assert scenario.description
    assert scenario.affects
    assert scenario.pages
    assert all(page.startswith("/") for page in scenario.pages)


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_scenario_copy_is_chinese(name: str) -> None:
    """The admin UI renders server-authored copy; it must not fall back to English."""
    scenario: PresetScenario = BY_NAME[name]
    assert scenario.title
    assert scenario.outcome
    assert scenario.data_impact
    for text in (scenario.title, scenario.outcome, scenario.data_impact, scenario.description):
        assert any("\u4e00" <= char <= "\u9fff" for char in text), text


def test_scenario_builds_are_immutable_snapshots() -> None:
    """Presets may reuse the shared default objects, but nothing can mutate them."""
    first = _build("fee_change")
    with pytest.raises(ValidationError):
        first.business.notice.current_fee = Decimal("1.00")  # type: ignore[misc]
    assert _build("fee_change").business.notice.current_fee == Decimal("96.00")
