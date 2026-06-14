"""PyInstaller entry point for the bundled `mbot` sidecar.

Thin shim so PyInstaller has a concrete script to freeze; it just delegates to
the Typer CLI app. Built by scripts/build-sidecar.sh.
"""

from meetingbot.cli import app

if __name__ == "__main__":
    app()
