"""HTML rendering for the notice page.

Everything a page needs is computed here, once, from an immutable
:class:`~mocksite.state.models.State`. Templates stay dumb: they render values
and never derive them, so a collector sees exactly what the state says.

The page is modelled on real Chinese university notice portals
(``notice.xidian.edu.cn``, ``notice.ysu.edu.cn``). Two properties matter for a
collector and are reproduced on purpose:

* **one instant, several renderings.** ``published_at`` is a single field; the
  page shows it as a date badge (``10月20日``), a full Chinese date
  (``2026年10月20日``) and a minute-precision timestamp
  (``2026-10-20 14:32``). All three are derived, so they can never disagree —
  and a collector that grabs the wrong one still reads a *plausible* value.
* **click count is client-rendered.** ``#view-count`` is empty in the static
  HTML and filled by the page script, like the portal's ``_showDynClicks``.
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


#: Status labels a portal shows instead of a raw enum.
STATUS_LABELS = {
    "published": "已发布",
    "withdrawn": "已撤回",
}

#: Column navigation and footer links are fixed page chrome, not content.
COLUMNS = (
    {"label": "学校通知", "path": "/static/notice"},
    {"label": "部门通知", "path": "/ssr/notice"},
    {"label": "历史公告", "path": "/static/notice"},
    {"label": "信息公开", "path": "/static/notice"},
)

RELATED_LINKS = (
    "信息公告",
    "OA系统",
    "一网通办",
    "网络服务",
)


def _money(value: Decimal) -> str:
    """Fixed two-decimal rendering, like a published fee schedule."""
    return f"{value:.2f}"


def date_parts(published_at: str) -> dict[str, str]:
    """Split ``YYYY-MM-DD HH:MM`` into the portal's three renderings.

    A single stored instant drives all of them; nothing here reads the clock,
    so a render is reproducible.
    """
    day, _, clock = published_at.partition(" ")
    year, month, dom = day.split("-")
    return {
        "badge_day": f"{int(month)}月{int(dom)}日",
        "badge_year": f"{year}年",
        "full_date": f"{year}年{int(month)}月{int(dom)}日",
        "timestamp": published_at,
        "iso_date": day,
        "clock": clock,
    }


def _context(state: State) -> dict[str, object]:
    notice = state.business.notice
    current = notice.current_fee
    previous = notice.previous_fee

    change_percent = 0
    if previous > 0 and current < previous:
        change_percent = round((previous - current) / previous * 100)
    savings = _money(previous - current) if previous > current else _money(Decimal(0))

    return {
        "revision": state.revision,
        "columns": COLUMNS,
        "related_links": RELATED_LINKS,
        "attachments": notice.attachments,
        "dates": date_parts(notice.published_at),
        "change_percent": change_percent,
        "savings": savings,
        # 30-minute billing unit after the first hour: a quarter of the headline fee.
        "unit_fee": _money(current / 4),
        # Daily cap: a tenth of the headline fee.
        "cap_fee": _money(current / 10),
        "status_label": STATUS_LABELS[notice.status],
        "body_paragraphs": notice.body,
        "notice": {
            "id": notice.id,
            "title": notice.title,
            "department": notice.department,
            "doc_no": notice.doc_no,
            "category": notice.category,
            # Decimal -> str keeps the exact decimal representation.
            "current_fee": _money(current),
            "previous_fee": _money(previous),
            "currency": notice.currency,
            "published_at": notice.published_at,
            "effective_date": notice.effective_date,
            "status": notice.status,
            "view_count": notice.view_count,
            "prev_title": notice.prev_title,
            "next_title": notice.next_title,
        },
    }


def render_notice(state: State) -> str:
    """Complete HTML for ``/static/notice`` and ``/ssr/notice``."""
    return _environment().get_template("notice.html").render(**_context(state))
