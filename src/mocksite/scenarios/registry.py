"""Scenario registry (README §4.2).

Every scenario builds a **complete** target state from the defaults and is
committed in one step, so:

* applying the same scenario twice yields identical business content (only the
  revision moves);
* scenarios never stack — ``price_change`` after ``outage`` clears the fault;
* combination conditions are expressed explicitly through ``PATCH`` instead of
  inventing a scenario per pair.

``build`` receives the current revision only so the returned state can carry it;
the store bumps it on commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from mocksite.state.models import (
    DEFAULT_BUSINESS,
    BusinessData,
    Faults,
    Item,
    Presentation,
    State,
)
from mocksite.state.store import StateStore


@dataclass(frozen=True, slots=True)
class PresetScenario:
    name: str
    description: str
    affects: tuple[str, ...]
    pages: tuple[str, ...]
    business: BusinessData
    presentation: Presentation = field(default_factory=Presentation)
    faults: Faults = field(default_factory=Faults)

    def build(self, revision: int) -> State:
        return State(
            revision=revision,
            business=self.business,
            presentation=self.presentation,
            faults=self.faults,
        )


def _business(
    *,
    current_price: Decimal | None = None,
    item_price: Decimal | None = None,
    items: tuple[Item, ...] | None = None,
) -> BusinessData:
    product = DEFAULT_BUSINESS.product
    if current_price is not None:
        product = product.model_copy(update={"current_price": current_price})
    rows = DEFAULT_BUSINESS.items if items is None else items
    if item_price is not None:
        rows = tuple(
            row.model_copy(update={"price": item_price}) if row.id == "A" else row for row in rows
        )
    return DEFAULT_BUSINESS.model_copy(update={"product": product, "items": rows})


_PRODUCT_PAGES = ("/static/product", "/ssr/product")
_LIST_PAGES = ("/react/list", "/vue/list", "/dynamic/deals")

SCENARIOS: tuple[PresetScenario, ...] = (
    PresetScenario(
        name="baseline",
        description="Default data and normal responses; faults cleared.",
        affects=("business", "presentation", "faults"),
        pages=(*_PRODUCT_PAGES, *_LIST_PAGES, "/api/data"),
        business=DEFAULT_BUSINESS,
    ),
    PresetScenario(
        name="no_change",
        description="Default business data with a new revision; nothing visible changes.",
        affects=("business", "presentation", "faults"),
        pages=(*_PRODUCT_PAGES, *_LIST_PAGES, "/api/data"),
        business=DEFAULT_BUSINESS,
    ),
    PresetScenario(
        name="price_change",
        description="Product current price 128.50 -> 96.00; lists unchanged.",
        affects=("business.product.current_price",),
        pages=_PRODUCT_PAGES,
        business=_business(current_price=Decimal("96.00")),
    ),
    PresetScenario(
        name="item_price_change",
        description="Row A price 10.00 -> 12.50 on every list page.",
        affects=("business.items[A].price",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(item_price=Decimal("12.50")),
    ),
    PresetScenario(
        name="empty_value",
        description="Current-price node kept, text rendered as an empty string.",
        affects=("presentation.product_price",),
        pages=_PRODUCT_PAGES,
        business=DEFAULT_BUSINESS,
        presentation=Presentation(product_price="empty"),
    ),
    PresetScenario(
        name="missing_node",
        description="Current-price node removed; selector matches nothing.",
        affects=("presentation.product_price",),
        pages=_PRODUCT_PAGES,
        business=DEFAULT_BUSINESS,
        presentation=Presentation(product_price="missing"),
    ),
    PresetScenario(
        name="structure_break",
        description="Current-price id renamed to replacement-current-price; text kept.",
        affects=("presentation.product_price",),
        pages=_PRODUCT_PAGES,
        business=DEFAULT_BUSINESS,
        presentation=Presentation(product_price="renamed"),
    ),
    PresetScenario(
        name="empty_list",
        description="List loads successfully with zero rows.",
        affects=("business.items",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(items=()),
    ),
    PresetScenario(
        name="field_rename",
        description="Row price cell class price -> cost; text kept.",
        affects=("presentation.item_price",),
        pages=_LIST_PAGES,
        business=DEFAULT_BUSINESS,
        presentation=Presentation(item_price="renamed"),
    ),
    PresetScenario(
        name="duplicate_rows",
        description="Row A appended once more at the end of the list.",
        affects=("business.items",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(items=(*DEFAULT_BUSINESS.items, DEFAULT_BUSINESS.items[0])),
    ),
    PresetScenario(
        name="pagination_grow",
        description="Rows D and E appended; page size stays 2, so two pages become three.",
        affects=("business.items",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(
            items=(
                *DEFAULT_BUSINESS.items,
                Item(id="D", name="Delta", price=Decimal("40.00")),
                Item(id="E", name="Epsilon", price=Decimal("50.00")),
            )
        ),
    ),
    PresetScenario(
        name="outage",
        description="Site pages and /api/data return 500; admin and /health stay up.",
        affects=("faults.kind",),
        pages=(*_PRODUCT_PAGES, *_LIST_PAGES, "/api/data"),
        business=DEFAULT_BUSINESS,
        faults=Faults(kind="outage"),
    ),
    PresetScenario(
        name="slow_site",
        description="Site pages and /api/data delay 8000ms; admin stays responsive.",
        affects=("faults.delay_ms",),
        pages=(*_PRODUCT_PAGES, *_LIST_PAGES, "/api/data"),
        business=DEFAULT_BUSINESS,
        faults=Faults(delay_ms=8000),
    ),
)

BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}

assert len(BY_NAME) == len(SCENARIOS), "duplicate scenario name"


def build_default_store() -> StateStore:
    """A :class:`StateStore` with every preset registered."""
    store = StateStore()
    store.register(*SCENARIOS)
    return store
