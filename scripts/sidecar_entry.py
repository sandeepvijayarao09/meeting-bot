"""PyInstaller entry point for the bundled `mbot` sidecar.

Thin shim so PyInstaller has a concrete script to freeze; it just delegates to
the Typer CLI app. Built by scripts/build-sidecar.sh.
"""

import multiprocessing

if __name__ == "__main__":
    # Must run before anything else parses argv. In a frozen build sys.executable
    # is `mbot` itself, so when multiprocessing starts a child it re-executes this
    # binary with Python's own flags (-B, -S, -c ...). Without freeze_support()
    # those fall through to Typer, which rejects them ("No such option: -B") and
    # kills the child — during transcription that surfaced as two spurious usage
    # errors plus "resource_tracker: process died unexpectedly, relaunching", and
    # leaked the semaphores the tracker existed to clean up.
    multiprocessing.freeze_support()

    from meetingbot.cli import app

    app()
