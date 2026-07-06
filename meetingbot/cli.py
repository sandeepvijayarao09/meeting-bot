"""mbot — command-line interface."""

import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import typer

from . import config, notes, recorder, summarize

app = typer.Typer(help="Local Granola-style meeting notetaker.", no_args_is_help=True)


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging")) -> None:
    """Install a stderr log handler for the meetingbot package (stdout stays clean
    for machine-readable output like `process --print-note-path`)."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    pkg_logger = logging.getLogger("meetingbot")
    pkg_logger.handlers = [handler]
    pkg_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    pkg_logger.propagate = False


def _resolve_session(name: str | None) -> Path:
    if name:
        path = Path(name)
        if not path.is_dir():
            path = config.SESSIONS_DIR / name
        if not (path / "meta.json").exists():
            typer.secho(f"no session at {path}", fg="red")
            raise typer.Exit(1)
        return path
    latest = recorder.latest_session()
    if latest is None:
        typer.secho("no sessions yet — run `mbot record` first", fg="red")
        raise typer.Exit(1)
    return latest


@app.command()
def record(
    title: str = typer.Option(None, "--title", "-t", help="Meeting title for the note"),
    no_summary: bool = typer.Option(False, help="Skip the NIM summary step"),
) -> None:
    """Record the current meeting until Ctrl+C (or `mbot stop` from another shell)."""
    rec = recorder.Recorder(
        title,
        on_segment=lambda s: typer.echo(
            f"  [{int(s['start']) // 60:02d}:{int(s['start']) % 60:02d}] "
            f"{config.SPEAKER_LABELS.get(s['speaker'], s['speaker'])}: {s['text']}"
        ),
    )
    typer.secho("Starting capture (first run will ask for permissions)…", fg="cyan")
    try:
        session = rec.start()
    except RuntimeError as e:  # double-record guard, missing audiocap, denied perms
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    typer.secho(f"● Recording — session {session.name}", fg="red", bold=True)
    typer.echo("  Transcribing live. Ctrl+C to stop.")
    typer.echo(f"  Jot rough notes in: {session / 'notes.txt'} (optional)")

    def _sigterm(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _sigterm)
    try:
        while rec.capture_alive():
            time.sleep(0.5)
        typer.secho("capture process exited unexpectedly", fg="red")
    except KeyboardInterrupt:
        pass

    typer.secho("\nStopping — finishing transcription…", fg="cyan")
    rec.stop()
    if not no_summary and summarize.have_key():
        typer.secho("Summarizing via NVIDIA NIM…", fg="cyan")
    note_path, summarized = rec.finalize(want_summary=not no_summary)
    typer.secho(f"✓ Note: {note_path}", fg="green", bold=True)
    if not summarized and not no_summary:
        typer.secho(
            "  (no NVIDIA_API_KEY yet — transcript saved; run `mbot summarize` later)",
            fg="yellow",
        )


@app.command()
def stop() -> None:
    """Stop a recording started in another terminal (or by the menu bar app)."""
    info = recorder.current_recording()
    if not info:
        typer.echo("nothing is recording")
        raise typer.Exit(1)
    os.kill(info["pid"], signal.SIGINT)
    typer.secho(f"sent stop to recording of session {Path(info['session_dir']).name}", fg="green")


@app.command()
def status() -> None:
    """Show whether a recording is in progress."""
    info = recorder.current_recording()
    if not info:
        typer.echo("idle — nothing is recording")
        return
    started = datetime.fromisoformat(info["started_at"])
    mins = int((datetime.now() - started).total_seconds()) // 60
    typer.secho(
        f"● recording {Path(info['session_dir']).name} — {mins}m elapsed (pid {info['pid']})",
        fg="red",
    )


@app.command(name="summarize")
def summarize_cmd(
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
    template: str = typer.Option(
        None, "--template", help="Meeting type: standup, one_on_one, interview, sales_call"
    ),
) -> None:
    """(Re)summarize a finished session — for when the API key arrives later."""
    path = _resolve_session(session)
    try:
        note_path = recorder.summarize_session(path, template=template)
    except summarize.MissingAPIKeyError as e:
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    typer.secho(f"✓ Note: {note_path}", fg="green", bold=True)


@app.command()
def export(
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
    to: list[str] = typer.Option(
        None, "--to", "-t", help="Targets: apple_notes, google_docs, markdown (repeatable)"
    ),
) -> None:
    """Export a finished session's note to Apple Notes / Google Docs / Markdown."""
    from . import exporters

    path = _resolve_session(session)
    targets = to or [n for n in exporters.configured_targets() if n != "markdown"] or ["markdown"]
    try:
        results = recorder.export_session(path, targets)
    except RuntimeError as e:
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    for r in results:
        if r.location:
            typer.secho(f"✓ {r.target}: {r.location}", fg="green")
        else:
            typer.secho(f"✗ {r.target}: {r.detail}", fg="yellow")


@app.command()
def recover(
    print_note_paths: bool = typer.Option(
        False, "--print-note-paths", help="Print only the recovered note paths (one per line)"
    ),
) -> None:
    """Finish any interrupted recordings (after a crash or force-quit)."""
    pending = recorder.unfinished_sessions()
    if not pending:
        if not print_note_paths:
            typer.secho("no interrupted recordings to recover", fg="green")
        return
    if not print_note_paths:
        typer.secho(f"recovering {len(pending)} interrupted recording(s)…", fg="cyan")
    for note_path in recorder.recover():
        typer.echo(str(note_path) if print_note_paths else f"✓ {note_path}")


@app.command(name="auth-google")
def auth_google() -> None:
    """Authorize Google Docs export (opens a browser once)."""
    from .exporters import google_docs

    try:
        google_docs.authorize()
    except Exception as e:  # surface setup problems plainly
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    typer.secho("✓ Google authorized — google_docs export is ready.", fg="green", bold=True)


@app.command(name="set-key")
def set_key(
    key: str = typer.Argument(
        None, help='Your NVIDIA NIM API key (nvapi-…). Omit to be prompted; pass "" to clear.'
    ),
) -> None:
    """Save your own NVIDIA NIM API key for summaries + Ask (bring-your-own-key).

    Get a free key at https://build.nvidia.com. Stored locally in
    ~/.config/meetingbot/.env — the same key the macOS app reads, never sent anywhere
    but NVIDIA when you summarize.
    """
    if key is None:
        key = typer.prompt("NVIDIA NIM API key (nvapi-…)", hide_input=True)
    key = key.strip()
    env_file = config.CONFIG_DIR / ".env"
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Upsert NVIDIA_API_KEY, preserving any other lines (mirrors the macOS Settings pane).
    lines = [
        ln
        for ln in (env_file.read_text().splitlines() if env_file.exists() else [])
        if not ln.startswith("NVIDIA_API_KEY=")
    ]
    if key:
        lines.append(f"NVIDIA_API_KEY={key}")
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""))
    if key:
        masked = f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "set"
        typer.secho(f"✓ key saved ({masked}) → {env_file}", fg="green", bold=True)
    else:
        typer.secho("✓ key cleared.", fg="yellow")


@app.command()
def process(
    session: str = typer.Argument(..., help="Session directory to process (from native capture)"),
    title: str = typer.Option(None, "--title", help="Meeting title for the note"),
    template: str = typer.Option(
        None, "--template", help="Meeting type: standup, one_on_one, interview, sales_call"
    ),
    print_note_path: bool = typer.Option(
        False, "--print-note-path", help="Print only the resulting note path on the last line"
    ),
) -> None:
    """Transcribe + summarize + export an already-recorded session directory.

    Entry point for the native macOS app, which captures audio itself (writing
    session.json + manifest + WAVs) and hands the finished session here for the
    local Whisper + NIM + export pipeline.
    """
    from . import transcribe as t

    path = Path(session)
    if not path.is_dir():
        path = config.SESSIONS_DIR / session
    if not path.is_dir():
        typer.secho(f"no session directory at {path}", fg="red")
        raise typer.Exit(1)
    recorder.ensure_meta(path, title=title)  # synthesize meta.json for native captures
    if not print_note_path:
        typer.secho(f"transcribing {path.name}…", fg="cyan")
    t.transcribe_session(path)
    note_path, summarized = recorder.finalize_session(path, want_summary=True, template=template)
    if print_note_path:
        typer.echo(str(note_path))
    else:
        state = "summarized" if summarized else "transcribed (no API key)"
        typer.secho(f"✓ {state}: {note_path}", fg="green", bold=True)


@app.command(name="transcribe")
def transcribe_cmd(
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
) -> None:
    """(Re)run local transcription for a session (e.g. after an interrupted recording)."""
    from . import transcribe as t

    path = _resolve_session(session)
    typer.secho(f"transcribing {path.name} with {config.WHISPER_MODEL}…", fg="cyan")
    t.transcribe_session(path)
    turns = t.merge_turns(t.load_segments(path))
    typer.secho(f"✓ {len(turns)} speaker turns in {path / 'transcript.jsonl'}", fg="green")


@app.command(name="refine")
def refine_cmd(
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
    tier: str = typer.Option(
        None, "--tier", help="off | local | cloud (default: MBOT_REFINE, i.e. local)"
    ),
) -> None:
    """Preview the Eloquent-style refined transcript (fillers, stutters, and false
    starts cleaned up). The note already embeds this; use --tier off for verbatim."""
    from . import refine as refine_mod

    path = _resolve_session(session)
    typer.echo(refine_mod.refine_transcript(path, tier=tier))


@app.command(name="transform")
def transform_cmd(
    kind: str = typer.Argument(..., help="key_points | formal | short | long"),
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
) -> None:
    """Reshape a meeting's transcript with an AI text tool (Eloquent-style)."""
    from . import refine as refine_mod
    from . import transform as transform_mod

    path = _resolve_session(session)
    # Feed the refined transcript; never trigger a billable cloud refine just to
    # prep input for the (already cloud) transform — downgrade "cloud" to local.
    text = recorder.refined_transcript_markdown(path, tier=refine_mod.noncloud_tier())
    try:
        out = transform_mod.transform(text, kind)
    except (ValueError, summarize.MissingAPIKeyError) as e:
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    typer.echo(out)


@app.command()
def diarize(
    session: str = typer.Argument(None, help="Session name/path (default: latest)"),
) -> None:
    """Label individual remote speakers (Speaker A/B/C) in a session's transcript.

    Requires the diarization extra: `uv sync --extra diarize` and an HF_TOKEN
    (free, after accepting the pyannote model terms). Re-runs on demand; the
    pipeline also does this automatically when MBOT_DIARIZE=1.
    """
    from . import diarize as diarize_mod

    path = _resolve_session(session)
    typer.secho(f"diarizing {path.name}…", fg="cyan")
    try:
        n = diarize_mod.diarize_session(path)
    except Exception as e:  # surface missing extra / token plainly
        typer.secho(f"diarization failed: {e}", fg="red")
        typer.echo("    install: uv sync --extra diarize   (and set HF_TOKEN)")
        raise typer.Exit(1) from e
    typer.secho(f"✓ found {n} speaker(s); transcript updated", fg="green")


@app.command(name="list")
def list_cmd(limit: int = typer.Option(10, "--limit", "-n")) -> None:
    """List recent notes."""
    paths = notes.list_notes()[:limit]
    if not paths:
        typer.echo("no notes yet")
        return
    for p in paths:
        typer.echo(f"  {p.name}")


@app.command()
def sessions() -> None:
    """List recorded sessions and their state."""
    found = recorder.list_sessions()
    if not found:
        typer.echo("no sessions yet")
        return
    for path in found:
        meta = recorder.read_meta(path)
        has_transcript = (path / "transcript.jsonl").exists()
        state = (
            "summarized"
            if meta.get("summarized")
            else "transcribed"
            if has_transcript
            else "recorded"
        )
        typer.echo(f"  {path.name:<40} {state}")


@app.command()
def ask(question: str) -> None:
    """Ask a question across all your meetings (retrieval + NIM answer)."""
    from . import ask as ask_mod

    try:
        result = ask_mod.ask(question)
    except summarize.MissingAPIKeyError as e:
        typer.secho(str(e), fg="red")
        raise typer.Exit(1) from e
    typer.echo(result.answer)
    if result.sources:
        typer.secho("\nSources:", bold=True)
        for s in result.sources:
            typer.echo(f"  • {s['title']} ({s['date']})")


@app.command()
def search(query: str) -> None:
    """Full-text search across all meeting notes."""
    hits = notes.search(query)
    if not hits:
        typer.echo("no matches")
        return
    for h in hits:
        typer.secho(f"{h['title']}  ({h['date'][:10]})", bold=True)
        typer.echo(f"  {h['snippet']}")
        typer.echo(f"  {h['path']}\n")


@app.command(name="open")
def open_cmd(
    session: str = typer.Argument(None, help="Session name (default: latest note)"),
) -> None:
    """Open the latest note (or a specific session's note)."""
    if session:
        meta = recorder.read_meta(_resolve_session(session))
        target = meta.get("note_path")
        if not target:
            typer.secho("that session has no note yet", fg="red")
            raise typer.Exit(1)
    else:
        recent = notes.list_notes()
        if not recent:
            typer.secho("no notes yet", fg="red")
            raise typer.Exit(1)
        target = recent[0]
    subprocess.run(["open", str(target)], check=False)


@app.command()
def serve(
    port: int = typer.Option(None, "--port", "-p", help="WebSocket port (default 8765)"),
) -> None:
    """Run the localhost capture server for the Chrome extension."""
    from . import server

    server.run(port=port)


@app.command()
def doctor() -> None:
    """Check that everything is set up."""
    ok = True

    if config.AUDIOCAP_BIN.exists():
        typer.secho(f"✓ audiocap binary: {config.AUDIOCAP_BIN}", fg="green")
    else:
        ok = False
        typer.secho("✗ audiocap binary missing — build it:", fg="red")
        typer.echo("    cd mac && swift build -c release")

    typer.echo(f"  whisper model: {config.WHISPER_MODEL} (downloads on first use)")

    if summarize.have_key():
        try:
            summarize.ping()
            typer.secho(f"✓ NVIDIA NIM reachable ({config.NIM_MODEL})", fg="green")
        except Exception as e:  # surface auth/network problems directly
            ok = False
            typer.secho(f"✗ NIM error: {e}", fg="red")
    else:
        ok = False
        typer.secho("✗ NVIDIA_API_KEY not set", fg="yellow")
        typer.echo("    free key: https://build.nvidia.com → ~/.config/meetingbot/.env")

    from . import exporters

    typer.echo("  export targets:")
    for name in exporters.configured_targets():
        exp = exporters.get(name)
        mark = "✓" if (name == "markdown" or exp.available()) else "·"
        note = "" if (name == "markdown" or exp.available()) else "  (run setup)"
        typer.echo(f"    {mark} {name}{note}")

    typer.echo(f"  notes dir:    {config.NOTES_DIR}")
    typer.echo(f"  sessions dir: {config.SESSIONS_DIR}")
    typer.echo(
        "  permissions: System Settings > Privacy & Security — your terminal needs "
        "Microphone + Screen Recording (prompted on first `mbot record`)"
    )
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
