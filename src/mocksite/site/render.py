"""HTML rendering for the site pages.

Rendering is pure: it takes a state and returns a string. ``StateStore`` calls
it inside its commit lock so the pre-rendered page can never lag behind the
state (README §4.1).

Jinja2 autoescaping is enabled for every template, and prices are passed as
their decimal strings, so a value can never be interpreted as markup.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from mocksite.state.models import State

TEMPLATES = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(enabled_extensions=("html",), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


#: Stock labels a shop shows instead of a raw enum.
STOCK_LABELS = {
    "in_stock": "In stock, ready to ship",
    "low_stock": "Low stock",
    "out_of_stock": "Out of stock",
    "preorder": "Pre-order — ships next week",
}

#: Recommended products are fixed: they are page chrome, not monitored content.
RECOMMENDATIONS = (
    {
        "name": "Kenya Nyeri AA 1kg",
        "price": "142.00",
        "src": "/static/assets/img/coffee-red.svg",
        "alt": "Kenya Nyeri coffee bag",
    },
    {
        "name": "Colombia Huila 1kg",
        "price": "118.00",
        "src": "/static/assets/img/coffee-black.svg",
        "alt": "Colombia Huila coffee bag",
    },
    {
        "name": "Brazil Cerrado 1kg",
        "price": "96.00",
        "src": "/static/assets/img/coffee-natural-back.svg",
        "alt": "Brazil Cerrado coffee bag",
    },
    {
        "name": "Decaf Guji 1kg",
        "price": "134.00",
        "src": "/static/assets/img/coffee-natural.svg",
        "alt": "Decaf Guji coffee bag",
    },
)


def _money(value: Decimal) -> str:
    """Fixed two-decimal rendering, like a shop price tag."""
    return f"{value:.2f}"


def _context(state: State) -> dict[str, object]:
    business = state.business
    product = business.product
    current = product.current_price
    original = product.original_price

    discount = 0
    if original > 0 and current < original:
        discount = round((original - current) / original * 100)
    savings = _money(original - current) if original > current else _money(Decimal(0))

    colors = tuple(v for v in product.variants if v.kind == "color")
    sizes = tuple(v for v in product.variants if v.kind == "size")

    return {
        "revision": state.revision,
        "images": product.images,
        "color_variants": colors,
        "size_variants": sizes,
        "default_color": colors[0] if colors else None,
        "default_size": next((v for v in sizes if v.id == "size-1kg"), sizes[0] if sizes else None),
        "recommendations": RECOMMENDATIONS,
        "review_page_size": business.review_page_size,
        "discount_percent": discount,
        "savings": savings,
        "installment_price": _money(current / 4),
        # 1 kg default: per-100 g is the price divided by ten.
        "unit_price": _money(current / 10),
        "stock_label": STOCK_LABELS[product.stock_status],
        "product": {
            "id": product.id,
            "name": product.name,
            "brand": product.brand,
            "sku": product.sku,
            # Decimal -> str keeps the exact decimal representation.
            "current_price": _money(current),
            "original_price": _money(original),
            "currency": product.currency,
            "rating": _money(product.rating),
            "review_count": product.review_count,
            "stock_status": product.stock_status,
            "stock_count": product.stock_count,
            "description": product.description,
            "highlights": product.highlights,
            "specs": product.specs,
        },
    }


def render_product(state: State) -> str:
    """Complete HTML for ``/static/product`` and ``/ssr/product``."""
    return _environment().get_template("product.html").render(**_context(state))


#: Vendored UMD bundles per framework. Order matters: react-dom needs react.
VENDOR_REACT: tuple[str, ...] = ("react-18.3.1.min.js", "react-dom-18.3.1.min.js")
VENDOR_VUE: tuple[str, ...] = ("vue-3.5.43.min.js",)


def render_list(state: State, framework: str) -> str:
    """HTML shell for a client-rendered list page.

    The shell is deliberately empty of rows: the collector must wait for
    ``#app[data-ready="true"]``, which the page script sets after fetching and
    rendering. Rendering rows server-side here would hide a broken data path.
    """
    if framework == "react":
        vendor, script, title = VENDOR_REACT, "react-list.js", "Inventory (React)"
    elif framework == "vue":
        vendor, script, title = VENDOR_VUE, "vue-list.js", "Inventory (Vue)"
    else:
        raise ValueError(f"unknown framework: {framework!r}")

    return (
        _environment()
        .get_template("list.html")
        .render(
            title=title,
            vendor=vendor,
            script=script,
            page_size=state.business.page_size,
        )
    )


def render_deals(state: State) -> str:
    """HTML shell for ``/dynamic/deals`` (pagination happens in the browser)."""
    return _environment().get_template("deals.html").render(page_size=state.business.page_size)
