"""``PATCH /_admin/state`` semantics.

Rules (README §5.2), all enforced here so the store never sees a half-valid
payload:

* objects merge recursively — ``{"business": {"notice": {"title": "x"}}}``
  leaves every other notice field alone;
* arrays replace wholesale — sending ``attachments`` with one item deletes the rest;
* ``null`` is not a value and is never a delete instruction;
* ``revision`` is read-only and rejected at any depth;
* unknown keys and type errors reject the whole patch.

A patch is applied to a JSON snapshot of the current state and then validated
as a complete :class:`State`, so a rejected patch cannot leave partial updates
behind: nothing is stored until validation succeeds.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from mocksite.state.errors import StateValidationError
from mocksite.state.models import State

MUTABLE_SECTIONS = ("business",)
READ_ONLY_KEYS = ("revision",)


def _reject_null(value: Any, loc: tuple[str, ...]) -> None:
    if value is None:
        raise StateValidationError.at(loc, "null is not allowed")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise StateValidationError.at((*loc, str(key)), "keys must be strings")
            _reject_null(child, (*loc, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_null(child, (*loc, str(index)))


def _reject_read_only(value: Any, loc: tuple[str, ...]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in READ_ONLY_KEYS:
                raise StateValidationError.at((*loc, str(key)), "field is read-only")
            _reject_read_only(child, (*loc, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_read_only(child, (*loc, str(index)))


def _merge(target: Any, patch: Any, loc: tuple[str, ...]) -> Any:
    """Recursively merge ``patch`` into ``target``; lists and scalars replace."""
    if not isinstance(target, Mapping) or not isinstance(patch, Mapping):
        return patch
    merged = dict(target)
    for key, value in patch.items():
        merged[key] = _merge(target.get(key), value, (*loc, key))
    return merged


def apply_patch(current: State, payload: Any) -> State:
    """Return the patched state (same revision); raise on any invalid input."""
    if not isinstance(payload, Mapping):
        raise StateValidationError.at((), "body must be a JSON object")

    _reject_null(payload, ())
    _reject_read_only(payload, ())

    unknown = [key for key in payload if key not in MUTABLE_SECTIONS]
    if unknown:
        raise StateValidationError({"loc": str(key), "msg": "unknown section"} for key in unknown)
    for key, value in payload.items():
        if not isinstance(value, Mapping):
            raise StateValidationError.at((key,), "must be a JSON object")

    document = current.model_dump(mode="json")
    for key, value in payload.items():
        document[key] = _merge(document[key], value, (key,))

    try:
        return State.model_validate(document)
    except ValidationError as exc:
        raise StateValidationError.from_pydantic(exc) from None
