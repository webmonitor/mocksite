"""Scenario registry (README §4.2).

Every scenario builds a **complete** target state from the defaults and is
committed in one step, so:

* applying the same scenario twice yields identical business content (only the
  revision moves);
* scenarios never stack — ``price_change`` after ``outage`` clears the fault;
* combination conditions are expressed explicitly through ``PATCH`` instead of
  inventing a scenario per pair.

Scope: this registry covers **data changes and transport faults only**. Page
structure is fixed across every scenario — there is no "node missing" or "id
renamed" preset, because the site verifies what a collector extracts when the
*values* change, not how it reacts to a rewritten DOM.

Each scenario also carries the wording the admin UI shows: a human title, a
one-line "what changes", which data field moves, and a group. The UI never
invents its own copy, so the two can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from mocksite.state.models import (
    DEFAULT_BUSINESS,
    BusinessData,
    Faults,
    Item,
    Product,
    Review,
    State,
)
from mocksite.state.store import StateStore

#: Grouping used by the admin UI to lay scenarios out by intent.
ScenarioGroup = Literal["baseline", "price", "content", "list", "fault"]


@dataclass(frozen=True, slots=True)
class PresetScenario:
    name: str
    description: str
    affects: tuple[str, ...]
    pages: tuple[str, ...]
    business: BusinessData
    faults: Faults = field(default_factory=Faults)
    #: Human-facing copy for the admin UI (Chinese, like the rest of the docs).
    title: str = ""
    #: What a collector observes, in one sentence.
    outcome: str = ""
    #: Which data field a collector should see change.
    data_impact: str = ""
    group: ScenarioGroup = "baseline"
    #: Set when the scenario is meant to be compared against ``baseline``.
    compare_with_baseline: bool = True

    def build(self, revision: int) -> State:
        return State(revision=revision, business=self.business, faults=self.faults)


def _business(
    *,
    current_price: Decimal | None = None,
    item_price: Decimal | None = None,
    items: tuple[Item, ...] | None = None,
    product: Product | None = None,
    reviews: tuple[Review, ...] | None = None,
) -> BusinessData:
    base = product if product is not None else DEFAULT_BUSINESS.product
    if current_price is not None:
        base = base.model_copy(update={"current_price": current_price})
    rows = DEFAULT_BUSINESS.items if items is None else items
    if item_price is not None:
        rows = tuple(
            row.model_copy(update={"price": item_price}) if row.id == "A" else row for row in rows
        )
    update: dict[str, object] = {"product": base, "items": rows}
    if reviews is not None:
        update["reviews"] = reviews
    return DEFAULT_BUSINESS.model_copy(update=update)


_PRODUCT_PAGES = ("/static/product", "/ssr/product")
_LIST_PAGES = ("/react/list", "/vue/list", "/dynamic/deals")
_ALL_PAGES = (*_PRODUCT_PAGES, *_LIST_PAGES, "/api/data")

SCENARIOS: tuple[PresetScenario, ...] = (
    # ---------------- baseline ----------------
    PresetScenario(
        name="baseline",
        description="Default data and normal responses; faults cleared.",
        affects=("business", "faults"),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        title="恢复基线",
        outcome="商品 128.50、列表 A/B/C、评价 5 条，故障全部清除。",
        data_impact="所有字段回到默认值。",
        group="baseline",
        compare_with_baseline=False,
    ),
    PresetScenario(
        name="no_change",
        description="Default business data with a new revision; nothing visible changes.",
        affects=("business", "faults"),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        title="版本推进但内容不变",
        outcome="页面数据与基线完全相同，只有 X-Mocksite-Revision 变化。",
        data_impact="没有任何业务字段变化；用于验证平台不会把版本号当成数据变化。",
        group="baseline",
        compare_with_baseline=False,
    ),
    # ---------------- price ----------------
    PresetScenario(
        name="price_change",
        description="Product current price 128.50 -> 96.00; lists unchanged.",
        affects=("business.product.current_price",),
        pages=_PRODUCT_PAGES,
        business=_business(current_price=Decimal("96.00")),
        title="商品现价下降",
        outcome="现价 128.50 → 96.00，原价与列表不变。",
        data_impact="business.product.current_price；页面上的折扣率与分期金额随之重算。",
        group="price",
    ),
    PresetScenario(
        name="price_increase",
        description="Product current price 128.50 -> 158.00.",
        affects=("business.product.current_price",),
        pages=_PRODUCT_PAGES,
        business=_business(current_price=Decimal("158.00")),
        title="商品现价上涨",
        outcome="现价 128.50 → 158.00，高于原价 199.00 之下的折扣区间。",
        data_impact="business.product.current_price；折扣徽章与单位价同步重算。",
        group="price",
    ),
    PresetScenario(
        name="item_price_change",
        description="Row A price 10.00 -> 12.50 on every list page.",
        affects=("business.items[A].price",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(item_price=Decimal("12.50")),
        title="列表 A 行涨价",
        outcome="列表行 A 的价格 10.00 → 12.50，三个列表页同步。",
        data_impact="business.items[0].price；商品现价不受影响。",
        group="price",
    ),
    # ---------------- content ----------------
    PresetScenario(
        name="stock_out",
        description="Stock status in_stock -> out_of_stock with zero units.",
        affects=("business.product.stock_status", "business.product.stock_count"),
        pages=_PRODUCT_PAGES,
        business=_business(
            product=DEFAULT_BUSINESS.product.model_copy(
                update={"stock_status": "out_of_stock", "stock_count": 0}
            )
        ),
        title="商品缺货",
        outcome="库存状态变为缺货，加入购物车按钮禁用，价格不变。",
        data_impact="business.product.stock_status 与 stock_count。",
        group="content",
    ),
    PresetScenario(
        name="rating_change",
        description="Rating 4.6 -> 3.2 and review count 128 -> 131.",
        affects=("business.product.rating", "business.product.review_count"),
        pages=_PRODUCT_PAGES,
        business=_business(
            product=DEFAULT_BUSINESS.product.model_copy(
                update={"rating": Decimal("3.2"), "review_count": 131}
            )
        ),
        title="评分下降",
        outcome="评分 4.60 → 3.20，评价总数 128 → 131。",
        data_impact="business.product.rating 与 review_count。",
        group="content",
    ),
    PresetScenario(
        name="reviews_empty",
        description="Review list becomes empty; the product and rating are unchanged.",
        affects=("business.reviews",),
        pages=_PRODUCT_PAGES,
        business=_business(reviews=()),
        title="评价清空",
        outcome="评价区正常加载但一条评价也没有，商品数据不变。",
        data_impact="business.reviews 变为空列表；评价数仍由 product.review_count 决定。",
        group="content",
    ),
    PresetScenario(
        name="reviews_grow",
        description="Two more reviews appended; review page size stays 2.",
        affects=("business.reviews",),
        pages=_PRODUCT_PAGES,
        business=_business(
            reviews=(
                *DEFAULT_BUSINESS.reviews,
                Review(
                    id="rev-6",
                    author="Sofia M.",
                    rating=4,
                    date="2026-07-18",
                    title="Good value for the size",
                    body=("The 1 kg bag lasts about a month at two cups a day. Consistent grind."),
                ),
                Review(
                    id="rev-7",
                    author="Tom H.",
                    rating=5,
                    date="2026-07-09",
                    title="Ordered again",
                    body=(
                        "Fourth bag. The roast date on the label is always within a week "
                        "of shipping."
                    ),
                ),
            )
        ),
        title="评价增加",
        outcome="评价从 5 条增至 7 条，分页从 3 页变成 4 页。",
        data_impact="business.reviews 追加两条。",
        group="content",
    ),
    # ---------------- list ----------------
    PresetScenario(
        name="empty_list",
        description="List loads successfully with zero rows.",
        affects=("business.items",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(items=()),
        title="列表为空",
        outcome="列表加载成功但 0 行。",
        data_impact="business.items 变为空列表；页面结构不变。",
        group="list",
    ),
    PresetScenario(
        name="duplicate_rows",
        description="Row A appended once more at the end of the list.",
        affects=("business.items",),
        pages=(*_LIST_PAGES, "/api/data"),
        business=_business(items=(*DEFAULT_BUSINESS.items, DEFAULT_BUSINESS.items[0])),
        title="列表出现重复行",
        outcome="列表末尾多出一条 A 行副本。",
        data_impact="business.items 末尾追加一条 id=A 的重复行。",
        group="list",
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
        title="列表变长，分页增加",
        outcome="列表追加 D、E 两行，页大小仍为 2，从两页变成三页。",
        data_impact="business.items 追加两行；已有行保持稳定。",
        group="list",
    ),
    # ---------------- fault ----------------
    PresetScenario(
        name="outage",
        description="Site pages and /api/data return 500; admin and /health stay up.",
        affects=("faults.kind",),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        faults=Faults(kind="outage"),
        title="站点 500 故障",
        outcome="目标页面与 /api/data 全部返回 500；管理后台与 /health 仍可用。",
        data_impact="没有任何数据可取；用于验证失败记录与恢复路径。",
        group="fault",
    ),
    PresetScenario(
        name="slow_site",
        description="Site pages and /api/data delay 8000ms; admin stays responsive.",
        affects=("faults.delay_ms",),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        faults=Faults(delay_ms=8000),
        title="站点响应缓慢",
        outcome="目标页面与 /api/data 延迟 8000ms；管理后台不受影响。",
        data_impact="数据最终一致；用于验证采集超时配置。",
        group="fault",
    ),
)

BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}

assert len(BY_NAME) == len(SCENARIOS), "duplicate scenario name"


def build_default_store() -> StateStore:
    """A :class:`StateStore` with every preset registered."""
    store = StateStore()
    store.register(*SCENARIOS)
    return store
