"""Packaging invariants: the installed metadata and the package must agree."""

from importlib.metadata import version

import mocksite


def test_installed_metadata_matches_package_version() -> None:
    assert version("mocksite") == mocksite.__version__
