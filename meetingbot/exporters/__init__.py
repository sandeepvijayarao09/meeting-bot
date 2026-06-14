"""Pluggable export targets for finished meeting notes.

`markdown` is always written (it is the local source of truth and what the search
index reads). Additional targets are opt-in via MBOT_EXPORTERS, e.g.:

    MBOT_EXPORTERS=markdown,apple_notes
"""

from __future__ import annotations

from typing import Any

from .apple_notes import AppleNotesExporter
from .base import Exporter, ExporterError, ExportResult, NeedsSetupError
from .google_docs import GoogleDocsExporter
from .markdown_file import MarkdownFileExporter

__all__ = [
    "ExportResult",
    "Exporter",
    "ExporterError",
    "NeedsSetupError",
    "all_targets",
    "configured_targets",
    "get",
    "run_exports",
]

_REGISTRY: dict[str, Exporter] = {
    e.name: e for e in (MarkdownFileExporter(), AppleNotesExporter(), GoogleDocsExporter())
}


def get(name: str) -> Exporter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ExporterError(
            f"unknown export target '{name}' (have: {', '.join(_REGISTRY)})"
        ) from None


def all_targets() -> list[str]:
    return list(_REGISTRY)


def configured_targets() -> list[str]:
    """Targets from MBOT_EXPORTERS, always including markdown first."""
    from .. import config

    names = [n.strip() for n in config.EXPORTERS.split(",") if n.strip()]
    ordered = ["markdown"] + [n for n in names if n != "markdown"]
    seen: set[str] = set()
    unique: list[str] = []
    for name in ordered:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def run_exports(
    targets: list[str], meta: dict[str, Any], summary_md: str, transcript_md: str
) -> list[ExportResult]:
    """Export to each target in order. The markdown write must succeed; other
    targets are best-effort and their failures are returned as detail, not raised.
    """
    results: list[ExportResult] = []
    for name in targets:
        exporter = get(name)
        if name != "markdown" and not exporter.available():
            results.append(
                ExportResult(target=name, location="", detail="not configured — skipped")
            )
            continue
        try:
            results.append(exporter.export(meta, summary_md, transcript_md))
        except ExporterError as e:
            if name == "markdown":
                raise
            results.append(ExportResult(target=name, location="", detail=f"failed: {e}"))
    return results
