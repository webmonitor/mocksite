"""In-process state kernel: models, PATCH semantics, store.

Imports no web framework, so it can be unit tested and reused by both the site
and admin listeners.
"""

from mocksite.state.errors import StateValidationError, UnknownScenario
from mocksite.state.models import DEFAULT_BUSINESS, DEFAULT_STATE, State
from mocksite.state.patch import apply_patch
from mocksite.state.store import Scenario, StateStore

__all__ = [
    "DEFAULT_BUSINESS",
    "DEFAULT_STATE",
    "Scenario",
    "State",
    "StateStore",
    "StateValidationError",
    "UnknownScenario",
    "apply_patch",
]
