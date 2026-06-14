#!/usr/bin/env bash
# Package dist/MeetingBot.app into a distributable DMG with an Applications
# symlink for drag-to-install. Run scripts/build-app.sh first.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$PROJECT/dist/MeetingBot.app"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist" 2>/dev/null || echo 0.1.0)"
DMG="$PROJECT/dist/MeetingBot-$VERSION.dmg"
STAGE="$(mktemp -d)"

[ -d "$APP" ] || { echo "✗ $APP not found — run scripts/build-app.sh first"; exit 1; }

echo "▸ Staging DMG contents…"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

echo "▸ Creating $DMG…"
rm -f "$DMG"
hdiutil create -volname "Meeting Bot" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo "✓ Built $DMG"
du -sh "$DMG" | awk '{print "  size: "$1}'
echo "  (Unsigned/un-notarized DMGs trigger Gatekeeper on other Macs — see DISTRIBUTION.md.)"
