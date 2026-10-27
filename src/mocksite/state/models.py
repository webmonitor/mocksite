"""Immutable state model for the mock site.

All models are frozen and hashable-by-construction (tuples, not lists), so a
snapshot handed to a request can never be mutated by it. Money amounts are
``Decimal`` in memory and decimal *strings* on the wire: floats never appear
anywhere.

``revision`` is carried on :class:`State` but is never accepted as input; the
store owns it.

The business data models **one university notice** — the shape of
``notice.xidian.edu.cn`` / ``notice.ysu.edu.cn``:

* a notice detail page with 标题 / 发布单位 / 发布时间 / 点击次数 / 正文段落 /
  附件 / 上一篇下一篇, where the same publication instant is rendered in three
  different formats;
* 点击次数 is rendered by the page script, not the server, exactly like the
  portal's ``_showDynClicks``.

There is no notice *list*: the site is a single notice, because that is the one
thing the consumer (WebMonitor) monitors.

Scope: this site verifies **data** changes only. The DOM structure of every page
is fixed; scenarios swap business values. Structural breakage (missing nodes,
renamed ids, empty cells) is deliberately *not* modelled — there is no
presentation-control layer, so a page cannot be made to render a different shape
for the same data. Transport faults are not modelled either: how a collector
behaves on 500s or timeouts is its own test, not a property of the input.
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
MAX_AMOUNT_TEXT = 64
MAX_BODY_PARAGRAPHS = 40

Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
LongText = Annotated[str, Field(min_length=1, max_length=MAX_LONG_TEXT)]
RowId = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
#: Portal timestamps are minute-precision and space-separated, e.g.
#: ``2026-10-20 14:32``. Not RFC 3339: the target pages are Chinese portals.
MinuteTime = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")]


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
    if len(value) > MAX_AMOUNT_TEXT:
        raise ValueError(f"value must be at most {MAX_AMOUNT_TEXT} characters")
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


Amount = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal_string),
    PlainSerializer(lambda value: str(value), return_type=str),
]

#: Lifecycle a real portal exposes; ``withdrawn`` still renders the page so a
#: collector can see the 撤回 banner instead of a 404.
NoticeStatus = Literal["published", "withdrawn"]
AttachmentKind = Literal["pdf", "doc", "xls", "zip"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Attachment(_Frozen):
    """One downloadable attachment. ``src`` is site-relative, never a CDN."""

    id: RowId
    name: Text
    src: Text
    kind: AttachmentKind = "pdf"
    size_text: Text = "1.2 MB"


class Notice(_Frozen):
    """The notice detail page."""

    id: RowId
    title: Text
    department: Text
    doc_no: Text
    category: Text
    current_fee: Amount
    previous_fee: Amount
    currency: Currency
    #: The single source of truth for the publication instant. Every rendered
    #: date is derived from it, so the three formats can never disagree.
    published_at: MinuteTime
    effective_date: IsoDate
    #: Rendered by the page script, like the portal's dynamic click counter.
    view_count: Annotated[StrictInt, Field(ge=0, le=10_000_000)] = 0
    status: NoticeStatus = "published"
    body: Annotated[tuple[LongText, ...], Field(max_length=MAX_BODY_PARAGRAPHS)] = ()
    attachments: Annotated[tuple[Attachment, ...], Field(max_length=20)] = ()
    #: Navigation titles look like content in a naive whole-page diff.
    prev_title: Text = ""
    next_title: Text = ""


class BusinessData(_Frozen):
    """The only thing a collection run should observe as content."""

    notice: Notice


class State(_Frozen):
    revision: Annotated[StrictInt, Field(ge=0)] = 0
    business: BusinessData


DEFAULT_NOTICE = Notice(
    id="notice-54493",
    title="关于调整校园停车收费标准的通知",
    department="后勤保障部",
    doc_no="校后保〔2026〕42 号",
    category="学校通知",
    current_fee=Decimal("128.50"),
    previous_fee=Decimal("199.00"),
    currency="CNY",
    published_at="2026-10-20 14:32",
    effective_date="2026-11-01",
    view_count=128,
    status="published",
    body=(
        (
            "为缓解校园停车压力、规范停车秩序，经2026年第12次校长办公会研究通过，"
            "决定调整校园停车收费标准。现将有关事项通知如下。"
        ),
        (
            "一、调整范围。本次调整适用于长安、雁塔两校区的道路泊位与校内公共停车场，"
            "教工住宅区自有车位不在此次调整范围内。"
        ),
        (
            "二、收费标准。小型车首小时由 199.00 元调整为 128.50 元，首小时后每30分钟"
            "加收 32.12 元；单日累计不超过 12.85 元。中型车、大型车按车型系数另行计收。"
        ),
        "三、执行时间。本通知自 2026 年 11 月 1 日起执行，执行前按原标准计收。",
        (
            "四、其他事项。军车、警车、消防车、救护车等特种车辆按规定免费停放；"
            "新能源汽车继续执行半价优惠。"
        ),
        (
            "请各单位做好宣传解释工作。如有疑问，请联系后勤保障部交通管理科，"
            "电话：029-81891818。"
        ),
    ),
    attachments=(
        Attachment(
            id="att-1",
            name="校园停车收费标准调整表.pdf",
            src="/static/shared/img/attachment-pdf.svg",
            kind="pdf",
            size_text="184 KB",
        ),
        Attachment(
            id="att-2",
            name="2026年第12次校长办公会纪要.pdf",
            src="/static/shared/img/attachment-pdf.svg",
            kind="pdf",
            size_text="312 KB",
        ),
        Attachment(
            id="att-3",
            name="停车收费标准公示回执.doc",
            src="/static/shared/img/attachment-doc.svg",
            kind="doc",
            size_text="96 KB",
        ),
        Attachment(
            id="att-4",
            name="意见征集汇总表.xls",
            src="/static/shared/img/attachment-xls.svg",
            kind="xls",
            size_text="72 KB",
        ),
    ),
    prev_title="关于CURA中国大学生路跑联赛期间临时交通管制的通知",
    next_title="关于举办第二届“百班千人国防尖兵挑战赛”的通知",
)

DEFAULT_BUSINESS = BusinessData(notice=DEFAULT_NOTICE)

DEFAULT_STATE = State(business=DEFAULT_BUSINESS)
