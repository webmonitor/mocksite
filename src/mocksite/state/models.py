"""Immutable state model for the mock site.

All models are frozen and hashable-by-construction (tuples, not lists), so a
snapshot handed to a request can never be mutated by it. Prices are ``Decimal``
in memory and decimal *strings* on the wire: floats never appear anywhere.

``revision`` is carried on :class:`State` but is never accepted as input; the
store owns it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
)

MAX_TEXT = 256
MAX_PRICE_TEXT = 64
MAX_ITEMS = 100
MAX_DELAY_MS = 30_000

Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
RowId = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]


def _parse_price(value: Any) -> Decimal:
    """Accept plain decimal strings (and ``Decimal`` for in-process builders).

    Floats are rejected rather than converted: ``0.1`` has no exact decimal
    representation and would make renders and diffs unstable.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("price must be finite")
        if value < 0:
            raise ValueError("price must not be negative")
        return value
    if not isinstance(value, str):
        # ValueError is intentional: pydantic turns it into a validation
        # error instead of a crash, which is exactly the desired 400.
        raise ValueError("price must be a decimal string, not a number")  # noqa: TRY004
    if not value:
        raise ValueError("price must not be empty")
    if len(value) > MAX_PRICE_TEXT:
        raise ValueError(f"price must be at most {MAX_PRICE_TEXT} characters")
    body = value.removeprefix("+")
    whole, dot, fraction = body.partition(".")
    if not whole.isdigit() or (dot and (not fraction or not fraction.isdigit())):
        raise ValueError("price must match <digits>[.<digits>]")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the checks above
        raise ValueError("price is not a valid decimal") from exc
    if not parsed.is_finite():
        raise ValueError("price must be finite")
    if parsed < 0:
        raise ValueError("price must not be negative")
    return parsed


Price = Annotated[
    Decimal,
    BeforeValidator(_parse_price),
    PlainSerializer(lambda value: str(value), return_type=str),
]

#: Presentation controls are single enums on purpose: one field, one state.
#: Two booleans (``empty`` + ``missing``) could contradict each other.
ProductPriceRendering = Literal["normal", "empty", "missing", "renamed"]
ItemPriceRendering = Literal["normal", "renamed"]
FaultKind = Literal["none", "outage"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Product(_Frozen):
    id: RowId
    name: Text
    current_price: Price
    original_price: Price
    currency: Currency


class Item(_Frozen):
    id: RowId
    name: Text
    price: Price


class BusinessData(_Frozen):
    """The only thing a collection run should observe as content."""

    product: Product
    items: Annotated[tuple[Item, ...], Field(max_length=MAX_ITEMS)] = ()
    page_size: Annotated[StrictInt, Field(ge=1, le=100)] = 2

    @property
    def page_count(self) -> int:
        """Derived, never stored: a stored total could contradict ``items``."""
        return -(-len(self.items) // self.page_size)


class Presentation(_Frozen):
    """How values are rendered, without corrupting the business data."""

    product_price: ProductPriceRendering = "normal"
    item_price: ItemPriceRendering = "normal"


class Faults(_Frozen):
    """Injected behaviour for site routes only; admin and ``/health`` ignore it.

    Both fields may be set at once (PATCH combines conditions); consumers must
    treat ``kind="outage"`` as taking precedence over ``delay_ms`` so a failure
    is never silently masked by a delay.
    """

    kind: FaultKind = "none"
    delay_ms: Annotated[StrictInt, Field(ge=0, le=MAX_DELAY_MS)] = 0


class State(_Frozen):
    revision: Annotated[StrictInt, Field(ge=0)] = 0
    business: BusinessData
    presentation: Presentation = Presentation()
    faults: Faults = Faults()


DEFAULT_BUSINESS = BusinessData(
    product=Product(
        id="coffee",
        name="Fixture Coffee",
        current_price=Decimal("128.50"),
        original_price=Decimal("199.00"),
        currency="USD",
    ),
    items=(
        Item(id="A", name="Alpha", price=Decimal("10.00")),
        Item(id="B", name="Beta", price=Decimal("20.00")),
        Item(id="C", name="Gamma", price=Decimal("30.00")),
    ),
    page_size=2,
)

DEFAULT_STATE = State(business=DEFAULT_BUSINESS)
