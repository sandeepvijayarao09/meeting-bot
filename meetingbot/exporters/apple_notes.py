"""Apple Notes exporter via AppleScript (`osascript`).

Creates one note per meeting in a folder. If that folder lives in your iCloud
account the note syncs to cloud and your other Apple devices; in an "On My Mac"
account it stays on the device. No API keys or network calls.
"""

from __future__ import annotations

import html
import subprocess
import sys
from datetime import datetime
from typing import Any

from .. import config
from .base import ExporterError, ExportResult
from .mdconvert import to_html


def _osascript(script: str) -> str:
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise ExporterError(f"AppleScript failed: {proc.stderr.strip() or 'unknown error'}")
    return proc.stdout.strip()


def _build_html(meta: dict[str, Any], summary_md: str, transcript_md: str) -> tuple[str, str]:
    started = datetime.fromisoformat(meta["started_at"])
    title = meta.get("title") or f"Meeting {started:%b %-d %H:%M}"
    body = (
        f"<div><h1>{html.escape(title)}</h1>"
        f"<p><i>{started:%Y-%m-%d %H:%M}</i></p>"
        f"{to_html(summary_md)}"
        f"<h2>Transcript</h2>{to_html(transcript_md)}</div>"
    )
    return title, body


def _applescript(folder: str, body_html: str) -> str:
    """Create the note in `folder`, creating the folder if necessary.

    AppleScript string literals escape backslash and double-quote.
    """
    esc = body_html.replace("\\", "\\\\").replace('"', '\\"')
    return f'''
    tell application "Notes"
        if not (exists folder "{folder}") then
            make new folder with properties {{name:"{folder}"}}
        end if
        set theNote to make new note at folder "{folder}" with properties {{body:"{esc}"}}
        return id of theNote
    end tell
    '''


class AppleNotesExporter:
    name = "apple_notes"

    def available(self) -> bool:
        return sys.platform == "darwin"

    def export(self, meta: dict[str, Any], summary_md: str, transcript_md: str) -> ExportResult:
        if not self.available():
            raise ExporterError("Apple Notes export requires macOS")
        _title, body_html = _build_html(meta, summary_md, transcript_md)
        note_id = _osascript(_applescript(config.APPLE_NOTES_FOLDER, body_html))
        return ExportResult(
            target=self.name,
            location=f"Notes ▸ {config.APPLE_NOTES_FOLDER}",
            detail=note_id,
        )
