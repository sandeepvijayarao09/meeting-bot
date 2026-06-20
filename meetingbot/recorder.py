"""Orchestrates one meeting: capture -> live transcription -> note.

Shared by the CLI and the menu bar app.
"""

import contextlib
import json
import logging
import os
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from . import analytics, capture, config, exporters, notes, summarize, transcribe

log = logging.getLogger(__name__)


def read_meta(session_dir: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((Path(session_dir) / "meta.json").read_text()))


def write_meta(session_dir: Path, meta: dict[str, Any]) -> None:
    (Path(session_dir) / "meta.json").write_text(json.dumps(meta, indent=2))


def _pid_is_meetingbot(pid: int) -> bool:
    """True if `pid` is alive AND looks like a Meeting Bot process.

    Guards against a stale lock whose PID was recycled to an unrelated process
    after a recording was hard-killed (which would otherwise falsely report
    "already recording" and block all future recordings).
    """
    try:
        os.kill(pid, 0)  # raises if the process is gone
    except (OSError, ValueError):
        return False
    try:
        cmd = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return True  # can't introspect — assume the live PID is genuine
    return any(token in cmd for token in ("mbot", "meetingbot", "audiocap"))


def current_recording() -> dict[str, Any] | None:
    """Info about an in-progress recording, if any (cross-process)."""
    if not config.CURRENT_FILE.exists():
        return None
    try:
        info: dict[str, Any] = json.loads(config.CURRENT_FILE.read_text())
        if _pid_is_meetingbot(int(info["pid"])):
            return info
    except (ValueError, KeyError, TypeError):
        pass
    config.CURRENT_FILE.unlink(missing_ok=True)
    return None


def ensure_meta(session_dir: Path, title: str | None = None) -> dict[str, Any]:
    """Guarantee a meta.json exists for a session captured by the native app.

    Native capture (CaptureKit) writes session.json + manifest + WAVs but no
    meta.json. Synthesize one from session.json's start time and the duration
    implied by the manifest, so the rest of the pipeline is source-agnostic.
    """
    session_dir = Path(session_dir)
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        meta = read_meta(session_dir)
        if title:
            meta["title"] = title
            write_meta(session_dir, meta)
        return meta

    started = datetime.now()
    session_json = session_dir / "session.json"
    if session_json.exists():
        # session.json is written by the native capture helper; tolerate it being
        # missing, malformed, or not even a JSON object without crashing.
        with contextlib.suppress(ValueError, KeyError, TypeError, json.JSONDecodeError):
            raw = json.loads(session_json.read_text())
            started = datetime.fromisoformat(raw["started_at"].replace("Z", "+00:00"))
            started = started.astimezone().replace(tzinfo=None)

    entries = transcribe.read_manifest(session_dir)
    duration = max((float(e["end"]) for e in entries), default=0.0)
    meta = {
        "title": title,
        "started_at": started.isoformat(timespec="seconds"),
        "duration_s": round(duration),
        "session_dir": str(session_dir),
        "source": "native-app",
    }
    write_meta(session_dir, meta)
    return meta


def transcript_markdown(session_dir: Path) -> str:
    turns = transcribe.merge_turns(transcribe.load_segments(session_dir))
    return transcribe.format_transcript(turns)


def maybe_diarize(session_dir: Path) -> None:
    """Label individual remote speakers if MBOT_DIARIZE is set. Best-effort:
    a missing model / HF token must never block note creation."""
    from . import diarize

    if not diarize.enabled():
        return
    try:
        n = diarize.diarize_session(session_dir)
        if n:
            log.info("diarized %d speaker(s)", n)
    except Exception as e:  # diarization is optional — never block note creation
        log.warning("diarization skipped: %s", e)


def _write_and_export(
    session_dir: Path, meta: dict[str, Any], summary_md: str, transcript_md: str
) -> Path:
    """Write the local note plus any configured exporters; record results in meta.

    The markdown note is the source of truth (search reads it) and its path is
    returned. Additional targets (Apple Notes, Google Docs) are best-effort.
    """
    if config.ANALYTICS:
        stats = analytics.section(transcribe.load_segments(session_dir))
        if stats:
            summary_md = f"{summary_md.rstrip()}\n\n{stats}"
    results = exporters.run_exports(exporters.configured_targets(), meta, summary_md, transcript_md)
    note_path = Path(next(r.location for r in results if r.target == "markdown"))
    meta["note_path"] = str(note_path)
    meta["exports"] = [
        {"target": r.target, "location": r.location, "detail": r.detail} for r in results
    ]
    write_meta(session_dir, meta)
    return note_path


def build_summary(
    session_dir: Path, meta: dict[str, Any], transcript_md: str, template: str | None = None
) -> str:
    notes_file = session_dir / "notes.txt"
    user_notes = notes_file.read_text() if notes_file.exists() else ""
    started = datetime.fromisoformat(meta["started_at"])
    return summarize.summarize_meeting(
        transcript_md,
        user_notes=user_notes,
        title=meta.get("title") or "",
        date=f"{started:%Y-%m-%d %H:%M}",
        duration=notes.format_duration(meta.get("duration_s")),
        template=template or meta.get("template"),
    )


def summarize_session(session_dir: Path, template: str | None = None) -> Path:
    """(Re)generate the summary + note for a finished session. Needs the API key."""
    session_dir = Path(session_dir)
    maybe_diarize(session_dir)
    meta = read_meta(session_dir)
    transcript_md = transcript_markdown(session_dir)
    if not transcript_md:
        raise RuntimeError(
            f"no transcript in {session_dir} — run `mbot transcribe {session_dir.name}` first"
        )
    summary = build_summary(session_dir, meta, transcript_md, template=template)
    if not meta.get("title"):
        # No calendar/extension title: name the note from its content, like a
        # smart calendar entry, instead of a generic "Meeting Jun 20 14:30".
        generated = summarize.generate_title(summary, transcript_md)
        if generated:
            meta["title"] = generated
    meta["summarized"] = True
    return _write_and_export(session_dir, meta, summary, transcript_md)


def export_session(session_dir: Path, targets: list[str]) -> list[exporters.ExportResult]:
    """Re-run specific export targets for an already-summarized session."""
    session_dir = Path(session_dir)
    meta = read_meta(session_dir)
    transcript_md = transcript_markdown(session_dir)
    if not transcript_md:
        raise RuntimeError(f"no transcript in {session_dir}")
    note_file = config.NOTES_DIR / Path(meta["note_path"]).name if meta.get("note_path") else None
    summary_md = (
        _extract_summary(note_file)
        if note_file and note_file.exists()
        else notes.PLACEHOLDER_SUMMARY
    )
    return exporters.run_exports(targets, meta, summary_md, transcript_md)


def _extract_summary(note_path: Path) -> str:
    """Pull the summary section (between the H1 and '## Transcript') from a note."""
    body = note_path.read_text()
    after_front = body.split("\n---\n", 1)[-1]
    lines = after_front.splitlines()
    out: list[str] = []
    started = False
    for line in lines:
        if line.startswith("# ") and not started:
            started = True
            continue
        if line.strip() == "## Transcript":
            break
        if started:
            out.append(line)
    return "\n".join(out).strip() or notes.PLACEHOLDER_SUMMARY


def finalize_session(
    session_dir: Path, want_summary: bool = True, template: str | None = None
) -> tuple[Path, bool]:
    """Write the note for a finished session. Returns (note_path, summarized?).

    Without an API key the note still gets written with the transcript and a
    placeholder summary, so nothing is ever lost.
    """
    session_dir = Path(session_dir)
    if want_summary and summarize.have_key():
        return summarize_session(session_dir, template=template), True
    maybe_diarize(session_dir)
    meta = read_meta(session_dir)
    transcript_md = transcript_markdown(session_dir)
    meta["summarized"] = False
    note_path = _write_and_export(session_dir, meta, notes.PLACEHOLDER_SUMMARY, transcript_md)
    return note_path, False


def list_sessions() -> list[Path]:
    if not config.SESSIONS_DIR.exists():
        return []
    return sorted(
        (p for p in config.SESSIONS_DIR.iterdir() if (p / "meta.json").exists()),
        reverse=True,
    )


def latest_session() -> Path | None:
    sessions = list_sessions()
    return sessions[0] if sessions else None


def unfinished_sessions() -> list[Path]:
    """Sessions with captured audio (a manifest) that never produced a note —
    e.g. the app was force-quit or crashed mid-meeting. Excludes the session
    currently recording and any already finalized."""
    if not config.SESSIONS_DIR.exists():
        return []
    current = current_recording()
    current_dir = Path(current["session_dir"]).resolve() if current else None
    result: list[Path] = []
    for s in sorted(config.SESSIONS_DIR.iterdir()):
        if not s.is_dir() or not (s / "manifest.jsonl").exists():
            continue
        if current_dir is not None and s.resolve() == current_dir:
            continue
        meta_path = s / "meta.json"
        if meta_path.exists() and read_meta(s).get("note_path"):
            continue  # already finalized
        result.append(s)
    return result


def recover(template: str | None = None) -> list[Path]:
    """Finish every interrupted recording: transcribe + write its note. Returns
    the note paths produced. Safe to call on launch; a no-op when nothing pending."""
    notes_made: list[Path] = []
    for session in unfinished_sessions():
        ensure_meta(session)
        transcribe.transcribe_session(session)
        if not transcript_markdown(session):
            continue  # nothing was actually said; skip empty captures
        note_path, _ = finalize_session(session, want_summary=True, template=template)
        notes_made.append(note_path)
    return notes_made


class Recorder:
    def __init__(
        self,
        title: str | None = None,
        on_segment: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.title = title
        self.on_segment = on_segment
        self.session_dir: Path | None = None
        self.started_at: datetime | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._transcriber: transcribe.LiveTranscriber | None = None

    def start(self) -> Path:
        if current_recording():
            raise RuntimeError("a recording is already in progress (see `mbot status`)")
        self.started_at = datetime.now()
        name = f"{self.started_at:%Y%m%d-%H%M%S}-{notes.slugify(self.title or 'meeting')}"
        self.session_dir = config.SESSIONS_DIR / name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        write_meta(
            self.session_dir,
            {
                "title": self.title,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "session_dir": str(self.session_dir),
            },
        )
        self._proc = capture.start(self.session_dir)
        self._transcriber = transcribe.LiveTranscriber(self.session_dir, on_segment=self.on_segment)
        self._transcriber.start()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.CURRENT_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "session_dir": str(self.session_dir),
                    "started_at": self.started_at.isoformat(timespec="seconds"),
                }
            )
        )
        return self.session_dir

    def capture_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> Path:
        """Stop capture, wait for transcription of remaining chunks."""
        if (
            self._proc is None
            or self._transcriber is None
            or self.session_dir is None
            or self.started_at is None
        ):
            raise RuntimeError("recorder is not running")
        capture.stop(self._proc)
        self._transcriber.finish()
        meta = read_meta(self.session_dir)
        ended = datetime.now()
        meta["ended_at"] = ended.isoformat(timespec="seconds")
        meta["duration_s"] = round((ended - self.started_at).total_seconds())
        write_meta(self.session_dir, meta)
        config.CURRENT_FILE.unlink(missing_ok=True)
        return self.session_dir

    def finalize(self, want_summary: bool = True) -> tuple[Path, bool]:
        if self.session_dir is None:
            raise RuntimeError("recorder has not started")
        return finalize_session(self.session_dir, want_summary)
