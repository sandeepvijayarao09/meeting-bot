#!/usr/bin/env bash
# Sign + notarize MeetingBot.app for distribution. Requires an Apple Developer
# account ($99/yr) and your own credentials — this is the one step that cannot
# be done for you.
#
# Prerequisites (one-time):
#   • A "Developer ID Application" certificate in your login keychain.
#   • A notarytool keychain profile:
#       xcrun notarytool store-credentials meetingbot-notary \
#         --apple-id you@example.com --team-id TEAMID --password APP_SPECIFIC_PW
#
# Usage:
#   DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" \
#   NOTARY_PROFILE=meetingbot-notary \
#   bash scripts/sign-notarize.sh
set -euo pipefail

: "${DEVELOPER_ID:?set DEVELOPER_ID to your 'Developer ID Application: …' identity}"
: "${NOTARY_PROFILE:?set NOTARY_PROFILE to your notarytool keychain profile name}"

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▸ (Re)building app signed with Developer ID…"
DEVELOPER_ID="$DEVELOPER_ID" EMBED_SIDECAR="${EMBED_SIDECAR:-1}" bash "$PROJECT/scripts/build-app.sh"

echo "▸ Building DMG…"
bash "$PROJECT/scripts/build-dmg.sh"
DMG="$(ls -t "$PROJECT"/dist/MeetingBot-*.dmg | head -1)"

echo "▸ Submitting $DMG to Apple notary service (this can take a few minutes)…"
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait

echo "▸ Stapling the notarization ticket…"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"

echo "✓ Notarized + stapled: $DMG"
echo "  This DMG now opens without Gatekeeper warnings on any Mac."
