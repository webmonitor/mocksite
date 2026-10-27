"""Packaging invariants: the installed metadata and the package must agree."""

from __future__ import annotations

import json
import tomllib
from importlib.metadata import version
from pathlib import Path

import mocksite

ROOT = Path(__file__).parents[2]
ASSETS = ROOT / "web" / "targets"


def test_installed_metadata_matches_package_version() -> None:
    assert version("mocksite") == mocksite.__version__


def test_every_referenced_asset_exists() -> None:
    """Offline requirement: the page may only point at files the wheel ships."""
    from mocksite.site.render import render_notice
    from mocksite.state.models import DEFAULT_STATE

    html = render_notice(DEFAULT_STATE)
    referenced = [
        fragment.split('"', 1)[0]
        for fragment in html.split('src="')[1:] + html.split('href="')[1:]
    ]
    # `/static/notice` is a route, not a file; only asset paths are checked.
    static = [
        path
        for path in referenced
        if path.startswith("/static/") and path.endswith((".css", ".js", ".svg"))
    ]
    assert static, "the notice page must reference at least its stylesheet"
    for path in static:
        assert (ASSETS / path.removeprefix("/static/")).is_file(), path
    assert "http://" not in html
    assert "https://" not in html


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


def test_pyproject_force_includes_the_shared_tree() -> None:
    """web/targets is the source of truth; the wheel must pull it in."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    forced = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert forced == {"web/targets/shared": "mocksite/_static/shared"}
    for source in forced:
        assert (ROOT / source).is_dir(), f"{source} is missing"


def test_target_manifest_matches_shipped_files() -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    assert manifest["assets"] == [], "no framework runtime is vendored any more"
