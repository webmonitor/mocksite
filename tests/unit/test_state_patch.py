"""``PATCH`` semantics: recursive merge, wholesale arrays, no ``null``."""

from __future__ import annotations

from typing import Any

import pytest

from mocksite.state.errors import StateValidationError
from mocksite.state.models import DEFAULT_STATE, State
from mocksite.state.patch import apply_patch


def _patched(payload: Any) -> State:
    return apply_patch(DEFAULT_STATE, payload)


def test_objects_merge_recursively() -> None:
    state = _patched({"business": {"product": {"name": "Renamed"}}})
    assert state.business.product.name == "Renamed"
    assert state.business.product.current_price == DEFAULT_STATE.business.product.current_price
    assert state.business.items == DEFAULT_STATE.business.items
    assert state.business.page_size == DEFAULT_STATE.business.page_size


def test_partial_patch_leaves_other_sections_untouched() -> None:
    state = _patched({"faults": {"kind": "outage"}})
    assert state.faults.kind == "outage"
    assert state.faults.delay_ms == 0
    assert state.business == DEFAULT_STATE.business


def test_empty_patch_is_a_no_op() -> None:
    assert _patched({}) == DEFAULT_STATE


def test_arrays_replace_wholesale() -> None:
    state = _patched({"business": {"items": [{"id": "Z", "name": "Zeta", "price": "5.00"}]}})
    assert [row.id for row in state.business.items] == ["Z"]


def test_empty_array_clears_rows() -> None:
    assert _patched({"business": {"items": []}}).business.items == ()


def test_replacing_rows_does_not_mutate_defaults() -> None:
    _patched({"business": {"items": []}})
    assert len(DEFAULT_STATE.business.items) == 3


def test_revision_is_preserved_by_patch() -> None:
    state = State(revision=7, business=DEFAULT_STATE.business)
    assert apply_patch(state, {"business": {"page_size": 3}}).revision == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"business": {"product": {"current_price": None}}},
        {"business": {"items": None}},
        {"business": {"items": [{"id": "A", "name": None, "price": "1.00"}]}},
        {"faults": {"kind": None}},
    ],
)
def test_null_is_rejected_everywhere(payload: Any) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert "null is not allowed" in excinfo.value.errors[0]["msg"]


@pytest.mark.parametrize(
    "payload",
    [
        {"revision": 5},
        {"business": {"revision": 5}},
        {"business": {"product": {"revision": 5}}},
        {"business": {"items": [{"revision": 1}]}},
    ],
)
def test_revision_is_read_only_at_any_depth(payload: Any) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert "read-only" in excinfo.value.errors[0]["msg"]


@pytest.mark.parametrize(
    ("payload", "loc"),
    [
        ({"nope": {}}, "nope"),
        ({"business": {"nope": 1}}, "business.nope"),
        ({"business": {"product": {"nope": 1}}}, "business.product.nope"),
        (
            {"business": {"items": [{"id": "A", "name": "n", "price": "1.00", "x": 1}]}},
            "business.items.0.x",
        ),
    ],
)
def test_unknown_keys_rejected(payload: Any, loc: str) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert excinfo.value.errors[0]["loc"] == loc


@pytest.mark.parametrize(
    "payload",
    [
        {"business": 1},
        {"business": []},
        {"business": "x"},
        {"faults": None},
    ],
)
def test_sections_must_be_objects(payload: Any) -> None:
    with pytest.raises(StateValidationError):
        _patched(payload)


@pytest.mark.parametrize("payload", [[], "x", 1, None])
def test_body_must_be_an_object(payload: Any) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert "JSON object" in excinfo.value.errors[0]["msg"]


@pytest.mark.parametrize(
    ("payload", "loc"),
    [
        ({"business": {"page_size": 0}}, "business.page_size"),
        ({"business": {"page_size": 101}}, "business.page_size"),
        ({"business": {"product": {"current_price": "1e2"}}}, "business.product.current_price"),
        ({"business": {"product": {"current_price": 1.5}}}, "business.product.current_price"),
        ({"business": {"product": {"currency": "usd"}}}, "business.product.currency"),
        ({"faults": {"delay_ms": 30_001}}, "faults.delay_ms"),
        (
            {"business": {"items": [{"id": "", "name": "n", "price": "1.00"}]}},
            "business.items.0.id",
        ),
    ],
)
def test_field_errors_are_located(payload: Any, loc: str) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert excinfo.value.errors[0]["loc"] == loc


def test_all_errors_are_reported_together() -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched({"business": {"page_size": 0}, "faults": {"delay_ms": -1}})
    assert {error["loc"] for error in excinfo.value.errors} == {
        "business.page_size",
        "faults.delay_ms",
    }


def test_rejected_patch_never_mutates_input_state() -> None:
    before = DEFAULT_STATE.model_dump(mode="json")
    with pytest.raises(StateValidationError):
        _patched({"business": {"product": {"name": "ok"}, "page_size": 0}})
    assert DEFAULT_STATE.model_dump(mode="json") == before
