#!/usr/bin/env bash
# Every release gate that can be checked on this Mac, run against the BUILT ARTIFACT
# rather than the source tree — the distinction that matters, because `make check`
# tests the repo and users download a bundle. Two defects shipped in the 1.0.0 DMG
# precisely because nothing inspected the artifact.
#
# Exits non-zero if the bundle is not fit for public distribution. Being ad-hoc signed
# (the default local build) is reported as a blocker, with the command that fixes it.
#
#   bash scripts/preflight-release.sh              # dist/MB.app + newest matching DMG
#   APP=/path/to/MB.app bash scripts/preflight-release.sh
set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="${APP_NAME:-MB}"
APP="${APP:-$PROJECT/dist/${APP_NAME}.app}"

FAIL=0
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }
hint() { printf '      %s\n' "$1"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ -d "$APP" ] || { echo "✗ no app bundle at $APP — run: EMBED_SIDECAR=1 bash scripts/build-app.sh"; exit 1; }
echo "Preflight: $APP"

# ---------------------------------------------------------------- bundle contents
head_ "Bundle"
PLIST="$APP/Contents/Info.plist"
plv() { /usr/libexec/PlistBuddy -c "Print :$1" "$PLIST" 2>/dev/null; }

if plutil -lint "$PLIST" >/dev/null 2>&1; then pass "Info.plist is valid"; else fail "Info.plist is malformed"; fi

VERSION="$(plv CFBundleShortVersionString)"
BUILD="$(plv CFBundleVersion)"
BUNDLE_ID="$(plv CFBundleIdentifier)"
[ -n "$VERSION" ] && [ -n "$BUILD" ] && pass "version $VERSION (build $BUILD), id $BUNDLE_ID" \
  || fail "missing CFBundleShortVersionString / CFBundleVersion"

# The DMG is named from the app's own version, so a stale stamp silently mislabels
# the download — this is the drift that nearly shipped 1.0.1 as "1.0.0".
REPO_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$PROJECT/meetingbot/__init__.py")"
if [ "$VERSION" = "$REPO_VERSION" ]; then
  pass "version matches meetingbot.__version__"
else
  fail "app says $VERSION but meetingbot.__version__ is $REPO_VERSION"
  hint "bump mac/MeetingBot/Info.plist — see the version table in RELEASE.md"
fi

for k in NSMicrophoneUsageDescription NSAudioCaptureUsageDescription; do
  [ -n "$(plv "$k")" ] && pass "$k present" || fail "$k missing — the app will crash on first capture"
done
[ -f "$APP/Contents/Resources/PrivacyInfo.xcprivacy" ] && pass "privacy manifest bundled" \
  || warn "no PrivacyInfo.xcprivacy (required for the App Store, not for Developer ID)"

ARCHS="$(lipo -archs "$APP/Contents/MacOS/$APP_NAME" 2>/dev/null)"
# MLX is Apple-Silicon only, so arm64-only is deliberate — but it must be stated on
# the download page, or Intel users get an unexplained "app is not compatible".
[ "$ARCHS" = "arm64" ] && pass "arm64 (Apple Silicon only, as documented)" \
  || warn "architectures: $ARCHS — docs promise Apple Silicon"

# ---------------------------------------------------------------- signing
head_ "Signature"
if codesign --verify --deep --strict "$APP" 2>/dev/null; then
  pass "signature valid (--deep --strict, covers nested code)"
else
  fail "codesign --verify --deep --strict failed"
  codesign --verify --deep --strict "$APP" 2>&1 | sed 's/^/      /' | head -5
fi

INFO="$(codesign -dvv "$APP" 2>&1)"
AUTHORITY="$(printf '%s' "$INFO" | sed -n 's/^Authority=//p' | head -1)"
TEAM="$(printf '%s' "$INFO" | sed -n 's/^TeamIdentifier=//p' | head -1)"

if printf '%s' "$INFO" | grep -q 'Signature=adhoc'; then
  fail "ad-hoc signed — Apple will not notarize this, and Gatekeeper blocks it"
  hint "DEVELOPER_ID=\"Developer ID Application: NAME (TEAMID)\" \\"
  hint "NOTARY_PROFILE=meetingbot-notary bash scripts/sign-notarize.sh"
elif printf '%s' "$AUTHORITY" | grep -q '^Developer ID Application'; then
  pass "signed by: $AUTHORITY"
  [ -n "$TEAM" ] && [ "$TEAM" != "not set" ] && pass "team identifier: $TEAM" \
    || fail "no team identifier — not a distributable signature"
else
  fail "unexpected signing authority: ${AUTHORITY:-none}"
  hint "public distribution requires a 'Developer ID Application' certificate"
fi

# Hardened runtime and a secure timestamp are both hard notarization requirements.
if printf '%s' "$INFO" | grep -qE '^CodeDirectory .*flags=.*runtime'; then
  pass "hardened runtime enabled"
else
  fail "hardened runtime NOT enabled — notarization will be rejected"
  hint "build-app.sh adds --options runtime whenever DEVELOPER_ID is set"
fi
if printf '%s' "$INFO" | grep -q '^Timestamp='; then
  pass "secure timestamp present"
else
  fail "no secure timestamp — notarization will be rejected"
  hint "requires --timestamp at signing time and network access to Apple"
fi

ENTS="$(codesign -d --entitlements - --xml "$APP" 2>/dev/null)"
printf '%s' "$ENTS" | grep -q 'com.apple.security.device.audio-input' \
  && pass "audio-input entitlement present" || fail "audio-input entitlement missing"

# The notary service rejects any unsigned Mach-O anywhere in the bundle; the sidecar
# contributes thousands, so verify them rather than trusting the signing loop.
head_ "Nested code (this takes a moment)"
UNSIGNED=0
TOTAL=0
while IFS= read -r -d '' f; do
  case "$(file -b "$f")" in
    *Mach-O*)
      TOTAL=$((TOTAL + 1))
      codesign --verify "$f" >/dev/null 2>&1 || { UNSIGNED=$((UNSIGNED + 1)); [ "$UNSIGNED" -le 3 ] && hint "unsigned: ${f#"$APP"/}"; }
      ;;
  esac
done < <(find "$APP/Contents" -type f -print0)
[ "$UNSIGNED" -eq 0 ] && pass "$TOTAL nested Mach-O binaries, all signed" \
  || fail "$UNSIGNED of $TOTAL nested Mach-O binaries are unsigned"

# ---------------------------------------------------------------- notarization
head_ "Notarization"
if xcrun stapler validate "$APP" >/dev/null 2>&1; then
  pass "notarization ticket stapled to the app"
else
  fail "no stapled ticket — a Mac with no network cannot verify this app"
  hint "scripts/sign-notarize.sh notarizes and staples the app before building the DMG"
fi

SPCTL="$(spctl -a -vvv -t exec "$APP" 2>&1)"
if printf '%s' "$SPCTL" | grep -q 'accepted'; then
  pass "Gatekeeper accepts the app"
  printf '%s' "$SPCTL" | sed -n 's/^source=/      source: /p'
else
  fail "Gatekeeper rejects the app — users get the 'unidentified developer' block"
  printf '%s' "$SPCTL" | sed 's/^/      /' | head -3
fi

# ---------------------------------------------------------------- the sidecar
head_ "Bundled sidecar"
MBOT="$APP/Contents/Resources/mbot"
if [ -x "$MBOT" ]; then
  SIDECAR_VERSION="$("$MBOT" --version 2>/dev/null | awk '{print $2}')"
  [ "$SIDECAR_VERSION" = "$VERSION" ] && pass "sidecar reports $SIDECAR_VERSION" \
    || fail "sidecar reports '${SIDECAR_VERSION:-nothing}' but the app is $VERSION"
  # The 1.0.0 DMG shipped without prompt templates; every summary raised
  # FileNotFoundError. `doctor` resolves the template, so this is the canary.
  DOCTOR="$(cd / && "$MBOT" doctor 2>&1)"
  printf '%s' "$DOCTOR" | grep -q '✓ prompt template' \
    && pass "prompt templates resolve inside the bundle" \
    || { fail "prompt template does NOT resolve — summaries will fail"; \
         printf '%s' "$DOCTOR" | grep -i template | sed 's/^/      /'; }
  case "$(printf '%s' "$DOCTOR" | sed -n 's/^  notes dir: *//p')" in
    "$APP"*) fail "notes default inside the app bundle, which is read-only" ;;
    *) pass "notes default outside the app bundle" ;;
  esac
else
  fail "no mbot sidecar — build with EMBED_SIDECAR=1 or the app cannot transcribe"
fi

# ---------------------------------------------------------------- the DMG
head_ "Disk image"
DMG="$PROJECT/dist/${APP_NAME}-${VERSION}-${BUILD}.dmg"
if [ -f "$DMG" ]; then
  pass "$(basename "$DMG") ($(du -h "$DMG" | awk '{print $1}'))"
  xcrun stapler validate "$DMG" >/dev/null 2>&1 && pass "notarization ticket stapled to the DMG" \
    || fail "DMG has no stapled ticket"
else
  warn "no DMG for this exact build — run: bash scripts/build-dmg.sh"
fi

head_ "Result"
if [ "$FAIL" -eq 0 ]; then
  echo "  ✓ fit for public distribution"
else
  echo "  ✗ NOT fit for public distribution — see the ✗ lines above"
fi
exit "$FAIL"
