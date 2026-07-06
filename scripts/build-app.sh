#!/usr/bin/env bash
# Build the native SwiftUI app (MB.app by default; override with APP_NAME) into dist/.
#
# By default produces an ad-hoc-signed bundle that runs on this machine. To make
# a distributable, notarizable build, set DEVELOPER_ID and run scripts/sign-notarize.sh.
#
#   bash scripts/build-app.sh            # ad-hoc signed, runs locally
#   EMBED_SIDECAR=1 bash scripts/build-app.sh   # also bundle the mbot Python sidecar
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# App/bundle display name. The Swift target is always "MeetingBot"; the shipped
# app and its executable are named by APP_NAME (default "MB"), matching
# CFBundleExecutable in Info.plist.
APP_NAME="${APP_NAME:-MB}"
APP="$PROJECT/dist/${APP_NAME}.app"
SRC="$PROJECT/mac/MeetingBot"

echo "▸ Compiling (swift build -c release)…"
( cd "$PROJECT/mac" && swift build -c release )
BIN="$PROJECT/mac/.build/release/MeetingBot"
[ -x "$BIN" ] || { echo "✗ build produced no MeetingBot binary"; exit 1; }

echo "▸ Assembling $APP…"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/${APP_NAME}"
cp "$SRC/Info.plist" "$APP/Contents/Info.plist"
cp "$SRC/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
cp "$SRC/PrivacyInfo.xcprivacy" "$APP/Contents/Resources/PrivacyInfo.xcprivacy"
printf 'APPL????' > "$APP/Contents/PkgInfo"

# Version stamping. Marketing version comes from MB_VERSION (else the plist's own
# value); the build number is monotonic from the git commit count (else MB_BUILD),
# so every notarized/App Store upload has a strictly increasing CFBundleVersion.
PLIST="$APP/Contents/Info.plist"
MARKETING_VERSION="${MB_VERSION:-$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PLIST")}"
BUILD_NUMBER="${MB_BUILD:-$(git -C "$PROJECT" rev-list --count HEAD 2>/dev/null || echo 1)}"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $MARKETING_VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$PLIST"
echo "▸ Version $MARKETING_VERSION (build $BUILD_NUMBER)"

# Bundle the Python pipeline as a sidecar so end users need no Python/venv. Without it
# the shipped app can't transcribe (Paths.mbotExecutable finds nothing on a clean Mac),
# so when EMBED_SIDECAR=1 a missing sidecar is a HARD error — never ship a broken app.
if [ "${EMBED_SIDECAR:-0}" = "1" ]; then
  if [ ! -x "$PROJECT/dist/sidecar/mbot" ]; then
    echo "▸ Sidecar not found — building it (scripts/build-sidecar.sh)…"
    bash "$PROJECT/scripts/build-sidecar.sh"
  fi
  [ -x "$PROJECT/dist/sidecar/mbot" ] || { echo "✗ sidecar unavailable — cannot embed"; exit 1; }
  echo "▸ Embedding mbot sidecar…"
  cp -R "$PROJECT/dist/sidecar/." "$APP/Contents/Resources/"
  [ -x "$APP/Contents/Resources/mbot" ] ||
    { echo "✗ sidecar did not land at Contents/Resources/mbot"; exit 1; }
fi

echo "▸ Validating Info.plist…"
plutil -lint "$APP/Contents/Info.plist" >/dev/null

# Strip any extended attributes (quarantine/provenance) so the freshly built app
# launches locally without Gatekeeper friction. Sign last so the signature is valid.
xattr -cr "$APP" 2>/dev/null || true

# Signing: real Developer ID if provided (for distribution + notarization, with the
# hardened runtime + a secure timestamp), else ad-hoc for local use.
ENTITLEMENTS="$SRC/MeetingBot.entitlements"
if [ -n "${DEVELOPER_ID:-}" ]; then
  SIGN_ID="$DEVELOPER_ID"
  HARDENED=1
  echo "▸ Signing with Developer ID: $DEVELOPER_ID"
else
  SIGN_ID="-"
  HARDENED=0
  echo "▸ Ad-hoc signing (local use; set DEVELOPER_ID for distribution)…"
fi

# Sign one Mach-O. $2="1" attaches entitlements (main executables only). Written as a
# function, not an options array, so it's safe under `set -u` on macOS's bash 3.2.
sign_macho() {
  if [ "$HARDENED" = "1" ] && [ "${2:-0}" = "1" ]; then
    codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$SIGN_ID" "$1"
  elif [ "$HARDENED" = "1" ]; then
    codesign --force --options runtime --timestamp --sign "$SIGN_ID" "$1"
  elif [ "${2:-0}" = "1" ]; then
    codesign --force --entitlements "$ENTITLEMENTS" --sign "$SIGN_ID" "$1"
  else
    codesign --force --sign "$SIGN_ID" "$1"
  fi
}

# Inside-out: every nested Mach-O in the sidecar must be signed BEFORE the outer app,
# or the notary service rejects the unsigned Python/MLX dylibs. dylibs get the runtime
# options only; the mbot executable also needs the JIT / library-validation entitlements.
if [ -e "$APP/Contents/Resources/mbot" ]; then
  echo "▸ Signing nested sidecar binaries…"
  # Detect Mach-O by content, not extension: PyInstaller/MLX bundles include
  # extensionless helper executables and framework binaries (e.g. Python.framework's
  # Python) that .so/.dylib globbing misses — and the notary service checks them all.
  # Sign the mbot launcher last (with entitlements), so exclude it from the sweep.
  find "$APP/Contents/Resources" -type f ! -name mbot -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q "Mach-O"; then sign_macho "$f"; fi
    done
  sign_macho "$APP/Contents/Resources/mbot" 1
fi

echo "▸ Signing app bundle…"
sign_macho "$APP" 1

codesign --verify --deep --strict "$APP" && echo "  ✓ signature valid"
echo "✓ Built $APP"
echo "  Launch:  open \"$APP\"   — a Dock icon appears and the Meetings window opens."
echo "  If Finder says 'unidentified developer': right-click the app → Open → Open (once)."
