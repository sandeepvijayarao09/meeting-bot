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

# Every call below that asks Gatekeeper a question, or runs the bundled sidecar,
# blocks forever on a quarantined bundle — the exact state of an app dragged out
# of a freshly downloaded DMG, which is the bundle this gate most needs to audit.
# A gate that hangs reports nothing, so each of those calls runs under a deadline.
# shellcheck source=scripts/with-timeout.sh
source "$(dirname "${BASH_SOURCE[0]}")/with-timeout.sh"
GATEKEEPER_TIMEOUT="${GATEKEEPER_TIMEOUT:-60}"   # spctl / stapler: assessment + Apple
SIDECAR_TIMEOUT="${SIDECAR_TIMEOUT:-60}"         # one cold start of the frozen sidecar
CODESIGN_TIMEOUT="${CODESIGN_TIMEOUT:-300}"      # --deep walks thousands of binaries

FAIL=0
pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }
hint() { printf '      %s\n' "$1"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }
xattr_fix() { hint "xattr -dr com.apple.quarantine \"$APP\"   # or audit a freshly built bundle"; }
quarantine_hint() {
  hint "a quarantined bundle blocks here — Gatekeeper assesses every exec of it"
  xattr_fix
}

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

# Worth saying out loud: it changes what every Gatekeeper check below means, and
# it is why those checks have deadlines.
if xattr -p com.apple.quarantine "$APP" >/dev/null 2>&1; then
  warn "quarantined — downloaded rather than built here, so Gatekeeper gates what follows"
  xattr_fix
fi

ARCHS="$(lipo -archs "$APP/Contents/MacOS/$APP_NAME" 2>/dev/null)"
# MLX is Apple-Silicon only, so arm64-only is deliberate — but it must be stated on
# the download page, or Intel users get an unexplained "app is not compatible".
[ "$ARCHS" = "arm64" ] && pass "arm64 (Apple Silicon only, as documented)" \
  || warn "architectures: $ARCHS — docs promise Apple Silicon"

# ---------------------------------------------------------------- signing
head_ "Signature"
VERIFY="$(with_timeout "$CODESIGN_TIMEOUT" codesign --verify --deep --strict "$APP" 2>&1)"
case $? in
  0) pass "signature valid (--deep --strict, covers nested code)" ;;
  "$TIMEOUT_STATUS")
    fail "codesign --verify --deep --strict did not finish in ${CODESIGN_TIMEOUT}s"
    quarantine_hint ;;
  *)
    fail "codesign --verify --deep --strict failed"
    printf '%s\n' "$VERIFY" | sed 's/^/      /' | head -5 ;;
esac

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
# No deadline on this loop: `codesign --verify` on a single file reads the
# signature it already has and never asks Gatekeeper, so it is slow, not stuck.
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
with_timeout "$GATEKEEPER_TIMEOUT" xcrun stapler validate "$APP" >/dev/null 2>&1
case $? in
  0) pass "notarization ticket stapled to the app" ;;
  "$TIMEOUT_STATUS")
    fail "stapler validate did not finish in ${GATEKEEPER_TIMEOUT}s — ticket state unknown"
    hint "it reaches Apple when no ticket is stapled; check the network, then re-run" ;;
  *)
    fail "no stapled ticket — a Mac with no network cannot verify this app"
    hint "scripts/sign-notarize.sh notarizes and staples the app before building the DMG" ;;
esac

SPCTL="$(with_timeout "$GATEKEEPER_TIMEOUT" spctl -a -vvv -t exec "$APP" 2>&1)"
if [ $? -eq "$TIMEOUT_STATUS" ]; then
  fail "spctl did not answer in ${GATEKEEPER_TIMEOUT}s — Gatekeeper's verdict is unknown"
  quarantine_hint
elif printf '%s' "$SPCTL" | grep -q 'accepted'; then
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
  # Running the sidecar is where a quarantined bundle used to hang this script
  # outright: Gatekeeper blocks the nested, ad-hoc-signed binary before it prints
  # a byte, and nothing ever returns. Each invocation now has a deadline, and a
  # deadline reached is a reported failure, not a pass.
  VERSION_OUT="$(with_timeout "$SIDECAR_TIMEOUT" "$MBOT" --version 2>/dev/null)"
  if [ $? -eq "$TIMEOUT_STATUS" ]; then
    fail "sidecar did not answer --version in ${SIDECAR_TIMEOUT}s"
    quarantine_hint
  else
    SIDECAR_VERSION="$(printf '%s' "$VERSION_OUT" | awk '{print $2}')"
    [ "$SIDECAR_VERSION" = "$VERSION" ] && pass "sidecar reports $SIDECAR_VERSION" \
      || fail "sidecar reports '${SIDECAR_VERSION:-nothing}' but the app is $VERSION"
  fi
  # The 1.0.0 DMG shipped without prompt templates; every summary raised
  # FileNotFoundError. `doctor` resolves the template, so this is the canary.
  DOCTOR="$(cd / && with_timeout "$SIDECAR_TIMEOUT" "$MBOT" doctor 2>&1)"
  if [ $? -eq "$TIMEOUT_STATUS" ]; then
    fail "sidecar did not finish \`doctor\` in ${SIDECAR_TIMEOUT}s — templates unverified"
    quarantine_hint
  else
    printf '%s' "$DOCTOR" | grep -q '✓ prompt template' \
      && pass "prompt templates resolve inside the bundle" \
      || { fail "prompt template does NOT resolve — summaries will fail"; \
           printf '%s' "$DOCTOR" | grep -i template | sed 's/^/      /'; }
    case "$(printf '%s' "$DOCTOR" | sed -n 's/^  notes dir: *//p')" in
      "$APP"*) fail "notes default inside the app bundle, which is read-only" ;;
      *) pass "notes default outside the app bundle" ;;
    esac
  fi
else
  fail "no mbot sidecar — build with EMBED_SIDECAR=1 or the app cannot transcribe"
fi

# ---------------------------------------------------------------- the DMG
head_ "Disk image"
DMG="$PROJECT/dist/${APP_NAME}-${VERSION}-${BUILD}.dmg"
if [ -f "$DMG" ]; then
  pass "$(basename "$DMG") ($(du -h "$DMG" | awk '{print $1}'))"
  with_timeout "$GATEKEEPER_TIMEOUT" xcrun stapler validate "$DMG" >/dev/null 2>&1
  case $? in
    0) pass "notarization ticket stapled to the DMG" ;;
    "$TIMEOUT_STATUS") fail "stapler validate on the DMG did not finish in ${GATEKEEPER_TIMEOUT}s" ;;
    *) fail "DMG has no stapled ticket" ;;
  esac
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
