"""HTML rendering for the site pages.

Rendering is pure: it takes a state and returns a string. ``StateStore`` calls
it inside its commit lock so the pre-rendered page can never lag behind the
state (README §4.1).

Jinja2 autoescaping is enabled for every template, and prices are passed as
their decimal strings, so a value can never be interpreted as markup.
"""

from __future__ import annotations

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


def _context(state: State) -> dict[str, object]:
    product = state.business.product
    return {
        "revision": state.revision,
        "presentation": state.presentation,
        "product": {
            "id": product.id,
            "name": product.name,
            # Decimal -> str keeps the exact decimal representation.
            "current_price": str(product.current_price),
            "original_price": str(product.original_price),
            "currency": product.currency,
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
            presentation=state.presentation,
        )
    )


def render_deals(state: State) -> str:
    """HTML shell for ``/dynamic/deals`` (pagination happens in the browser)."""
    return (
        _environment()
        .get_template("deals.html")
        .render(
            page_size=state.business.page_size,
            presentation=state.presentation,
        )
    )
