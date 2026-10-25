"""Store invariants: revision discipline, atomic commit, render-then-swap."""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from mocksite.state.errors import StateValidationError, UnknownScenario
from mocksite.state.models import DEFAULT_STATE, State
from mocksite.state.store import StateStore


def test_initial_state_is_default_with_revision_zero() -> None:
    store = StateStore()
    assert store.state == DEFAULT_STATE
    assert store.state.revision == 0


def test_patch_advances_revision_once() -> None:
    store = StateStore()
    assert store.patch({"business": {"page_size": 3}}).revision == 1
    assert store.patch({"business": {"page_size": 4}}).revision == 2


def test_invalid_patch_does_not_advance_revision() -> None:
    store = StateStore()
    store.patch({"business": {"page_size": 3}})
    with pytest.raises(StateValidationError):
        store.patch({"business": {"page_size": 0}})
    assert store.state.revision == 1
    assert store.state.business.page_size == 3


def test_reset_restores_defaults_and_advances_revision() -> None:
    store = StateStore()
    store.patch({"business": {"product": {"current_price": "1.00"}}, "faults": {"kind": "outage"}})
    before, after = store.reset()
    assert before.revision == 1
    assert after.revision == 2
    assert after.business == DEFAULT_STATE.business
    assert after.faults.kind == "none"


def test_reset_is_idempotent_in_content_but_not_revision() -> None:
    store = StateStore()
    _, first = store.reset()
    _, second = store.reset()
    assert first.business == second.business
    assert second.revision == first.revision + 1


def test_static_html_is_rerendered_on_every_commit() -> None:
    rendered: list[int] = []

    def renderer(state: State) -> str:
        rendered.append(state.revision)
        return f"rev={state.revision}"

    store = StateStore(renderer=renderer)
    store.patch({"business": {"page_size": 3}})
    state, html = store.snapshot()
    assert html == f"rev={state.revision}"
    assert rendered == [0, 1]


def test_renderer_failure_does_not_advance_state_or_page() -> None:
    def renderer(state: State) -> str:
        if state.revision == 1:
            raise RuntimeError("template exploded")
        return f"rev={state.revision}"

    store = StateStore(renderer=renderer)
    with pytest.raises(RuntimeError):
        store.patch({"business": {"page_size": 3}})
    assert store.state.revision == 0
    assert store.static_html == "rev=0"


def test_failed_render_keeps_previous_page_content() -> None:
    def renderer(state: State) -> str:
        if state.business.page_size == 4:
            raise RuntimeError("boom")
        return f"page_size={state.business.page_size}"

    store = StateStore(renderer=renderer)
    store.patch({"business": {"page_size": 3}})
    with pytest.raises(RuntimeError):
        store.patch({"business": {"page_size": 4}})
    state, html = store.snapshot()
    assert state.business.page_size == 3
    assert html == "page_size=3"


def test_snapshot_is_consistent_under_concurrent_writes() -> None:
    store = StateStore(renderer=lambda state: f"rev={state.revision}")
    mismatches: list[tuple[int, str]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            state, html = store.snapshot()
            if html != f"rev={state.revision}":
                mismatches.append((state.revision, html))

    def writer() -> None:
        for size in range(1, 60):
            store.patch({"business": {"page_size": size % 100 + 1}})

    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    try:
        writer()
    finally:
        stop.set()
        reader_thread.join()

    assert mismatches == []
    assert store.state.revision == 59


def test_concurrent_patches_never_lose_a_revision() -> None:
    store = StateStore()
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for step in range(25):
                store.patch({"business": {"page_size": (index * 25 + step) % 100 + 1}})
        except Exception as exc:  # noqa: BLE001 - surfaced by assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.state.revision == 100


def test_scenario_application_returns_before_and_after() -> None:
    from mocksite.scenarios.registry import build_default_store

    store = build_default_store()
    before, after = store.apply_scenario("price_change")
    assert before.revision == 0
    assert after.revision == 1
    assert after.business.product.current_price == Decimal("96.00")


def test_unknown_scenario_raises_and_leaves_state_alone() -> None:
    from mocksite.scenarios.registry import build_default_store

    store = build_default_store()
    with pytest.raises(UnknownScenario):
        store.apply_scenario("does-not-exist")
    assert store.state.revision == 0


def test_scenario_is_idempotent_in_content() -> None:
    from mocksite.scenarios.registry import build_default_store

    store = build_default_store()
    _, first = store.apply_scenario("item_price_change")
    _, second = store.apply_scenario("item_price_change")
    assert first.business == second.business
    assert second.revision == first.revision + 1


def test_duplicate_scenario_registration_rejected() -> None:
    from mocksite.scenarios.registry import SCENARIOS

    store = StateStore()
    store.register(SCENARIOS[0])
    with pytest.raises(ValueError):
        store.register(SCENARIOS[0])


def test_scenarios_do_not_stack() -> None:
    from mocksite.scenarios.registry import build_default_store

    store = build_default_store()
    store.apply_scenario("outage")
    _, after = store.apply_scenario("price_change")
    assert after.faults.kind == "none"
    assert after.business.product.current_price == Decimal("96.00")


def test_empty_patch_still_advances_revision() -> None:
    """A write that changes nothing is still a write (cf. the ``no_change`` scenario)."""
    store = StateStore()
    assert store.patch({}).revision == 1
    assert store.state.business == DEFAULT_STATE.business
