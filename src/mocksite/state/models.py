"""Immutable state model for the mock site.

All models are frozen and hashable-by-construction (tuples, not lists), so a
snapshot handed to a request can never be mutated by it. Prices are ``Decimal``
in memory and decimal *strings* on the wire: floats never appear anywhere.

``revision`` is carried on :class:`State` but is never accepted as input; the
store owns it.

The business data describes a realistic product-detail page: a gallery, several
price nodes, stock, variants, specifications and reviews. That richness is the
point — a collector has to pick the *right* node out of a page that looks like
a real shop, not out of an eight-element fixture.

Scope: this site verifies **data** changes only. The DOM structure of every page
is fixed; scenarios swap business values (price, rows, reviews, stock) and inject
transport faults. Structural breakage (missing nodes, renamed ids, empty cells)
is deliberately *not* modelled — there is no presentation-control layer, so a
page cannot be made to render a different shape for the same data.
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
MAX_LONG_TEXT = 2000
MAX_PRICE_TEXT = 64
MAX_ITEMS = 100
MAX_REVIEWS = 50
MAX_DELAY_MS = 30_000

Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
LongText = Annotated[str, Field(min_length=1, max_length=MAX_LONG_TEXT)]
RowId = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


def _parse_decimal_string(value: Any) -> Decimal:
    """Accept plain decimal strings (and ``Decimal`` for in-process builders).

    Floats are rejected rather than converted: ``0.1`` has no exact decimal
    representation and would make renders and diffs unstable.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("value must be finite")
        if value < 0:
            raise ValueError("value must not be negative")
        return value
    if not isinstance(value, str):
        # ValueError is intentional: pydantic turns it into a validation
        # error instead of a crash, which is exactly the desired 400.
        raise ValueError("value must be a decimal string, not a number")  # noqa: TRY004
    if not value:
        raise ValueError("value must not be empty")
    if len(value) > MAX_PRICE_TEXT:
        raise ValueError(f"value must be at most {MAX_PRICE_TEXT} characters")
    body = value.removeprefix("+")
    whole, dot, fraction = body.partition(".")
    if not whole.isdigit() or (dot and (not fraction or not fraction.isdigit())):
        raise ValueError("value must match <digits>[.<digits>]")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the checks above
        raise ValueError("value is not a valid decimal") from exc
    if not parsed.is_finite():
        raise ValueError("value must be finite")
    if parsed < 0:
        raise ValueError("value must not be negative")
    return parsed


def _parse_rating(value: Any) -> Decimal:
    parsed = _parse_decimal_string(value)
    if parsed > 5:
        raise ValueError("rating must be at most 5")
    return parsed


Price = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal_string),
    PlainSerializer(lambda value: str(value), return_type=str),
]

Rating = Annotated[
    Decimal,
    BeforeValidator(_parse_rating),
    PlainSerializer(lambda value: str(value), return_type=str),
]

FaultKind = Literal["none", "outage"]

#: Stock states a real shop exposes; ``out_of_stock`` still renders the page.
StockStatus = Literal["in_stock", "low_stock", "out_of_stock", "preorder"]
VariantKind = Literal["color", "size"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Image(_Frozen):
    """One gallery entry. ``src`` is a site-relative asset path, never a CDN."""

    id: RowId
    alt: Text
    src: Text
    color: RowId


class Variant(_Frozen):
    id: RowId
    label: Text
    kind: VariantKind
    available: bool = True


class Spec(_Frozen):
    label: Text
    value: Text


class Review(_Frozen):
    id: RowId
    author: Text
    rating: Annotated[StrictInt, Field(ge=1, le=5)]
    date: IsoDate
    title: Text
    body: LongText
    verified: bool = True


class Product(_Frozen):
    id: RowId
    name: Text
    brand: Text
    sku: Text
    current_price: Price
    original_price: Price
    currency: Currency
    rating: Rating = Decimal("4.6")
    review_count: Annotated[StrictInt, Field(ge=0, le=100_000)] = 128
    stock_status: StockStatus = "in_stock"
    stock_count: Annotated[StrictInt, Field(ge=0, le=10_000)] = 42
    description: LongText = "A fixture product."
    highlights: Annotated[tuple[Text, ...], Field(max_length=20)] = ()
    images: Annotated[tuple[Image, ...], Field(max_length=20)] = ()
    variants: Annotated[tuple[Variant, ...], Field(max_length=40)] = ()
    specs: Annotated[tuple[Spec, ...], Field(max_length=40)] = ()


class Item(_Frozen):
    id: RowId
    name: Text
    price: Price


class BusinessData(_Frozen):
    """The only thing a collection run should observe as content."""

    product: Product
    items: Annotated[tuple[Item, ...], Field(max_length=MAX_ITEMS)] = ()
    page_size: Annotated[StrictInt, Field(ge=1, le=100)] = 2
    reviews: Annotated[tuple[Review, ...], Field(max_length=MAX_REVIEWS)] = ()
    review_page_size: Annotated[StrictInt, Field(ge=1, le=50)] = 2

    @property
    def page_count(self) -> int:
        """Derived, never stored: a stored total could contradict ``items``."""
        return -(-len(self.items) // self.page_size)

    @property
    def review_page_count(self) -> int:
        return -(-len(self.reviews) // self.review_page_size)


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
    faults: Faults = Faults()


DEFAULT_PRODUCT = Product(
    id="coffee",
    name="Fixture Coffee Roaster — Ethiopia Guji 1kg",
    brand="Fixture Roasters",
    sku="FX-COF-GUJI-1KG",
    current_price=Decimal("128.50"),
    original_price=Decimal("199.00"),
    currency="USD",
    rating=Decimal("4.6"),
    review_count=128,
    stock_status="in_stock",
    stock_count=42,
    description=(
        "A washed Ethiopian single origin from the Guji zone, roasted for filter. "
        "Bright citrus acidity, jasmine aroma and a long honeyed finish. Roasted to "
        "order and shipped within 48 hours."
    ),
    highlights=(
        "Single origin, washed process, Guji zone",
        "Roasted to order — ships within 48 hours",
        "1 kg whole bean, also available ground",
        "Free shipping on orders over 50.00",
    ),
    images=(
        Image(
            id="img-1",
            alt="Bag of Guji coffee, front",
            src="/static/shared/img/coffee-natural.svg",
            color="natural",
        ),
        Image(
            id="img-2",
            alt="Bag of Guji coffee, back",
            src="/static/shared/img/coffee-natural-back.svg",
            color="natural",
        ),
        Image(
            id="img-3",
            alt="Guji coffee in a black bag",
            src="/static/shared/img/coffee-black.svg",
            color="black",
        ),
        Image(
            id="img-4",
            alt="Guji coffee in a red bag",
            src="/static/shared/img/coffee-red.svg",
            color="red",
        ),
    ),
    variants=(
        Variant(id="color-natural", label="Natural kraft", kind="color"),
        Variant(id="color-black", label="Matte black", kind="color"),
        Variant(id="color-red", label="Chili red", kind="color"),
        Variant(id="size-250", label="250 g", kind="size"),
        Variant(id="size-500", label="500 g", kind="size"),
        Variant(id="size-1kg", label="1 kg", kind="size"),
        Variant(id="size-2kg", label="2 kg", kind="size", available=False),
    ),
    specs=(
        Spec(label="Origin", value="Ethiopia, Guji zone"),
        Spec(label="Process", value="Washed"),
        Spec(label="Variety", value="Heirloom"),
        Spec(label="Roast level", value="Medium-light"),
        Spec(label="Net weight", value="1 kg"),
        Spec(label="Packaging", value="Recyclable kraft bag with valve"),
        Spec(label="Best before", value="12 months from roast date"),
    ),
)

DEFAULT_REVIEWS = (
    Review(
        id="rev-1",
        author="Dana R.",
        rating=5,
        date="2026-09-14",
        title="Exactly the jasmine note I wanted",
        body=(
            "Brewed as V60 at 1:16. The jasmine aroma is unmistakable and the finish "
            "stays sweet. Second bag I order."
        ),
    ),
    Review(
        id="rev-2",
        author="Miguel S.",
        rating=4,
        date="2026-09-02",
        title="Great but needs a rest",
        body=(
            "First cups were a little muted; after a week of resting it opened up "
            "nicely. Packaging keeps it fresh."
        ),
    ),
    Review(
        id="rev-3",
        author="Aiko T.",
        rating=5,
        date="2026-08-21",
        title="Consistent roast",
        body=(
            "Third order in a row and the roast level has not drifted. Grind size is "
            "consistent for pour over."
        ),
    ),
    Review(
        id="rev-4",
        author="Peter N.",
        rating=3,
        date="2026-08-05",
        title="Good, not exceptional",
        body=(
            "Solid daily coffee. I expected more fruit for a Guji, but it is clean and "
            "easy to brew."
        ),
    ),
    Review(
        id="rev-5",
        author="Lena K.",
        rating=5,
        date="2026-07-30",
        title="Fast shipping",
        body=(
            "Ordered Monday, roasted Tuesday, arrived Thursday. The valve bag smells "
            "fantastic when opened."
        ),
    ),
)

DEFAULT_BUSINESS = BusinessData(
    product=DEFAULT_PRODUCT,
    items=(
        Item(id="A", name="Alpha", price=Decimal("10.00")),
        Item(id="B", name="Beta", price=Decimal("20.00")),
        Item(id="C", name="Gamma", price=Decimal("30.00")),
    ),
    page_size=2,
    reviews=DEFAULT_REVIEWS,
    review_page_size=2,
)

DEFAULT_STATE = State(business=DEFAULT_BUSINESS)
