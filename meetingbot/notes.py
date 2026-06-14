"""Markdown note writing + SQLite FTS5 index for search."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config

PLACEHOLDER_SUMMARY = (
    "_Not summarized yet — set NVIDIA_API_KEY (free key from https://build.nvidia.com) "
    "and run `mbot summarize` to generate notes from the transcript below._"
)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "meeting"


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return "?"
    m = int(seconds) // 60
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def note_path_for(meta: dict[str, Any]) -> Path:
    started = datetime.fromisoformat(meta["started_at"])
    title = meta.get("title") or f"Meeting {started:%b %-d %H:%M}"
    return config.NOTES_DIR / f"{started:%Y-%m-%d-%H%M}-{slugify(title)}.md"


def write_note(meta: dict[str, Any], summary_md: str, transcript_md: str) -> Path:
    started = datetime.fromisoformat(meta["started_at"])
    title = meta.get("title") or f"Meeting {started:%b %-d %H:%M}"
    path = note_path_for(meta)
    config.NOTES_DIR.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        f"title: {title}\n"
        f"date: {started.isoformat(timespec='seconds')}\n"
        f"duration: {format_duration(meta.get('duration_s'))}\n"
        f"session: {meta.get('session_dir', '')}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{summary_md.strip()}\n\n"
        "## Transcript\n\n"
        f"{transcript_md.strip()}\n"
    )
    path.write_text(body)
    index_note(path, title, started.isoformat(timespec="seconds"), summary_md, transcript_md)
    return path


def _db() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(title, date, path, body)")
    return con


def index_note(path: Path, title: str, date: str, summary: str, transcript: str) -> None:
    con = _db()
    try:
        con.execute("DELETE FROM notes WHERE path = ?", (str(path),))
        con.execute(
            "INSERT INTO notes (title, date, path, body) VALUES (?, ?, ?, ?)",
            (title, date, str(path), summary + "\n" + transcript),
        )
        con.commit()
    finally:
        con.close()


def _fts_query(query: str) -> str:
    """Turn free text (incl. natural-language questions) into a safe FTS5 MATCH.

    Each word becomes a quoted literal OR-joined for recall, so punctuation like
    '?' or ':' can't trip FTS5's query syntax. Returns "" if there are no words.
    """
    tokens = re.findall(r"\w+", query)
    return " OR ".join(f'"{t}"' for t in tokens)


def search(query: str, limit: int = 10) -> list[dict[str, str]]:
    match = _fts_query(query)
    if not match:
        return []
    con = _db()
    try:
        rows = con.execute(
            "SELECT title, date, path, snippet(notes, 3, '**', '**', '…', 12) "
            "FROM notes WHERE notes MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
    finally:
        con.close()
    return [{"title": r[0], "date": r[1], "path": r[2], "snippet": r[3]} for r in rows]


def list_notes() -> list[Path]:
    if not config.NOTES_DIR.exists():
        return []
    return sorted(config.NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
