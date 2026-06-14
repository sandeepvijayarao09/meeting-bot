"""Default exporter: the local Markdown note (always on, always available)."""

from __future__ import annotations

from typing import Any

from .. import notes
from .base import ExportResult


class MarkdownFileExporter:
    name = "markdown"

    def available(self) -> bool:
        return True

    def export(self, meta: dict[str, Any], summary_md: str, transcript_md: str) -> ExportResult:
        path = notes.write_note(meta, summary_md, transcript_md)
        return ExportResult(target=self.name, location=str(path))
