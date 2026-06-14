"""Spawn and stop the audiocap Swift helper."""

import json
import signal
import subprocess
from pathlib import Path

from . import config


class AudiocapError(RuntimeError):
    pass


def start(session_dir: Path) -> subprocess.Popen[str]:
    """Start audiocap for a session. Blocks until capture is actually running.

    May block on first run while macOS shows the Microphone / Screen Recording
    permission prompts.
    """
    binary = config.AUDIOCAP_BIN
    if not binary.exists():
        raise AudiocapError(
            f"audiocap binary not found at {binary}\n"
            "Build it with:  cd audiocap && swift build -c release"
        )
    proc = subprocess.Popen(
        [str(binary), str(session_dir), "--chunk-seconds", str(config.CHUNK_SECONDS)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stdout is not None  # PIPE above guarantees this
    line = proc.stdout.readline()
    if not line:
        proc.wait()
        raise AudiocapError(f"audiocap exited immediately (code {proc.returncode})")
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        event = {"event": "error", "message": f"unexpected audiocap output: {line!r}"}
    if event.get("event") == "error":
        stop(proc)
        raise AudiocapError(event.get("message", "unknown audiocap error"))
    if event.get("event") != "started":
        stop(proc)
        raise AudiocapError(f"unexpected audiocap event: {event}")
    return proc


def stop(proc: subprocess.Popen[str], timeout: float = 15.0) -> None:
    """Stop audiocap gracefully so it flushes partial chunks."""
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
