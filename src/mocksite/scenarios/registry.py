"""Scenario registry (README §4.2).

Every scenario builds a **complete** target state from the defaults and is
committed in one step, so:

* applying the same scenario twice yields identical business content (only the
  revision moves);
* scenarios never stack — ``fee_change`` after ``title_change`` shows only the fee;
* combination conditions are expressed explicitly through ``PATCH`` instead of
  inventing a scenario per pair.

Scope: this registry covers **data changes only**. Page structure is fixed
across every scenario — there is no "node missing" or "id renamed" preset,
because the site verifies what a collector extracts when the *values* change,
not how it reacts to a rewritten DOM. Transport faults are out of scope too:
a collector's retry/timeout/500 handling is its own contract, and injecting it
here would mix "the input changed" with "the network broke".

The scenarios follow how a real university notice changes after publication:
the fee is revised, the effective date slips, the notice is withdrawn, the title
is amended, or the view counter climbs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from mocksite.state.models import DEFAULT_BUSINESS, BusinessData, Notice, State
from mocksite.state.store import StateStore

#: Grouping used by the admin UI to lay scenarios out by intent.
ScenarioGroup = Literal["baseline", "fee", "content"]


@dataclass(frozen=True, slots=True)
class PresetScenario:
    name: str
    description: str
    affects: tuple[str, ...]
    pages: tuple[str, ...]
    business: BusinessData
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
        return State(revision=revision, business=self.business)


def _business(
    *,
    current_fee: Decimal | None = None,
    notice: Notice | None = None,
) -> BusinessData:
    base = notice if notice is not None else DEFAULT_BUSINESS.notice
    if current_fee is not None:
        base = base.model_copy(update={"current_fee": current_fee})
    return DEFAULT_BUSINESS.model_copy(update={"notice": base})


_NOTICE_PAGES = ("/static/notice", "/ssr/notice")
_ALL_PAGES = (*_NOTICE_PAGES, "/api/views")

SCENARIOS: tuple[PresetScenario, ...] = (
    # ---------------- baseline ----------------
    PresetScenario(
        name="baseline",
        description="默认数据与正常响应。",
        affects=("business",),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        title="恢复基线",
        outcome="现行标准 128.50、点击次数 128、正文六段。",
        data_impact="所有字段回到默认值。",
        group="baseline",
        compare_with_baseline=False,
    ),
    PresetScenario(
        name="no_change",
        description="业务数据不变，仅版本号推进；页面上看不出任何变化。",
        affects=("business",),
        pages=_ALL_PAGES,
        business=DEFAULT_BUSINESS,
        title="版本推进但内容不变",
        outcome="页面数据与基线完全相同，只有 X-Mocksite-Revision 变化。",
        data_impact="没有任何业务字段变化；用于验证平台不会把版本号当成数据变化。",
        group="baseline",
        compare_with_baseline=False,
    ),
    # ---------------- fee ----------------
    PresetScenario(
        name="fee_change",
        description="现行标准 128.50 → 96.00；日期与正文不变。",
        affects=("business.notice.current_fee",),
        pages=_NOTICE_PAGES,
        business=_business(current_fee=Decimal("96.00")),
        title="收费标准下调",
        outcome="现行标准 128.50 → 96.00，原标准与正文不变。",
        data_impact="business.notice.current_fee；页面上的降幅与折算金额随之重算。",
        group="fee",
    ),
    PresetScenario(
        name="fee_increase",
        description="现行标准 128.50 → 158.00。",
        affects=("business.notice.current_fee",),
        pages=_NOTICE_PAGES,
        business=_business(current_fee=Decimal("158.00")),
        title="收费标准上调",
        outcome="现行标准 128.50 → 158.00，高于原标准 199.00 之下的降幅区间。",
        data_impact="business.notice.current_fee；降幅标记与折算金额同步重算。",
        group="fee",
    ),
    # ---------------- content ----------------
    PresetScenario(
        name="notice_withdrawn",
        description="通知状态由已发布变为已撤回，页面保留正文并显示撤回提示。",
        affects=("business.notice.status",),
        pages=_NOTICE_PAGES,
        business=_business(
            notice=DEFAULT_BUSINESS.notice.model_copy(update={"status": "withdrawn"})
        ),
        title="通知撤回",
        outcome="页面顶部出现撤回横幅，状态变为已撤回，正文与标准仍在。",
        data_impact="business.notice.status（状态枚举）；标题、标准与正文不变。",
        group="content",
    ),
    PresetScenario(
        name="effective_date_shift",
        description="执行日期 2026-11-01 → 2026-12-01，发布时间与标准不变。",
        affects=("business.notice.effective_date",),
        pages=_NOTICE_PAGES,
        business=_business(
            notice=DEFAULT_BUSINESS.notice.model_copy(update={"effective_date": "2026-12-01"})
        ),
        title="执行日期推迟",
        outcome="执行日期 2026-11-01 → 2026-12-01；发布时间与时间戳不变。",
        data_impact="business.notice.effective_date；另外三处日期渲染不应被误判为变化。",
        group="content",
    ),
    PresetScenario(
        name="title_change",
        description="通知标题被修改，其他字段不变。",
        affects=("business.notice.title",),
        pages=_NOTICE_PAGES,
        business=_business(
            notice=DEFAULT_BUSINESS.notice.model_copy(
                update={"title": "关于调整校园停车收费标准的补充通知"}
            )
        ),
        title="标题修改",
        outcome="标题末尾增加“补充”字样；标准、日期与正文不变。",
        data_impact="business.notice.title；用于验证标题提取而不是整页文本比对。",
        group="content",
    ),
    PresetScenario(
        name="view_count_grow",
        description="点击次数 128 → 1531，正文与标准不变。",
        affects=("business.notice.view_count",),
        pages=_NOTICE_PAGES,
        business=_business(
            notice=DEFAULT_BUSINESS.notice.model_copy(update={"view_count": 1531})
        ),
        title="点击次数增长",
        outcome="点击次数 128 → 1531；正文、标准、日期全部不变。",
        data_impact="business.notice.view_count；点击次数由脚本异步填充，不应被当成内容变化。",
        group="content",
    ),
)

BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}

assert len(BY_NAME) == len(SCENARIOS), "duplicate scenario name"


def build_default_store() -> StateStore:
    """A :class:`StateStore` with every preset registered."""
    store = StateStore()
    store.register(*SCENARIOS)
    return store
