"""How `meetingbot.config` must resolve paths inside the PyInstaller sidecar.

The macOS app ships the Python pipeline frozen into `MB.app/Contents/Resources`,
where the package sits under `_internal/` and the repo layout does not exist. That
path was never exercised by the suite, and two defects shipped in the 1.0.0 DMG:
`prompts/` resolved inside `_internal` (so every summary raised FileNotFoundError)
and the default notes directory pointed inside the read-only signed bundle.

These tests reload the module with the PyInstaller markers set, which is the only
way to exercise its import-time constants.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from meetingbot import config as real_config


@pytest.fixture
def frozen_config(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ModuleType]:
    """`meetingbot.config` as it loads inside the frozen sidecar."""
    meipass = Path(str(tmp_path)) / "_MEIPASS"
    (meipass / "prompts").mkdir(parents=True)
    (meipass / "prompts" / "meeting_summary.md").write_text("{{TRANSCRIPT}}")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.delenv("MBOT_NOTES_DIR", raising=False)
    monkeypatch.delenv("MBOT_AUDIOCAP", raising=False)

    try:
        yield importlib.reload(real_config)
    finally:
        # Other tests import the module-level constants; restore the source layout.
        monkeypatch.undo()
        importlib.reload(real_config)


def test_prompts_come_from_the_bundle(frozen_config: ModuleType) -> None:
    """Templates are --add-data payloads, unpacked to _MEIPASS — not repo-relative."""
    unpacked = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    assert unpacked == frozen_config.RESOURCE_ROOT
    template = frozen_config.resolve_template("default")
    assert template.exists(), "the bundled default prompt must be readable"
    assert template.read_text() == "{{TRANSCRIPT}}"


def test_notes_default_outside_the_app_bundle(frozen_config: ModuleType) -> None:
    """The signed bundle is read-only, so notes cannot default inside it."""
    assert frozen_config.NOTES_DIR == frozen_config.DATA_DIR / "notes"
    assert frozen_config.RESOURCE_ROOT not in frozen_config.NOTES_DIR.parents


def test_audiocap_is_not_looked_for_in_the_package(frozen_config: ModuleType) -> None:
    """`mac/.build/release/audiocap` does not exist in a bundle; the app captures
    in-process instead, so the default points beside the frozen executable."""
    beside_executable = Path(sys.executable).resolve().parent / "audiocap"
    assert beside_executable == frozen_config.AUDIOCAP_BIN


def test_source_checkout_is_unchanged() -> None:
    """The non-frozen defaults keep working — this is the developer path."""
    assert real_config.FROZEN is False
    assert real_config.RESOURCE_ROOT == real_config.PROJECT_ROOT
    assert real_config.resolve_template("default").exists()
