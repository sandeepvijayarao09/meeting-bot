"""Exporter interface and shared result type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ExportResult:
    """Outcome of one export. `location` is a path, URL, or app reference."""

    target: str
    location: str
    detail: str = ""


class ExporterError(RuntimeError):
    """Raised when an export fails for a reason worth showing the user."""


class NeedsSetupError(ExporterError):
    """Raised when a target is not yet configured (e.g. Google not authorized)."""


@runtime_checkable
class Exporter(Protocol):
    """A destination a finished meeting note can be written to."""

    name: str

    def available(self) -> bool:
        """True if this target can run now (platform present, credentials set)."""

    def export(self, meta: dict[str, Any], summary_md: str, transcript_md: str) -> ExportResult: ...
