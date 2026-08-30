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
#
# FRESHNESS: dist/ is gitignored but persists across releases, so an old sidecar
# would otherwise be silently re-embedded — shipping months-old Python inside a
# freshly versioned app. Every build records a fingerprint of its inputs in
# dist/sidecar/.fingerprint; `--if-stale` rebuilds only when that no longer matches.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$PROJECT/dist/sidecar"
STAMP="$OUT/.fingerprint"

# Hash of everything frozen into the binary: the Python package, the entry point,
# the bundled prompt templates, and the dependency set.
fingerprint() {
  cd "$PROJECT"
  {
    find meetingbot prompts -type f -not -path '*__pycache__*' -print0 | sort -z | xargs -0 shasum -a 256
    shasum -a 256 scripts/sidecar_entry.py scripts/build-sidecar.sh uv.lock pyproject.toml
  } | shasum -a 256 | awk '{print $1}'
}

FP="$(fingerprint)"

if [ "${1:-}" = "--if-stale" ]; then
  if [ -x "$OUT/mbot" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$FP" ]; then
    echo "▸ Sidecar is up to date (fingerprint $FP) — reusing $OUT/mbot"
    exit 0
  fi
  echo "▸ Sidecar missing or stale — rebuilding…"
fi

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
    --add-data "$PROJECT/prompts:prompts" \
    --hidden-import meetingbot.cli \
    --console \
    scripts/sidecar_entry.py )

mkdir -p "$OUT"
cp -R "$PROJECT/dist/_sidecar_build/mbot/." "$OUT/"
rm -rf "$PROJECT/dist/_sidecar_build" "$PROJECT/build" "$PROJECT/mbot.spec"

if [ -x "$OUT/mbot" ]; then
  printf '%s' "$FP" > "$STAMP"
  echo "✓ Sidecar built at $OUT/mbot"
  du -sh "$OUT" | awk '{print "  size: "$1}'
else
  echo "✗ Sidecar build failed — no executable at $OUT/mbot"
  exit 1
fi
