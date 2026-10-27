"""Catalogue of target pages and their stable selectors (README §3.3).

Single source of truth for the admin UI's selector reference and for any script
that needs to know which selector belongs to which page. Pages that are not
implemented yet are listed with ``implemented=False`` so the UI can show them as
planned instead of pretending they work.

Selectors are grouped by role, because a real notice page has *several*
money-shaped and date-shaped nodes: a collector must know which one is the fee
to monitor and which of the four dates is the execution date.

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


NOTICE_FEE = Selector(
    label="现行标准",
    css="#notice #current-fee",
    xpath='//*[@id="notice"]//*[@id="current-fee"]',
    role=ROLE_PRIMARY,
    note="唯一应当监控的金额节点。",
)
NOTICE_EFFECTIVE_DATE = Selector(
    label="执行日期",
    css="#notice #effective-date",
    xpath='//*[@id="notice"]//*[@id="effective-date"]',
    role=ROLE_PRIMARY,
    note="唯一决定新标准何时执行的日期；其余三处都是发布时间。",
)
NOTICE_TITLE = Selector(
    label="通知标题",
    css="#notice #notice-title",
    xpath='//*[@id="notice"]//*[@id="notice-title"]',
    role=ROLE_SUPPORTING,
    note="标题文本；正文段落另有节点。",
)
NOTICE_DOC_NO = Selector(
    label="文号",
    css="#notice-doc-no",
    xpath='//*[@id="notice-doc-no"]',
    role=ROLE_SUPPORTING,
)
NOTICE_STATUS = Selector(
    label="通知状态",
    css="#notice-status",
    xpath='//*[@id="notice-status"]',
    role=ROLE_SUPPORTING,
    note="文本随状态枚举变化；父节点 data-status 给出机器可读值。",
)
NOTICE_DEPARTMENT = Selector(
    label="发布单位",
    css="#notice-department",
    xpath='//*[@id="notice-department"]',
    role=ROLE_SUPPORTING,
)
NOTICE_BODY = Selector(
    label="正文段落",
    css="#notice-body p",
    xpath='//*[@id="notice-body"]/p',
    role=ROLE_PRIMARY,
    note="每段一个节点；整页文本比对会被页头页脚干扰。",
)
NOTICE_ATTACHMENTS = Selector(
    label="附件条目",
    css="#attachments .attachment-item",
    xpath='//*[@id="attachments"]//li[contains(@class,"attachment-item")]',
    role=ROLE_SUPPORTING,
    note="链接文本是文件名，父节点 data-kind 给出文件类型。",
)
NOTICE_PREV = Selector(
    label="上一篇标题",
    css="#prev-notice",
    xpath='//*[@id="prev-notice"]',
    role=ROLE_DECOY,
    note="诱饵：也是一条通知标题，但不是当前公告的内容。",
)
NOTICE_PREVIOUS_FEE = Selector(
    label="原标准（划线价）",
    css="#notice #previous-fee",
    xpath='//*[@id="notice"]//*[@id="previous-fee"]',
    role=ROLE_DECOY,
    note="诱饵：也是金额形状，但语义是调整前标准，不是现行标准。",
)
NOTICE_UNIT_FEE = Selector(
    label="折算单位费",
    css=".unit-fee strong",
    xpath='//*[contains(@class,"unit-fee")]//strong',
    role=ROLE_DECOY,
    note="诱饵：每 30 分钟加收金额，数值约为现行标准的 1/4。",
)
NOTICE_CAP_FEE = Selector(
    label="单日封顶",
    css=".cap-fee strong",
    xpath='//*[contains(@class,"cap-fee")]//strong',
    role=ROLE_DECOY,
    note="诱饵：单日累计上限，数值约为现行标准的 1/10。",
)
NOTICE_PREVIOUS_NOTE = Selector(
    label="原标准说明段",
    css=".previous-fee-note",
    xpath='//*[contains(@class,"previous-fee-note")]',
    role=ROLE_DECOY,
    note="诱饵：整段文本里同时含原标准与差额。",
)
NOTICE_BADGE_DATE = Selector(
    label="日期徽章（发布时间）",
    css="#date-badge",
    xpath='//*[@id="date-badge"]',
    role=ROLE_DECOY,
    note="诱饵：'10月20日' 形式，是发布时间，不是执行日期。",
)
NOTICE_PUBLISHED_CN = Selector(
    label="中文发布日期",
    css="#published-date-cn",
    xpath='//*[@id="published-date-cn"]',
    role=ROLE_DECOY,
    note="诱饵：'2026年10月20日'，与徽章同一时刻的另一种渲染。",
)
NOTICE_PUBLISHED_AT = Selector(
    label="发布时间戳",
    css="#published-at",
    xpath='//*[@id="published-at"]',
    role=ROLE_DECOY,
    note="诱饵：'2026-10-20 14:32'，最像执行日期的一处。",
)
VIEW_COUNT = Selector(
    label="点击次数（脚本填充）",
    css='#view-count[data-loaded="true"]',
    xpath='//*[@id="view-count" and @data-loaded="true"]',
    role=ROLE_READY,
    note="静态 HTML 为空，由页面脚本请求 /api/views 后填充；等待它可识别异步计数。",
)

PAGES: tuple[TargetPage, ...] = (
    TargetPage(
        path="/static/notice",
        purpose=(
            "真实高校通知详情页：标题、发布单位、点击次数（脚本异步填充）、"
            "同一时刻的三种日期渲染、正文段落、附件下载、上一篇下一篇；"
            "状态提交时预渲染，无 JS 也能拿到正文"
        ),
        implemented=True,
        selectors=(
            NOTICE_FEE,
            NOTICE_EFFECTIVE_DATE,
            NOTICE_TITLE,
            NOTICE_DOC_NO,
            NOTICE_STATUS,
            NOTICE_DEPARTMENT,
            NOTICE_BODY,
            NOTICE_ATTACHMENTS,
            NOTICE_PREVIOUS_FEE,
            NOTICE_UNIT_FEE,
            NOTICE_CAP_FEE,
            NOTICE_PREVIOUS_NOTE,
            NOTICE_BADGE_DATE,
            NOTICE_PUBLISHED_CN,
            NOTICE_PUBLISHED_AT,
            VIEW_COUNT,
            NOTICE_PREV,
        ),
    ),
    TargetPage(
        path="/ssr/notice",
        purpose="同一份通知详情页，每次请求按当前状态渲染（对比静态预渲染）",
        implemented=True,
        selectors=(NOTICE_FEE, NOTICE_EFFECTIVE_DATE, NOTICE_BODY, VIEW_COUNT),
    ),
    TargetPage(
        path="/api/views",
        purpose="点击次数的 JSON 端点；静态页由脚本异步请求",
        implemented=True,
    ),
    TargetPage(
        path="/health",
        purpose="进程存活；不随业务数据变化",
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
