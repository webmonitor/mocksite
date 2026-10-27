"""The notice page: fixed structure, data-driven values.

Scope note: this site verifies **data** changes only. Page structure never
changes between scenarios, so these tests pin two things:

* the structural invariants a collector depends on (the fee node is unique
  among money-shaped decoys, the execution date is unique among the four date
  renderings, the click counter is client-filled, the body is real paragraphs);
* the fact that *only values* move when data changes.
"""

from __future__ import annotations

import re

import pytest

from mocksite.scenarios.registry import BY_NAME
from mocksite.site.render import date_parts, render_notice
from mocksite.state.models import DEFAULT_STATE, State


def _render(state: State | None = None) -> str:
    return render_notice(state or DEFAULT_STATE)


def test_fee_node_is_unique_but_surrounded_by_decoys() -> None:
    html = _render()
    # Exactly one element may carry the monitored id.
    assert html.count('id="current-fee"') == 1
    # The decoys exist and carry real amounts, so a wrong selector returns data
    # instead of nothing — which is the failure mode worth catching.
    assert "unit-fee" in html
    assert "cap-fee" in html
    assert "previous-fee-note" in html
    assert 'id="previous-fee"' in html
    amounts = re.findall(r"\b\d+\.\d{2}\b", html)
    assert len(amounts) >= 5, "the page should contain several money-shaped values"


def test_execution_date_is_unique_among_the_four_dates() -> None:
    """One instant is rendered three times plus the execution date."""
    html = _render()
    assert html.count('id="effective-date"') == 1
    assert html.count('id="date-badge"') == 1
    assert html.count('id="published-date-cn"') == 1
    assert html.count('id="published-at"') == 1
    assert 'id="effective-date">2026-11-01<' in html


def test_date_renderings_describe_the_same_instant() -> None:
    """The badge, the Chinese date and the timestamp are derived from one field.

    This is the trap a real portal sets: three plausible-looking dates from a
    single publication moment. Deriving them guarantees they never drift.
    """
    parts = date_parts("2026-10-20 14:32")
    assert parts["badge_day"] == "10月20日"
    assert parts["badge_year"] == "2026年"
    assert parts["full_date"] == "2026年10月20日"
    assert parts["timestamp"] == "2026-10-20 14:32"
    assert parts["iso_date"] == "2026-10-20"
    assert parts["clock"] == "14:32"

    html = _render()
    for value in ("10月20日", "2026年10月20日", "2026-10-20 14:32"):
        assert value in html, value


def test_leading_zeroes_are_not_rendered_in_chinese_dates() -> None:
    """`09月05日`, never `09月05日` with the ISO padding intact."""
    parts = date_parts("2026-01-05 08:03")
    assert parts["badge_day"] == "1月5日"
    assert parts["full_date"] == "2026年1月5日"
    # The timestamp keeps its padding: it is the machine-readable form.
    assert parts["timestamp"] == "2026-01-05 08:03"


def test_current_fee_renders_exactly() -> None:
    html = _render()
    assert '<span id="current-fee">128.50</span>' in html
    assert '<span id="previous-fee">199.00</span>' in html
    assert '<span class="fee-currency" id="currency">CNY</span>' in html


def test_structure_is_identical_for_every_scenario() -> None:
    """The whole point of the data-only model: shape never changes."""
    markers = (
        'id="current-fee"',
        'id="previous-fee"',
        'id="effective-date"',
        'id="notice-body"',
        'id="attachments"',
        'id="prev-notice"',
    )
    shapes = {}
    for scenario in BY_NAME.values():
        html = render_notice(scenario.build(revision=0))
        shapes[scenario.name] = tuple(marker for marker in markers if marker in html)
    baseline = shapes["baseline"]
    for name, shape in shapes.items():
        assert shape == baseline, f"{name} changed the page structure"


def test_data_scenarios_move_values_without_moving_structure() -> None:
    def fee_node(html: str) -> str:
        match = re.search(r'<span id="current-fee">([^<]*)</span>', html)
        assert match is not None, "the fee node must always exist"
        return match.group(1)

    baseline = _render()
    priced = _render(BY_NAME["fee_change"].build(revision=0))
    assert fee_node(baseline) == "128.50"
    assert fee_node(priced) == "96.00"
    assert baseline.count('id="current-fee"') == priced.count('id="current-fee"') == 1


def test_click_counter_is_empty_until_the_script_fills_it() -> None:
    """Like the portal's `_showDynClicks`: the server emits no number."""
    html = _render()
    match = re.search(r'<span id="view-count"([^>]*)></span>', html)
    assert match is not None, "the counter node must exist and start empty"
    assert 'data-loaded="false"' in match.group(1)
    assert str(DEFAULT_STATE.business.notice.view_count) not in match.group(0)


def test_page_carries_revision_for_correlation() -> None:
    state = State(business=DEFAULT_STATE.business, revision=7)
    html = render_notice(state)
    assert 'data-revision="7"' in html
    assert 'data-doc-no="校后保〔2026〕42 号"' in html


def test_body_is_real_paragraphs() -> None:
    html = _render()
    body = html.split('id="notice-body"', 1)[1].split("</div>", 1)[0]
    assert body.count("<p>") == len(DEFAULT_STATE.business.notice.body)
    assert "为缓解校园停车压力" in html


def test_attachments_carry_kind_and_size() -> None:
    html = _render()
    assert html.count('class="attachment-item"') == 4
    for kind in ("pdf", "doc", "xls"):
        assert f'data-kind="{kind}"' in html
    assert "校园停车收费标准调整表.pdf" in html


def test_withdrawn_notice_shows_a_banner_and_is_reachable() -> None:
    """A withdrawn notice still renders; the collector must see *why*."""
    html = _render(BY_NAME["notice_withdrawn"].build(revision=0))
    assert 'id="withdrawn-banner"' in html
    assert 'data-status="withdrawn"' in html
    assert "已撤回" in html
    # The body and the fee stay on the page.
    assert 'id="current-fee"' in html


def test_published_notice_has_no_banner() -> None:
    assert "withdrawn-banner" not in _render()


def test_execution_date_follows_the_data_but_publication_does_not() -> None:
    html = _render(BY_NAME["effective_date_shift"].build(revision=0))
    assert 'id="effective-date">2026-12-01<' in html
    assert 'id="published-at">2026-10-20 14:32<' in html
    assert "2026年10月20日" in html


def test_prev_next_titles_are_page_chrome_only() -> None:
    """Navigation titles are decoys: plausible content, not this notice."""
    html = _render()
    assert 'id="prev-notice"' in html
    assert 'id="next-notice"' in html
    body = html.split('id="notice-body"', 1)[1].split('id="attachments"', 1)[0]
    assert "CURA" not in body


def test_derived_fees_follow_the_current_fee() -> None:
    html = _render()
    # 128.50 of 199.00 is 35% down; per-30-min is a quarter; the daily cap a tenth.
    assert "35% 降幅" in html
    assert "32.12" in html
    assert "12.85" in html


@pytest.mark.parametrize("status", ["published", "withdrawn"])
def test_every_status_renders_a_label(status: str) -> None:
    notice = DEFAULT_STATE.business.notice.model_copy(update={"status": status})
    business = DEFAULT_STATE.business.model_copy(update={"notice": notice})
    html = render_notice(State(business=business))
    match = re.search(r'<span id="notice-status">([^<]+)</span>', html)
    assert match is not None
    assert match.group(1).strip()


def test_every_asset_referenced_by_the_page_is_packaged() -> None:
    """The wheel `include` list must cover every local asset the page links.

    This bit us once: the stylesheet and attachment icons were added to the page
    but not to `pyproject.toml`, so the production image served an unstyled page
    while the dev container looked fine.
    """
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    forced = wheel.get("force-include", {})

    html = _render()
    assets = {
        match.group(1)
        for match in re.finditer(r'(?:src|href)="(/static/[^"]+)"', html)
        if not match.group(1).startswith("/static/notice")
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
