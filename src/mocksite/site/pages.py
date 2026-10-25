"""Catalogue of target pages and their stable selectors (README §3.3).

Single source of truth for the admin UI's "target pages" panel and for any
script that needs to know which selector belongs to which page. Pages that are
not implemented yet are listed with ``implemented=False`` so the UI can show
them as planned instead of pretending they work.

Selectors are grouped by role, because the product page has *several*
price-shaped nodes: a collector must know which one is the price to monitor.

The DOM shape of every page is fixed — scenarios change data only — so there is
no "this selector breaks under scenario X" note anywhere in this catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass

#: How important a selector is for a typical verification run.
SelectorRole = str

ROLE_PRIMARY = "primary"
ROLE_READY = "ready"
ROLE_SUPPORTING = "supporting"
ROLE_DECOY = "decoy"


@dataclass(frozen=True, slots=True)
class Selector:
    label: str
    css: str
    xpath: str
    role: SelectorRole = ROLE_PRIMARY
    #: Why this node matters, or why it is a trap. Shown in the admin UI.
    note: str = ""


@dataclass(frozen=True, slots=True)
class TargetPage:
    path: str
    purpose: str
    implemented: bool
    selectors: tuple[Selector, ...] = ()


PRODUCT_PRICE = Selector(
    label="商品现价",
    css="#product #current-price",
    xpath='//*[@id="product"]//*[@id="current-price"]',
    role=ROLE_PRIMARY,
    note="唯一应当监控的价格节点。",
)
PRODUCT_NAME = Selector(
    label="商品名称",
    css="#product #product-name",
    xpath='//*[@id="product"]//*[@id="product-name"]',
    role=ROLE_SUPPORTING,
    note="标题文本，含品牌与规格。",
)
PRODUCT_SKU = Selector(
    label="商品 SKU",
    css="#product-sku",
    xpath='//*[@id="product-sku"]',
    role=ROLE_SUPPORTING,
)
PRODUCT_STOCK = Selector(
    label="库存状态",
    css="#stock-status",
    xpath='//*[@id="stock-status"]',
    role=ROLE_SUPPORTING,
    note="文本随库存枚举变化；父节点 data-stock 给出机器可读值。",
)
PRODUCT_RATING = Selector(
    label="评分（数字）",
    css="#product #rating-value",
    xpath='//*[@id="product"]//*[@id="rating-value"]',
    role=ROLE_SUPPORTING,
    note="十进制字符串；不要从星级字符反推。",
)
PRODUCT_REVIEW_COUNT = Selector(
    label="评价总数",
    css="#review-count",
    xpath='//*[@id="review-count"]',
    role=ROLE_SUPPORTING,
)
PRODUCT_ORIGINAL_PRICE = Selector(
    label="原价（划线价）",
    css="#product #original-price",
    xpath='//*[@id="product"]//*[@id="original-price"]',
    role=ROLE_DECOY,
    note="诱饵：也是价格形状，但语义是原价，不是当前价。",
)
PRODUCT_INSTALLMENT = Selector(
    label="分期价",
    css=".installment-price strong",
    xpath='//*[contains(@class,"installment-price")]//strong',
    role=ROLE_DECOY,
    note="诱饵：分期每期金额，数值约为现价的 1/4。",
)
PRODUCT_UNIT_PRICE = Selector(
    label="单位价",
    css=".unit-price strong",
    xpath='//*[contains(@class,"unit-price")]//strong',
    role=ROLE_DECOY,
    note="诱饵：每 100 g 单价，数值约为现价的 1/10。",
)
PRODUCT_MSRP = Selector(
    label="标价（List price）",
    css=".msrp-price",
    xpath='//*[contains(@class,"msrp-price")]',
    role=ROLE_DECOY,
    note="诱饵：整段文本里同时含原价与节省金额。",
)
PRODUCT_SPECS = Selector(
    label="规格表行",
    css="#specs .spec-table tbody tr",
    xpath='//*[@id="specs"]//tbody/tr',
    role=ROLE_SUPPORTING,
    note="每行 th=标签、td=值。",
)
PRODUCT_HIGHLIGHTS = Selector(
    label="卖点列表",
    css="#product .highlights li",
    xpath='//*[@id="product"]//*[contains(@class,"highlights")]/li',
    role=ROLE_SUPPORTING,
)
PRODUCT_GALLERY = Selector(
    label="主图",
    css="#gallery-image",
    xpath='//*[@id="gallery-image"]',
    role=ROLE_SUPPORTING,
)
REVIEWS_READY = Selector(
    label="评价区就绪标记",
    css='#reviews[data-ready="true"]',
    xpath='//*[@id="reviews" and @data-ready="true"]',
    role=ROLE_READY,
    note="只有第一页评价真正渲染后才会出现；静态 HTML 里是骨架屏。",
)
REVIEWS_LIST = Selector(
    label="评价条目",
    css="#reviews-list li.review-item",
    xpath=(
        '//*[@id="reviews-list"]/li[contains(concat(" ", normalize-space(@class), " "),'
        ' " review-item ")]'
    ),
    role=ROLE_PRIMARY,
)
REVIEWS_MORE = Selector(
    label="加载更多评价按钮",
    css="#load-more-reviews",
    xpath='//*[@id="load-more-reviews"]',
    role=ROLE_SUPPORTING,
    note="末页后 hidden；加载中 disabled。",
)

LIST_READY = Selector(
    label="列表就绪标记",
    css='#app[data-ready="true"]',
    xpath='//*[@id="app" and @data-ready="true"]',
    role=ROLE_READY,
    note="数据加载并渲染完成后才设置；失败时不设置。",
)
LIST_ROWS = Selector(
    label="列表行",
    css="#inventory tbody tr.item",
    xpath=(
        "//*[@id=\"inventory\"]/tbody/tr[contains(concat(' ', normalize-space(@class), ' '),"
        " ' item ')]"
    ),
    role=ROLE_PRIMARY,
    note="data-id 属性保存稳定业务 ID。",
)
ROW_PRICE = Selector(
    label="行内价格（相对当前行）",
    css="td.price",
    xpath=".//td[contains(concat(' ', normalize-space(@class), ' '), ' price ')]",
    role=ROLE_PRIMARY,
)
LOAD_MORE = Selector(
    label="下一页按钮",
    css="#load-more",
    xpath='//*[@id="load-more"]',
    role=ROLE_SUPPORTING,
)

PAGES: tuple[TargetPage, ...] = (
    TargetPage(
        path="/static/product",
        purpose=(
            "真实电商详情页：图库、多重价格节点、库存、变体、规格、懒加载评价；"
            "状态提交时预渲染，无 JS 也能拿到主内容"
        ),
        implemented=True,
        selectors=(
            PRODUCT_PRICE,
            PRODUCT_NAME,
            PRODUCT_SKU,
            PRODUCT_STOCK,
            PRODUCT_RATING,
            PRODUCT_REVIEW_COUNT,
            PRODUCT_ORIGINAL_PRICE,
            PRODUCT_INSTALLMENT,
            PRODUCT_UNIT_PRICE,
            PRODUCT_MSRP,
            PRODUCT_SPECS,
            PRODUCT_HIGHLIGHTS,
            PRODUCT_GALLERY,
            REVIEWS_READY,
            REVIEWS_LIST,
            REVIEWS_MORE,
        ),
    ),
    TargetPage(
        path="/ssr/product",
        purpose="同一份商品详情页，每次请求按当前状态渲染（对比静态预渲染）",
        implemented=True,
        selectors=(PRODUCT_PRICE, PRODUCT_NAME, REVIEWS_READY, REVIEWS_LIST),
    ),
    TargetPage(
        path="/react/list",
        purpose="React 在浏览器中拉取并渲染列表；验证 JS 执行与就绪等待",
        implemented=True,
        selectors=(LIST_READY, LIST_ROWS, ROW_PRICE),
    ),
    TargetPage(
        path="/vue/list",
        purpose="同一组列表数据在 Vue 下渲染",
        implemented=True,
        selectors=(LIST_READY, LIST_ROWS, ROW_PRICE),
    ),
    TargetPage(
        path="/dynamic/deals",
        purpose="首屏一页，点击“加载更多”追加下一页；验证分页聚合与结束判断",
        implemented=True,
        selectors=(LIST_READY, LIST_ROWS, ROW_PRICE, LOAD_MORE),
    ),
    TargetPage(
        path="/api/data",
        purpose="当前商品、列表与评价的 JSON 数据；前端数据源与人工核对",
        implemented=True,
    ),
    TargetPage(
        path="/api/reviews",
        purpose="评价分页 JSON（?page=N），便于不经 DOM 分页验证",
        implemented=True,
    ),
    TargetPage(
        path="/health",
        purpose="进程存活；不受场景故障影响",
        implemented=True,
    ),
)


def pages_document(site_origin: str, site_public_origin: str) -> list[dict[str, object]]:
    """Wire form for the admin UI: both URLs per page, never just one."""
    return [
        {
            "path": page.path,
            "purpose": page.purpose,
            "implemented": page.implemented,
            "collect_url": f"{site_origin}{page.path}",
            "preview_url": f"{site_public_origin}{page.path}",
            "selectors": [
                {
                    "label": selector.label,
                    "css": selector.css,
                    "xpath": selector.xpath,
                    "role": selector.role,
                    "note": selector.note,
                }
                for selector in page.selectors
            ],
        }
        for page in PAGES
    ]
