"""Rendered list shells: asset wiring, no server-rendered rows, no CDN."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mocksite.site.render import VENDOR_REACT, VENDOR_VUE, render_deals, render_list
from mocksite.state.models import DEFAULT_STATE

ASSETS = Path(__file__).parents[2] / "web" / "targets"


@pytest.mark.parametrize(
    ("framework", "vendor", "script"),
    [("react", VENDOR_REACT, "react-list.js"), ("vue", VENDOR_VUE, "vue-list.js")],
)
def test_list_shell_loads_shared_then_page_script(
    framework: str, vendor: tuple[str, ...], script: str
) -> None:
    html = render_list(DEFAULT_STATE, framework)
    # Order matters: the shared helper defines window.MocksiteList, and the
    # page script fails immediately without it.
    assert html.index("/static/shared/list.js") < html.index(f"/static/{framework}/{script}")
    for asset in vendor:
        assert f"/static/{framework}/{asset}" in html


def test_list_shell_has_no_rows() -> None:
    """Server-rendered rows would hide a broken client data path."""
    for framework in ("react", "vue"):
        html = render_list(DEFAULT_STATE, framework)
        assert "<tbody>" not in html
        assert "Alpha" not in html
        assert "128.50" not in html


def test_list_shell_never_marks_ready() -> None:
    for html in (
        render_list(DEFAULT_STATE, "react"),
        render_list(DEFAULT_STATE, "vue"),
        render_deals(DEFAULT_STATE),
    ):
        assert "data-ready" not in html
        assert "data-revision" not in html


def test_list_shell_passes_page_size() -> None:
    state = DEFAULT_STATE.model_copy(
        update={"business": DEFAULT_STATE.business.model_copy(update={"page_size": 3})}
    )
    html = render_list(state, "react")
    payload = json.loads(
        html.split('<script id="mocksite-config" type="application/json">', 1)[1].split(
            "</script>", 1
        )[0]
    )
    assert payload == {"pageSize": 3}


def test_unknown_framework_rejected() -> None:
    with pytest.raises(ValueError, match="unknown framework"):
        render_list(DEFAULT_STATE, "svelte")


def test_deals_shell_loads_shared_then_page_script() -> None:
    html = render_deals(DEFAULT_STATE)
    assert html.index("/static/shared/list.js") < html.index("/static/shared/deals.js")


def test_no_external_asset_references() -> None:
    """Offline requirement: nothing may point at a CDN or absolute origin."""
    for html in (
        render_list(DEFAULT_STATE, "react"),
        render_list(DEFAULT_STATE, "vue"),
        render_deals(DEFAULT_STATE),
    ):
        assert "http://" not in html
        assert "https://" not in html
        assert "//cdn" not in html


def test_vendor_manifest_matches_shipped_files() -> None:
    import base64
    import hashlib

    manifest = json.loads((ASSETS / "manifest.json").read_text())
    assert manifest["assets"], "manifest must list the vendored bundles"
    for asset in manifest["assets"]:
        framework = "react" if asset["package"].startswith("react") else "vue"
        data = (ASSETS / framework / asset["file"]).read_bytes()
        digest = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        assert digest == asset["sha512"], asset["file"]
        assert len(data) == asset["bytes"], asset["file"]
        assert (ASSETS / framework / asset["license_file"]).is_file(), asset["license_file"]


def test_every_referenced_asset_exists() -> None:
    for html in (
        render_list(DEFAULT_STATE, "react"),
        render_list(DEFAULT_STATE, "vue"),
        render_deals(DEFAULT_STATE),
    ):
        for fragment in html.split('src="')[1:]:
            path = fragment.split('"', 1)[0]
            if not path.startswith("/static/"):
                continue
            assert (ASSETS / path.removeprefix("/static/")).is_file(), path


def test_asset_resolution_prefers_the_packaged_copy() -> None:
    """An installed package must never fall back to the repo checkout.

    The production image deletes ``web/``, so if resolution ever preferred the
    repo path the image would start with "assets not found" instead of serving
    pages. Order is: explicit config, packaged wheel copy, repo checkout.
    """
    from mocksite.site.routes import PACKAGED_ASSETS, REPO_ASSETS, resolve_asset_dir

    # The packaged location sits at the package root, next to `site/`.
    assert PACKAGED_ASSETS.name == "_static"
    assert PACKAGED_ASSETS.parent.name == "mocksite"
    # The repo fallback points at the frontend folder, not at src/.
    assert REPO_ASSETS.parts[-2:] == ("web", "targets")

    # In a source checkout only the repo copy exists, so it is what resolves.
    assert resolve_asset_dir() == REPO_ASSETS


def test_pyproject_force_includes_every_asset_tree() -> None:
    """web/targets is the source of truth; the wheel must pull all three subtrees."""
    import tomllib

    root = Path(__file__).parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    forced = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    for subtree in ("shared", "react", "vue"):
        assert f"web/targets/{subtree}" in forced
    # Everything lands under the package root so `PACKAGED_ASSETS` finds it.
    assert all(target.startswith("mocksite/") for target in forced.values())
    for source in forced:
        assert (root / source).is_dir(), f"{source} is missing"
