"""Process-local state store: the single source of truth.

Every write goes through :meth:`StateStore.commit`, which performs validation,
static-page re-render, state swap and revision increment **inside one lock**.
That ordering is the point of this module: there is no window where the state
has advanced but the pre-rendered static page still shows the old content.

The store is synchronous and free of HTTP/framework imports so it can be unit
tested directly. Request handlers in stage 2 call it from async code; the
critical section is pure CPU work (render + swap), never I/O.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from mocksite.state.errors import UnknownScenario
from mocksite.state.models import DEFAULT_STATE, State
from mocksite.state.patch import apply_patch

Renderer = Callable[[State], str]


class Scenario(Protocol):
    """A named, absolute target state built from defaults (never incremental)."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def affects(self) -> tuple[str, ...]: ...

    @property
    def pages(self) -> tuple[str, ...]: ...

    def build(self, revision: int) -> State: ...


class StateStore:
    def __init__(
        self,
        *,
        renderer: Renderer | None = None,
        initial: State = DEFAULT_STATE,
    ) -> None:
        self._renderer = renderer or _no_renderer
        self._lock = threading.Lock()
        self._state = initial
        self._static = self._renderer(initial)
        self._scenarios: dict[str, Scenario] = {}

    # -- reads -------------------------------------------------------------
    @property
    def state(self) -> State:
        """Current immutable snapshot; safe to keep for the duration of a request."""
        return self._state

    @property
    def static_html(self) -> str:
        """HTML pre-rendered at the last commit (``/static/product``)."""
        return self._static

    def snapshot(self) -> tuple[State, str]:
        """Read state and its static page atomically."""
        with self._lock:
            return self._state, self._static

    def set_renderer(self, renderer: Renderer) -> None:
        """Install the page renderer and refresh the pre-rendered page.

        Used once at startup by the process entrypoint; the kernel itself does
        not know about Jinja2.
        """
        with self._lock:
            self._renderer = renderer
            self._static = renderer(self._state)

    def scenarios(self) -> tuple[Scenario, ...]:
        return tuple(self._scenarios.values())

    def scenario(self, name: str) -> Scenario:
        try:
            return self._scenarios[name]
        except KeyError:
            raise UnknownScenario(name) from None

    def register(self, *scenarios: Scenario) -> None:
        for scenario in scenarios:
            if scenario.name in self._scenarios:
                raise ValueError(f"scenario already registered: {scenario.name!r}")
            self._scenarios[scenario.name] = scenario

    # -- writes ------------------------------------------------------------
    def commit(self, candidate: State) -> State:
        """Publish ``candidate`` with ``revision + 1``; returns the new state."""
        with self._lock:
            return self._commit_locked(candidate)

    def patch(self, payload: Any) -> State:
        with self._lock:
            return self._commit_locked(apply_patch(self._state, payload))

    def apply_scenario(self, name: str) -> tuple[State, State]:
        """Atomically apply a scenario; returns ``(before, after)``."""
        scenario = self.scenario(name)
        with self._lock:
            before = self._state
            after = self._commit_locked(scenario.build(revision=before.revision))
            return before, after

    def reset(self) -> tuple[State, State]:
        """Restore defaults, clearing faults and counters; advances revision."""
        with self._lock:
            before = self._state
            after = self._commit_locked(DEFAULT_STATE)
            return before, after

    # -- internals ---------------------------------------------------------
    def _commit_locked(self, candidate: State) -> State:
        # Bump first so the renderer sees the revision it is publishing, then
        # render, then swap. A failing template therefore leaves both the state
        # and the pre-rendered page untouched — no half-committed revision.
        committed = candidate.model_copy(update={"revision": self._state.revision + 1})
        rendered = self._renderer(committed)
        self._state, self._static = committed, rendered
        return committed


def _no_renderer(state: State) -> str:
    del state
    return ""
