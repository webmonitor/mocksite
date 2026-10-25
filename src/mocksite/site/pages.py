"""Catalogue of target pages and their stable selectors (README §3.3).

Single source of truth for the admin UI's "target pages" panel and for any
script that needs to know which selector belongs to which page. Pages that are
not implemented yet are listed with ``implemented=False`` so the UI can show
them as planned instead of pretending they work.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Selector:
    label: str
    css: str
    xpath: str


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
)
LIST_READY = Selector(
    label="列表就绪标记",
    css='#app[data-ready="true"]',
    xpath='//*[@id="app" and @data-ready="true"]',
)
LIST_ROWS = Selector(
    label="列表行",
    css="#inventory tbody tr.item",
    xpath=(
        "//*[@id=\"inventory\"]/tbody/tr[contains(concat(' ', normalize-space(@class), ' '),"
        " ' item ')]"
    ),
)
ROW_PRICE = Selector(
    label="行内价格（相对当前行）",
    css="td.price",
    xpath=".//td[contains(concat(' ', normalize-space(@class), ' '), ' price ')]",
)
LOAD_MORE = Selector(
    label="下一页按钮",
    css="#load-more",
    xpath='//*[@id="load-more"]',
)

PAGES: tuple[TargetPage, ...] = (
    TargetPage(
        path="/static/product",
        purpose="状态提交时预渲染的完整 HTML，无 JS；HTTP 提取基线",
        implemented=True,
        selectors=(PRODUCT_PRICE,),
    ),
    TargetPage(
        path="/ssr/product",
        purpose="每次请求按当前状态渲染的完整 HTML，无 JS",
        implemented=True,
        selectors=(PRODUCT_PRICE,),
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
        purpose="当前商品与列表的 JSON 数据；前端数据源与人工核对",
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
                {"label": selector.label, "css": selector.css, "xpath": selector.xpath}
                for selector in page.selectors
            ],
        }
        for page in PAGES
    ]
