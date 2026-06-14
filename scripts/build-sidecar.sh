#!/usr/bin/env bash
# Build the `mbot` Python pipeline into a self-contained sidecar binary that the
# MeetingBot.app bundles in Contents/Resources — so end users need no Python,
# no venv, and no `pip install`.
#
# Output: dist/sidecar/mbot (+ its support files). Consumed by:
#   EMBED_SIDECAR=1 bash scripts/build-app.sh
#
# NOTE ON SIZE: mlx-whisper pulls in mlx + numpy; the onedir bundle lands around
# 250–400 MB before the Whisper model (the model downloads on first run to
# ~/.cache). If that is too large for your distribution, the lighter-weight
# alternative is to drop Python entirely and call whisper.cpp from Swift — see
# DISTRIBUTION.md ("Going fully native"). This script keeps the Python pipeline.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$PROJECT/dist/sidecar"

echo "▸ Installing PyInstaller into the project env…"
( cd "$PROJECT" && uv pip install pyinstaller >/dev/null )

echo "▸ Building mbot sidecar (onedir)…"
rm -rf "$OUT" "$PROJECT/build" "$PROJECT/mbot.spec"
( cd "$PROJECT" && uv run pyinstaller \
    --name mbot \
    --onedir \
    --noconfirm \
    --distpath "$PROJECT/dist/_sidecar_build" \
    --collect-all mlx_whisper \
    --collect-all mlx \
    --hidden-import meetingbot.cli \
    --console \
    scripts/sidecar_entry.py )

mkdir -p "$OUT"
cp -R "$PROJECT/dist/_sidecar_build/mbot/." "$OUT/"
rm -rf "$PROJECT/dist/_sidecar_build" "$PROJECT/build" "$PROJECT/mbot.spec"

if [ -x "$OUT/mbot" ]; then
  echo "✓ Sidecar built at $OUT/mbot"
  du -sh "$OUT" | awk '{print "  size: "$1}'
else
  echo "✗ Sidecar build failed — no executable at $OUT/mbot"
  exit 1
fi
