"""Guards that the version strings which must agree actually agree.

The marketing version lives in several files that no build step reconciles, and
they have drifted before: 1.0.1 was cut with `mac/MeetingBot/Info.plist` left at
1.0.0, so `scripts/build-app.sh` — which reads the marketing version out of that
plist — would have stamped and named the release DMG `MB-1.0.0-<build>.dmg`.

Only the pairs that describe the *same* artifact are asserted here. The iOS app
and the Chrome extension version independently on purpose (a Python-only patch
release does not re-version them), so they are deliberately not checked.
"""

from __future__ import annotations

import plistlib
import re
import tomllib
from pathlib import Path

import meetingbot

ROOT = Path(__file__).resolve().parent.parent


def test_package_version_matches_pyproject() -> None:
    """`meetingbot.__version__` is what `pip install` reports."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert meetingbot.__version__ == pyproject["project"]["version"]


def test_macos_plist_matches_xcode_project() -> None:
    """Both macOS build paths — build-app.sh (plist) and xcodegen (project.yml)
    — must stamp the same marketing version into the same app."""
    with (ROOT / "mac" / "MeetingBot" / "Info.plist").open("rb") as fh:
        plist_version = plistlib.load(fh)["CFBundleShortVersionString"]

    project_yml = (ROOT / "mac" / "project.yml").read_text()
    match = re.search(r'^\s*MARKETING_VERSION:\s*"?([^"\s]+)"?\s*$', project_yml, re.M)
    assert match is not None, "MARKETING_VERSION not found in mac/project.yml"

    assert plist_version == match.group(1)


def test_macos_app_version_matches_python_backend() -> None:
    """The macOS app embeds the Python backend as a sidecar, so they ship as one
    unit and share a marketing version."""
    with (ROOT / "mac" / "MeetingBot" / "Info.plist").open("rb") as fh:
        plist_version = plistlib.load(fh)["CFBundleShortVersionString"]

    assert plist_version == meetingbot.__version__
