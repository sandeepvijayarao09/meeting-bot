#!/usr/bin/env bash
# Build the `mbot` Python pipeline into a self-contained sidecar binary that the
# MeetingBot.app bundles in Contents/Resources — so end users need no Python,
# no venv, and no `pip install`.
#
# Output: dist/sidecar/mbot (+ its support files). Consumed by:
#   EMBED_SIDECAR=1 bash scripts/build-app.sh
#
# NOTE ON SIZE: mlx-whisper pulls in mlx + numba/llvmlite + scipy, which is most of
# what remains after the exclusions below (see the block above the pyinstaller call
# for what is cut and why). The Whisper model is NOT in here — it downloads once to
# ~/.cache on demand, via `mbot download-model`. If the remainder is still too large,
# the lighter-weight alternative is to drop Python entirely and call whisper.cpp from
# Swift — see DISTRIBUTION.md ("Going fully native").
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
# PyInstaller analyses imports statically, so it sweeps in anything reachable from a
# module it decides to keep — including code no execution path reaches. Left alone it
# ships ~420 MB of that. Each exclusion below is verified unreachable, not guessed:
#
#   torch (319 MB)  mlx-whisper declares it, but only torch_whisper.py imports it, and
#                   nothing imports torch_whisper — it is the PyTorch→MLX checkpoint
#                   converter, irrelevant when loading a pre-converted mlx-community
#                   repo. meetingbot/diarize.py also imports torch, behind the opt-in
#                   MBOT_DIARIZE extra that a shipped build never has installed.
#   dev tooling     mypy/pytest/hypothesis/ruff live in the dev group and land in the
#                   build venv, so they get analysed like anything else.
#
# NOT excluded: numba, llvmlite and scipy (147 MB). mlx_whisper/transcribe.py does
# `from .timing import add_word_timestamps` at module scope, so they are needed at
# import time even though we never request word timestamps. Dropping them breaks
# transcription outright — verify with `mbot doctor` before touching them.
( cd "$PROJECT" && uv run pyinstaller \
    --name mbot \
    --onedir \
    --noconfirm \
    --distpath "$PROJECT/dist/_sidecar_build" \
    --collect-all mlx_whisper \
    --collect-all mlx \
    --exclude-module torch \
    --exclude-module torchvision \
    --exclude-module torchaudio \
    --exclude-module pyannote \
    --exclude-module mypy \
    --exclude-module pytest \
    --exclude-module hypothesis \
    --exclude-module coverage \
    --exclude-module ruff \
    --add-data "$PROJECT/prompts:prompts" \
    --hidden-import meetingbot.cli \
    --console \
    scripts/sidecar_entry.py )

mkdir -p "$OUT"
cp -R "$PROJECT/dist/_sidecar_build/mbot/." "$OUT/"
rm -rf "$PROJECT/dist/_sidecar_build" "$PROJECT/build" "$PROJECT/mbot.spec"

# google-api-python-client ships a snapshot of every Google API's discovery document
# — 582 files, 96 MB — for offline client construction. The Google Docs exporter calls
# build(..., cache_discovery=False), so not one of them is ever read. Keep only the two
# APIs we build, so the directory stays valid if that flag ever changes.
DISCOVERY="$OUT/_internal/googleapiclient/discovery_cache/documents"
if [ -d "$DISCOVERY" ]; then
  BEFORE_KB=$(du -sk "$DISCOVERY" | awk '{print $1}')
  find "$DISCOVERY" -type f ! -name 'docs.v1.json' ! -name 'drive.v3.json' -delete
  AFTER_KB=$(du -sk "$DISCOVERY" | awk '{print $1}')
  echo "▸ Pruned unused Google discovery docs ($(( (BEFORE_KB - AFTER_KB) / 1024 )) MB)"
fi

if [ -x "$OUT/mbot" ]; then
  printf '%s' "$FP" > "$STAMP"
  echo "✓ Sidecar built at $OUT/mbot"
  du -sh "$OUT" | awk '{print "  size: "$1}'
else
  echo "✗ Sidecar build failed — no executable at $OUT/mbot"
  exit 1
fi
