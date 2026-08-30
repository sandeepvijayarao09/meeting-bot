#!/usr/bin/env bash
# Sign, notarize, and staple MB.app + its DMG for public distribution.
#
# Requires an Apple Developer account ($99/yr) and your own credentials — the one
# step that cannot be done for you. Both prerequisites are checked up front, before
# the ~15-minute build, so a missing credential fails in seconds.
#
# Prerequisites (one-time):
#   • A "Developer ID Application" certificate in your login keychain
#     (Xcode ▸ Settings ▸ Accounts ▸ Manage Certificates ▸ + ▸ Developer ID Application).
#     Confirm with: security find-identity -v -p codesigning
#   • A notarytool keychain profile, using an app-specific password from
#     https://account.apple.com (Sign-In and Security ▸ App-Specific Passwords):
#       xcrun notarytool store-credentials meetingbot-notary \
#         --apple-id you@example.com --team-id TEAMID --password xxxx-xxxx-xxxx-xxxx
#
# Usage:
#   DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" \
#   NOTARY_PROFILE=meetingbot-notary \
#   bash scripts/sign-notarize.sh
set -euo pipefail

: "${DEVELOPER_ID:?set DEVELOPER_ID to your 'Developer ID Application: …' identity}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE to your notarytool keychain profile name}"

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="${APP_NAME:-MB}"
APP="$PROJECT/dist/${APP_NAME}.app"

# ── Preflight the credentials ────────────────────────────────────────────────
# Discovering a missing certificate after a 15-minute PyInstaller build is a bad
# trade; both checks below cost about a second.
echo "▸ Checking credentials…"
if ! security find-identity -v -p codesigning | grep -Fq "$DEVELOPER_ID"; then
  echo "✗ no codesigning identity matching: $DEVELOPER_ID"
  echo "  available identities:"
  security find-identity -v -p codesigning | sed 's/^/    /'
  echo "  Add one in Xcode ▸ Settings ▸ Accounts ▸ Manage Certificates ▸ + ▸ Developer ID Application."
  exit 1
fi
echo "  ✓ certificate: $DEVELOPER_ID"

if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
  echo "✗ notarytool profile '$NOTARY_PROFILE' is missing or invalid. Create it with:"
  echo "    xcrun notarytool store-credentials $NOTARY_PROFILE \\"
  echo "      --apple-id you@example.com --team-id TEAMID --password <app-specific-password>"
  exit 1
fi
echo "  ✓ notary profile: $NOTARY_PROFILE"

# ── Build, signed with the real identity ─────────────────────────────────────
echo "▸ Building app signed with Developer ID…"
DEVELOPER_ID="$DEVELOPER_ID" EMBED_SIDECAR="${EMBED_SIDECAR:-1}" bash "$PROJECT/scripts/build-app.sh"

# ── Notarize and staple the APP, before it goes into the DMG ─────────────────
# Stapling only the DMG leaves the app itself ticketless: once a user drags it to
# /Applications and the DMG is gone, an offline Mac has no way to verify it. Apple's
# guidance is to staple the app first, then package the stapled app.
ZIP="$PROJECT/dist/${APP_NAME}-notarize.zip"
echo "▸ Submitting the app to Apple (a few minutes)…"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
rm -f "$ZIP"

echo "▸ Stapling the ticket to the app…"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

# ── Package the stapled app, then notarize the DMG too ───────────────────────
echo "▸ Building DMG from the stapled app…"
bash "$PROJECT/scripts/build-dmg.sh"

# Recompute the name the same way build-dmg.sh does, rather than picking the newest
# file on disk: `ls -t` happily selects a previous release's DMG if this build failed.
VERSION="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")"
BUILD="$(/usr/libexec/PlistBuddy -c 'Print CFBundleVersion' "$APP/Contents/Info.plist")"
DMG="$PROJECT/dist/${APP_NAME}-${VERSION}-${BUILD}.dmg"
[ -f "$DMG" ] || { echo "✗ expected $DMG — build-dmg.sh naming has diverged"; exit 1; }

echo "▸ Signing the DMG…"
codesign --force --timestamp --sign "$DEVELOPER_ID" "$DMG"

echo "▸ Submitting the DMG to Apple…"
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait

echo "▸ Stapling the ticket to the DMG…"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"

# ── Prove it ─────────────────────────────────────────────────────────────────
echo "▸ Verifying the finished artifact…"
bash "$PROJECT/scripts/preflight-release.sh"

echo
echo "✓ Notarized + stapled: $DMG"
echo "  Opens with no Gatekeeper warning on any Apple Silicon Mac, online or offline."
