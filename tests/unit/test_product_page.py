"""The product page: fixed structure, data-driven values.

Scope note: this site verifies **data** changes only. Page structure never
changes between scenarios, so these tests pin two things:

* the structural invariants a collector depends on (the price node is unique
  among price-shaped decoys, the review list is client-rendered, ...);
* the fact that *only values* move when data changes.
"""

from __future__ import annotations

import re

import pytest

from mocksite.scenarios.registry import BY_NAME
from mocksite.site.render import render_product
from mocksite.state.models import DEFAULT_STATE, State


def _render(state: State | None = None) -> str:
    return render_product(state or DEFAULT_STATE)


def test_price_node_is_unique_but_surrounded_by_decoys() -> None:
    html = _render()
    # Exactly one element may carry the monitored id.
    assert html.count('id="current-price"') == 1
    # The decoys exist and carry real prices, so a wrong selector returns data
    # instead of nothing — which is the failure mode worth catching.
    assert "installment-price" in html
    assert "unit-price" in html
    assert "msrp-price" in html
    assert 'id="original-price"' in html
    prices = re.findall(r"\b\d+\.\d{2}\b", html)
    assert len(prices) >= 5, "the page should contain several price-shaped values"


def test_current_price_renders_exactly() -> None:
    html = _render()
    assert '<span id="current-price">128.50</span>' in html
    assert '<span id="original-price">199.00</span>' in html
    assert '<span class="price-currency" id="currency">USD</span>' in html


def test_structure_is_identical_for_every_scenario() -> None:
    """The whole point of the data-only model: shape never changes."""
    markers = (
        'id="current-price"',
        'id="original-price"',
        'id="rating-value"',
        "gallery-image",
        "reviews-list",
        "spec-table",
        "reco-grid",
    )
    shapes = {}
    for scenario in BY_NAME.values():
        html = render_product(scenario.build(revision=0))
        shapes[scenario.name] = tuple(marker for marker in markers if marker in html)
    baseline = shapes["baseline"]
    for name, shape in shapes.items():
        assert shape == baseline, f"{name} changed the page structure"


def test_data_scenarios_move_values_without_moving_structure() -> None:
    def price_node(html: str) -> str:
        match = re.search(r'<span id="current-price">([^<]*)</span>', html)
        assert match is not None, "the price node must always exist"
        return match.group(1)

    baseline = _render()
    priced = _render(BY_NAME["price_change"].build(revision=0))
    # Read the monitored node itself: the recommendations block contains other
    # price-shaped numbers (96.00 is one of them), so a whole-page substring
    # check would be ambiguous.
    assert price_node(baseline) == "128.50"
    assert price_node(priced) == "96.00"
    assert baseline.count('id="current-price"') == priced.count('id="current-price"') == 1


def test_static_html_ships_skeletons_and_no_ready_marker() -> None:
    html = _render()
    # The review list is client-rendered; the shell must not pretend to be
    # ready, otherwise a broken /api/data path would go unnoticed.
    assert 'data-ready="true"' not in html
    assert "review-skeleton" in html
    assert '<span id="reviews-status" data-state="pending">' in html


def test_page_carries_revision_for_correlation() -> None:
    state = State(business=DEFAULT_STATE.business, revision=7)
    html = render_product(state)
    assert 'data-revision="7"' in html
    assert 'data-sku="FX-COF-GUJI-1KG"' in html


def test_specs_and_highlights_are_rendered() -> None:
    html = _render()
    assert "Ethiopia, Guji zone" in html
    assert "Roasted to order" in html
    assert html.count("<tr>") >= 7


@pytest.mark.parametrize("status", ["in_stock", "low_stock", "out_of_stock", "preorder"])
def test_every_stock_state_renders_a_label(status: str) -> None:
    product = DEFAULT_STATE.business.product.model_copy(update={"stock_status": status})
    business = DEFAULT_STATE.business.model_copy(update={"product": product})
    html = render_product(State(business=business))
    match = re.search(r'<span id="stock-status">([^<]+)</span>', html)
    assert match is not None
    assert match.group(1).strip()


def test_out_of_stock_disables_the_cart_button() -> None:
    product = DEFAULT_STATE.business.product.model_copy(
        update={"stock_status": "out_of_stock", "stock_count": 0}
    )
    business = DEFAULT_STATE.business.model_copy(update={"product": product})
    html = render_product(State(business=business))
    assert 'id="add-to-cart" disabled' in html


def test_rating_follows_the_data() -> None:
    html = _render(BY_NAME["rating_change"].build(revision=0))
    assert '<span class="rating-value" id="rating-value">3.20</span>' in html
    assert "131 reviews" in html


def test_discount_and_derived_prices_follow_the_current_price() -> None:
    html = _render()
    # 128.50 of 199.00 is 35% off; per-100 g is a tenth; instalments a quarter.
    assert "35% off" in html
    assert "12.85" in html
    assert "32.12" in html


def test_every_asset_referenced_by_the_page_is_packaged() -> None:
    """The wheel `include` list must cover every local asset the page links.

    This bit us once: `shop.css` and `img/*.svg` were added to the page but not
    to `pyproject.toml`, so the production image served an unstyled page while
    the dev container looked fine.
    """
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    forced = wheel.get("force-include", {})

    html = _render()
    assets = {
        match.group(1) for match in re.finditer(r'(?:src|href)="(/static/assets/[^"]+)"', html)
    }
    assert assets, "the page should reference local assets"

    # Assets live in web/targets and reach the wheel through force-include; a
    # file that is not force-included is absent from the production image.
    for path in assets:
        source = root / "web" / "targets" / path.removeprefix("/static/")
        assert source.is_file(), f"{path} does not exist under web/targets"
        relative = str(source.relative_to(root))
        assert any(relative.startswith(prefix) for prefix in forced), (
            f"{path} is not covered by force-include ({sorted(forced)})"
        )
