#!/usr/bin/env bash
# Package the Chrome extension into a Web Store-ready zip containing ONLY the
# production files — never node_modules/, test/, types/, tsconfig, or package
# manifests, which bloat the upload and draw review flags.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$PROJECT/chrome-extension"
VERSION="$(python3 -c "import json; print(json.load(open('$EXT/manifest.json'))['version'])")"
OUT="$PROJECT/dist/meeting-bot-extension-$VERSION.zip"

# Explicit allowlist of shipped files (matches manifest.json references).
FILES=(
  manifest.json
  background.js
  offscreen.html offscreen.js
  popup.html popup.js
  permission.html permission.js
  pcm-worklet.js
  icons
)

for f in "${FILES[@]}"; do
  [ -e "$EXT/$f" ] || { echo "✗ missing production file: $f"; exit 1; }
done

mkdir -p "$PROJECT/dist"
rm -f "$OUT"
(cd "$EXT" && zip -r -X "$OUT" "${FILES[@]}" >/dev/null)

echo "✓ Built $OUT"
echo "  contents:"
unzip -l "$OUT" | awk 'NR>3 && $4 {print "    "$4}' | grep -v '^    $' || true
echo "  Upload this zip at https://chrome.google.com/webstore/devconsole"
