#!/usr/bin/env bash
# Build MeetingBot.app — the native SwiftUI menu bar app — into dist/.
#
# By default produces an ad-hoc-signed bundle that runs on this machine. To make
# a distributable, notarizable build, set DEVELOPER_ID and run scripts/sign-notarize.sh.
#
#   bash scripts/build-app.sh            # ad-hoc signed, runs locally
#   EMBED_SIDECAR=1 bash scripts/build-app.sh   # also bundle the mbot Python sidecar
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$PROJECT/dist/MeetingBot.app"
SRC="$PROJECT/mac/MeetingBot"

echo "▸ Compiling (swift build -c release)…"
( cd "$PROJECT/mac" && swift build -c release )
BIN="$PROJECT/mac/.build/release/MeetingBot"
[ -x "$BIN" ] || { echo "✗ build produced no MeetingBot binary"; exit 1; }

echo "▸ Assembling $APP…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MeetingBot"
cp "$SRC/Info.plist" "$APP/Contents/Info.plist"
cp "$SRC/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
printf 'APPL????' > "$APP/Contents/PkgInfo"

# Optionally bundle the Python pipeline as a sidecar (see scripts/build-sidecar.sh).
if [ "${EMBED_SIDECAR:-0}" = "1" ]; then
  if [ -x "$PROJECT/dist/sidecar/mbot" ]; then
    echo "▸ Embedding mbot sidecar…"
    cp -R "$PROJECT/dist/sidecar/." "$APP/Contents/Resources/"
  else
    echo "⚠ EMBED_SIDECAR=1 but dist/sidecar/mbot not found — run scripts/build-sidecar.sh first"
  fi
fi

echo "▸ Validating Info.plist…"
plutil -lint "$APP/Contents/Info.plist" >/dev/null

# Signing: real Developer ID if provided (for distribution), else ad-hoc (local).
ENTITLEMENTS="$SRC/MeetingBot.entitlements"
if [ -n "${DEVELOPER_ID:-}" ]; then
  echo "▸ Signing with Developer ID: $DEVELOPER_ID"
  codesign --force --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" --sign "$DEVELOPER_ID" "$APP"
else
  echo "▸ Ad-hoc signing (local use; set DEVELOPER_ID for distribution)…"
  codesign --force --entitlements "$ENTITLEMENTS" --sign - "$APP"
fi

codesign --verify --deep --strict "$APP" && echo "  ✓ signature valid"
echo "✓ Built $APP"
echo "  Launch:  open \"$APP\"   (look for the 🎤 in the menu bar)"
