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
    state = _patched({"business": {"notice": {"title": "改过的标题"}}})
    assert state.business.notice.title == "改过的标题"
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee
    assert state.business.notice.body == DEFAULT_STATE.business.notice.body


def test_patch_touches_only_the_addressed_field() -> None:
    state = _patched({"business": {"notice": {"view_count": 7}}})
    assert state.business.notice.view_count == 7
    assert state.business.notice.title == DEFAULT_STATE.business.notice.title
    assert state.business.notice.current_fee == DEFAULT_STATE.business.notice.current_fee


def test_empty_patch_is_a_no_op() -> None:
    assert _patched({}) == DEFAULT_STATE


def test_arrays_replace_wholesale() -> None:
    """Sending one attachment deletes the rest; there is no per-item merge."""
    state = _patched(
        {
            "business": {
                "notice": {
                    "attachments": [
                        {"id": "only", "name": "附件.pdf", "src": "/static/shared/img/attachment-pdf.svg"}
                    ]
                }
            }
        }
    )
    assert [item.id for item in state.business.notice.attachments] == ["only"]


def test_empty_array_clears_the_body() -> None:
    assert _patched({"business": {"notice": {"body": []}}}).business.notice.body == ()


def test_replacing_arrays_does_not_mutate_defaults() -> None:
    _patched({"business": {"notice": {"body": []}}})
    assert len(DEFAULT_STATE.business.notice.body) == 6


def test_revision_is_preserved_by_patch() -> None:
    state = State(revision=7, business=DEFAULT_STATE.business)
    assert apply_patch(state, {"business": {"notice": {"view_count": 3}}}).revision == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"business": {"notice": {"current_fee": None}}},
        {"business": {"notice": {"attachments": None}}},
        {"business": {"notice": {"title": None}}},
        {"business": {"notice": {"body": [None]}}},
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
        {"business": {"notice": {"revision": 5}}},
        {"business": {"notice": {"body": [{"revision": 1}]}}},
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
        ({"business": {"notice": {"nope": 1}}}, "business.notice.nope"),
        (
            {
                "business": {
                    "notice": {
                        "attachments": [
                            {
                                "id": "a",
                                "name": "n",
                                "src": "/s",
                                "x": 1,
                            }
                        ]
                    }
                }
            },
            "business.notice.attachments.0.x",
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
        {"business": {"notice": []}},
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
        ({"business": {"notice": {"view_count": -1}}}, "business.notice.view_count"),
        ({"business": {"notice": {"current_fee": "1e2"}}}, "business.notice.current_fee"),
        ({"business": {"notice": {"current_fee": 1.5}}}, "business.notice.current_fee"),
        ({"business": {"notice": {"currency": "cny"}}}, "business.notice.currency"),
        ({"business": {"notice": {"effective_date": "2026/11/01"}}}, "business.notice.effective_date"),
        (
            {"business": {"notice": {"attachments": [{"id": "", "name": "n", "src": "/s"}]}}},
            "business.notice.attachments.0.id",
        ),
    ],
)
def test_field_errors_are_located(payload: Any, loc: str) -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched(payload)
    assert excinfo.value.errors[0]["loc"] == loc


def test_all_errors_are_reported_together() -> None:
    with pytest.raises(StateValidationError) as excinfo:
        _patched({"business": {"notice": {"view_count": -1, "current_fee": "1e2"}}})
    assert {error["loc"] for error in excinfo.value.errors} == {
        "business.notice.view_count",
        "business.notice.current_fee",
    }


def test_faults_section_is_rejected_as_unknown() -> None:
    """Fault injection was removed; a stale client must get a clear 400."""
    with pytest.raises(StateValidationError) as excinfo:
        _patched({"faults": {"kind": "outage"}})
    assert excinfo.value.errors[0]["loc"] == "faults"


def test_rejected_patch_never_mutates_input_state() -> None:
    before = DEFAULT_STATE.model_dump(mode="json")
    with pytest.raises(StateValidationError):
        _patched({"business": {"notice": {"title": "ok", "view_count": -1}}})
    assert DEFAULT_STATE.model_dump(mode="json") == before
