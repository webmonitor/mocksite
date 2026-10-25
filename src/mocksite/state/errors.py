"""Rejected state writes.

The state kernel never raises bare ``ValueError`` for user input: every
rejection carries a list of ``{"loc": ..., "msg": ...}`` entries so the admin
API can return a structured 400 without re-parsing messages.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

ErrorEntry = Mapping[str, str]


def _join(loc: Iterable[Any]) -> str:
    return ".".join(str(part) for part in loc)


class StateValidationError(ValueError):
    """Input rejected; nothing was committed and ``revision`` did not move."""

    def __init__(self, errors: Iterable[ErrorEntry]) -> None:
        self.errors: tuple[dict[str, str], ...] = tuple(dict(error) for error in errors)
        if not self.errors:
            raise ValueError("StateValidationError requires at least one entry")
        super().__init__("; ".join(f"{e['loc']}: {e['msg']}" for e in self.errors))

    @classmethod
    def at(cls, loc: Iterable[Any], msg: str) -> StateValidationError:
        return cls([{"loc": _join(loc), "msg": msg}])

    @classmethod
    def from_pydantic(cls, exc: Any) -> StateValidationError:
        """Convert a pydantic ``ValidationError`` into kernel-shaped errors."""
        return cls({"loc": _join(error["loc"]), "msg": str(error["msg"])} for error in exc.errors())


class UnknownScenario(LookupError):
    """Requested scenario name is not registered."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown scenario: {name!r}")
