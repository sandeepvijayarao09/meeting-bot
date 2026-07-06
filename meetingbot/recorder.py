"""Orchestrates one meeting: capture -> live transcription -> note.

Shared by the CLI and the menu bar app.
"""

import contextlib
import json
import logging
import os
import re
import subprocess
import wave
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from . import analytics, capture, config, exporters, notes, refine, summarize, transcribe

log = logging.getLogger(__name__)

# Chunk WAVs are named "<stream>-<index>.wav", e.g. "mic-0001.wav".
_WAV_CHUNK_RE = re.compile(r"^(mic|sys)-(\d+)\.wav$")


def _wav_duration(path: Path) -> float:
    """Seconds of audio in a WAV, read from its header (no full decode)."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, OSError, ZeroDivisionError):
        return 0.0


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
    # Salvage orphaned WAV chunks before anything reads the manifest. The native
    # recorder registers a chunk in the manifest only when it closes, so a meeting
    # shorter than one chunk — or one interrupted before a boundary — leaves WAVs on
    # disk with an empty/missing manifest. Without this, `process` (the app's stop
    # path) finds no audio and fails with "no transcript", silently losing a real
    # recording. Rebuilding here fixes both `process` and `recover` in one place.
    manifest = session_dir / "manifest.jsonl"
    if (not manifest.exists() or manifest.stat().st_size == 0) and any(session_dir.glob("*.wav")):
        _rebuild_manifest(session_dir)
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


def refined_transcript_markdown(session_dir: Path, tier: str | None = None) -> str:
    """Eloquent-style refined transcript used for the note body and the summarizer
    input. Honors ``config.REFINE`` by default; the raw transcript.jsonl is never
    touched (it stays the verbatim source of truth, recoverable via
    `mbot refine --tier off`). Talk-time analytics deliberately stays on the raw
    segments, so it reflects what was actually said."""
    return refine.refine_transcript(session_dir, tier=tier)


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
    if not transcript_markdown(session_dir):  # was anything said? (raw, no cloud cost)
        raise RuntimeError(
            f"no transcript in {session_dir} — run `mbot transcribe {session_dir.name}` first"
        )
    # Refined transcript (Eloquent-style cleanup) feeds both the note body and the
    # summarizer; cleaner input yields cleaner notes. Raw transcript.jsonl is kept.
    transcript_md = refined_transcript_markdown(session_dir)
    if not transcript_md.strip():
        # An all-filler recording refines to nothing even though the raw guard above
        # passed; summarize the raw transcript rather than sending an empty prompt to
        # the model (which would hallucinate a summary from nothing).
        transcript_md = transcript_markdown(session_dir)
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
    # Match the note's refined transcript, but never re-bill the cloud tier on a
    # re-export — downgrade "cloud" to the deterministic local cleanup.
    transcript_md = refined_transcript_markdown(session_dir, tier=refine.noncloud_tier())
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
    # No key: refinement falls back to local (cloud needs a key), so the note's
    # transcript is still cleaned even without summarization.
    transcript_md = refined_transcript_markdown(session_dir)
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
    """Sessions with captured audio that never produced a note — e.g. the app was
    force-quit or crashed mid-meeting. Includes sessions whose manifest is empty
    or missing but that still have orphaned WAV chunks on disk (a crash before the
    first chunk closed). Excludes the session currently recording, ones already
    finalized, and ones we already determined had no speech."""
    if not config.SESSIONS_DIR.exists():
        return []
    current = current_recording()
    current_dir = Path(current["session_dir"]).resolve() if current else None
    result: list[Path] = []
    for s in sorted(config.SESSIONS_DIR.iterdir()):
        if not s.is_dir():
            continue
        has_audio = (s / "manifest.jsonl").exists() or any(s.glob("*.wav"))
        if not has_audio:
            continue
        if current_dir is not None and s.resolve() == current_dir:
            continue
        if (s / "meta.json").exists():
            meta = read_meta(s)
            if meta.get("note_path") or meta.get("recovered_empty"):
                continue  # already finalized, or already known to be silent
        result.append(s)
    return result


def _rebuild_manifest(session_dir: Path) -> None:
    """Reconstruct manifest.jsonl from orphaned WAV chunks on disk.

    The native recorder registers a chunk in the manifest only when the chunk
    closes; a crash/force-quit before that (e.g. a meeting shorter than one chunk)
    leaves WAVs with no manifest entries, which `recover` needs to salvage them.
    Each chunk's start is the cumulative duration of earlier chunks in its stream.
    """
    chunks: dict[str, list[tuple[int, Path]]] = {}
    for wav in session_dir.glob("*.wav"):
        match = _WAV_CHUNK_RE.match(wav.name)
        if match:
            chunks.setdefault(match.group(1), []).append((int(match.group(2)), wav))
    if not chunks:
        return
    entries: list[dict[str, Any]] = []
    for stream, items in chunks.items():
        start = 0.0
        for _idx, wav in sorted(items):
            duration = _wav_duration(wav)
            entries.append(
                {
                    "file": wav.name,
                    "stream": stream,
                    "start": round(start, 2),
                    "end": round(start + duration, 2),
                }
            )
            start += duration
    entries.sort(key=lambda e: (e["start"], e["stream"]))
    with (session_dir / "manifest.jsonl").open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def recover(template: str | None = None) -> list[Path]:
    """Finish every interrupted recording: transcribe + write its note. Returns
    the note paths produced. Safe to call on launch; a no-op when nothing pending."""
    notes_made: list[Path] = []
    for session in unfinished_sessions():
        ensure_meta(session)  # synthesizes meta + salvages orphaned WAVs (empty/missing manifest)
        transcribe.transcribe_session(session)
        if not transcript_markdown(session):
            # No speech captured: mark it so we don't retry on every launch.
            meta = read_meta(session)
            meta["recovered_empty"] = True
            write_meta(session, meta)
            continue
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
