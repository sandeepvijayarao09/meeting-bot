# Release & store-submission guide

How each MB app ships, what the repo already prepares (verified by `make check` + the
per-app builds below), and the steps that need **your** developer accounts / credentials.
Privacy-policy text is in [PRIVACY.md](PRIVACY.md); since the repo is public it already has
a usable URL — <https://github.com/sandeepvijayarao09/meeting-bot/blob/main/PRIVACY.md> — so paste that into every store listing.

> Targets: **Chrome extension → Web Store** · **iOS → App Store** · **macOS → notarized
> download now, Mac App Store next (native migration underway)** · **Android → planned.**

## ⚠️ Before any public launch: verify on real hardware

`make check` is green (Python 216 + coverage, Swift/MeetingBotKit 20, iOS build+tests,
extension) and every app produces a release artifact — but automated tests **mock the
network and cannot exercise the GUI/device**. Before shipping, on real hardware:

1. **macOS:** record a real meeting → confirm mic + system-audio capture, Stop → note saved.
2. **iOS:** run on a device → confirm mic capture, background/lock, transcript + note.
3. **A reachable NIM key** → confirm a real cloud summary returns (the pipeline now bounds
   the call at 90s and falls back to transcript-only on failure, but verify the happy path).

Runtime bugs have slipped past the automated tests before (lost short recordings, a
spurious "user stopped the stream" error, a 10-minute NIM hang), so device testing is a
hard gate, not a formality.

## Prerequisites you must provide (gated on accounts/credentials)

| Need | For |
|---|---|
| Apple Developer Program ($99/yr) | iOS App Store + macOS notarization/App Store |
| Developer ID Application cert + a `notarytool` profile | macOS notarized DMG |
| Apple Distribution cert + provisioning / App Store Connect app records | iOS (+ macOS App Store) |
| Chrome Web Store developer account ($5 once) | Chrome extension |
| Google Play account ($25 once) + upload keystore | Play Store (after the Android app exists) |
| ~~A public **privacy-policy URL**~~ — done, the repo is public: [app](https://github.com/sandeepvijayarao09/meeting-bot/blob/main/PRIVACY.md) · [extension](https://github.com/sandeepvijayarao09/meeting-bot/blob/main/chrome-extension/PRIVACY.md) | all stores |
| Real-device screenshots, descriptions, keywords, age rating | all store listings |

`security find-identity -v -p codesigning` currently shows **no distribution identities on
this machine**, so nothing can be signed for distribution yet. Installing the certificate
and creating the notary profile are the first two steps of
[§3 macOS](#ship-a-notarized-download); do them before any signing step below.

## Bring-your-own-key (all AI features)

Summaries use **your** NVIDIA NIM key (free at https://build.nvidia.com). No key is bundled.
- **CLI / backend:** `mbot set-key` (or set `NVIDIA_API_KEY` in `~/.config/meetingbot/.env`).
- **macOS app:** Settings → "API key".  **iOS app:** Settings → API key (stored in Keychain).
- **Chrome extension:** keyless — summarization runs through the paired macOS app's key.

---

## 1. Chrome extension → Chrome Web Store  ✅ artifact-ready

**Prepared:** Manifest V3, minimal permissions (`tabCapture`, `offscreen`, `activeTab` — no
host permissions), no remote code, no bundled secrets. `make ext-check` + `make ext-test`
pass; `make ext-package` produces the upload artifact.

**You do:**
1. `make ext-package` → `dist/meeting-bot-extension-<version>.zip` (production files only).
2. Privacy-policy URL (already live, the repo is public):
   <https://github.com/sandeepvijayarao09/meeting-bot/blob/main/chrome-extension/PRIVACY.md>
3. In the Web Store dashboard: upload the zip, paste the privacy-policy URL in the Privacy
   tab, fill the single-purpose + data-usage forms, add screenshots (≥1; use
   [store/](store/) assets), and submit. Listing copy: [store/listing.md](store/listing.md).

**Note:** the extension streams tab+mic audio to the **local** macOS app (127.0.0.1) which
does transcription/summary — so it's useful only alongside the Mac app. Say so in the listing.

---

## 2. iOS → Apple App Store  ✅ code-ready

**Prepared:** native SwiftUI, on-device transcription (Apple Speech), NIM summary via BYO
key (Keychain-stored); background-audio mode + interruption/route-change handling;
permissions requested up-front; privacy manifest ([PrivacyInfo.xcprivacy](ios/MB/Sources/PrivacyInfo.xcprivacy));
usage strings (mic + speech); `ITSAppUsesNonExemptEncryption=false`; bundle `ai.meetingbot.mb.ios`.
Builds for device-arch Release + unit tests pass (`make ios-test`).

**You do:**
1. In `ios/MB/project.yml` set `DEVELOPMENT_TEAM`, drop `CODE_SIGNING_ALLOWED: NO` for
   archive builds; `xcodegen generate`.
2. Create the App Store Connect record (bundle id above); set the privacy-policy URL.
3. **App Privacy form:** the app itself collects nothing; when the user sets a key, the
   *transcript text* is sent to NVIDIA (a user-configured service, not retained by us). The
   defensible declaration is **User Content → not linked, not used for tracking**, with an
   in-app disclosure (already shown at the key field). Do **not** advertise "100% private"
   without the transcript-to-cloud caveat.
4. Archive + upload:
   ```bash
   cd ios/MB && xcodegen generate
   xcodebuild -project MB.xcodeproj -scheme MB -sdk iphoneos \
     -destination 'generic/platform=iOS' -archivePath build/MB.xcarchive archive
   xcodebuild -exportArchive -archivePath build/MB.xcarchive \
     -exportOptionsPlist ExportOptions.plist -exportPath build/export
   xcrun altool --upload-app -f build/export/*.ipa -t ios --apiKey ... --apiIssuer ...
   ```
5. Screenshots (6.7" + 6.1"), description, keywords; submit. **Review note:** recording may
   require participant consent; the app surfaces on-device processing.

---

## 3. macOS → notarized download (ship now) + Mac App Store (next)

**Prepared:** `scripts/build-app.sh` version-stamps (git commit
count, override with `MB_VERSION`/`MB_BUILD`), embeds the PyInstaller `mbot` sidecar, and
signs **inside-out** (every nested Mach-O incl. framework binaries) so notarization won't
reject unsigned payloads — verified end-to-end ad-hoc (`codesign --verify --deep --strict`
passes, embedded `mbot` runs). Hardened-runtime entitlements + privacy manifest bundled.
The app is also a standard, archivable Xcode project (`mac/project.yml` → `make mac-project`,
mirroring iOS) for IDE work and a Developer ID `Product ▸ Archive`; `build-app.sh` remains
the release path because it bundles + signs the `mbot` sidecar the DMG needs.

**Never trust the source tree as evidence about the bundle.** The sidecar is a separate
PyInstaller build; `make release-check` (below) is what actually inspects it. `build-app.sh`
also rebuilds the sidecar whenever its inputs change (`build-sidecar.sh --if-stale`
fingerprints `meetingbot/`, `prompts/`, `uv.lock`, `pyproject.toml`), so `dist/` can no
longer leak a previous release's build into a new one.

### Ship a notarized download

Everything below the two credential steps is automated and verified; those two steps need
your Apple account and cannot be scripted for you.

**Step 1 (you, once): install a Developer ID Application certificate.**
Xcode ▸ Settings ▸ Accounts ▸ (your Apple ID) ▸ Manage Certificates ▸ **+** ▸ *Developer ID
Application*. This requires an active $99/yr Apple Developer Program membership; a free
account cannot create Developer ID certificates. Then confirm and copy the exact identity
string — you need the `Developer ID Application: NAME (TEAMID)` text verbatim:
```bash
security find-identity -v -p codesigning
```

**Step 2 (you, once): create a notarytool credential profile.**
Generate an app-specific password at <https://account.apple.com> ▸ Sign-In and Security ▸
App-Specific Passwords (your normal Apple ID password will not work), then:
```bash
xcrun notarytool store-credentials meetingbot-notary \
  --apple-id you@example.com --team-id TEAMID --password xxxx-xxxx-xxxx-xxxx
```

**Step 3: build, notarize, staple, verify.**
```bash
DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" make notarize
```
`scripts/sign-notarize.sh` verifies both credentials **before** the ~15-minute build, signs
inside-out with the hardened runtime and a secure timestamp, notarizes and staples the
**app**, packages the stapled app into the DMG, then signs, notarizes and staples the DMG
too, and finishes by running the preflight below. Stapling the app matters: a DMG-only
ticket leaves the copy in `/Applications` unverifiable on an offline Mac.

If Apple rejects the submission, read the actual reason — it is never guesswork:
```bash
xcrun notarytool log <submission-id> --keychain-profile meetingbot-notary
```

**Step 4: verify the artifact, always.**
```bash
make release-check
```
This audits `dist/MB.app` and its DMG — signature validity, Developer ID authority and team,
hardened runtime, secure timestamp, entitlements, every nested Mach-O, the stapled ticket,
the Gatekeeper verdict, the version stamp, and a sidecar smoke test. It must end with
`✓ fit for public distribution`. Both defects that shipped in the 1.0.0 DMG (missing prompt
templates, a stale sidecar) were invisible to `make check` and are caught here.

**Step 5: publish it.** Notarizing from the `v1.0.1` tag reproduces the same build number,
so the DMG keeps its exact filename and you can replace the asset in place rather than
cutting a version whose only change is a better signature:
```bash
git checkout v1.0.1
DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" make notarize
make release-check                                    # must say: fit for public distribution
gh release upload v1.0.1 dist/MB-1.0.1-34.dmg --clobber
```
Then update [INSTALL.md](INSTALL.md) §1 and the release notes — the right-click ▸ Open
workaround no longer applies, and telling users to bypass Gatekeeper when they no longer
need to is worse than useless.

**Size:** ~860 MB installed (bundled Python + MLX-Whisper sidecar), compressing to ~312 MB
for download. The native migration (below) removes the sidecar and shrinks this dramatically.

**Mac App Store (native migration):** the app store
requires the App Sandbox, which forbids the Python subprocess. The migration path: the
macOS app can run the **native in-process `MeetingBotKit` pipeline** (the same one iOS uses)
behind `MBOT_NATIVE_PIPELINE=1` (Phase A done — flag-gated, builds/tests green). Remaining
before MAS submission: validate the native path on a real Mac, make it the default, remove
the `Process`/sidecar paths, add `com.apple.security.app-sandbox` + `network.client`
entitlements (drop `allow-jit`/`disable-library-validation`), and switch to an Apple
Distribution cert. This also **eliminates the ~860 MB sidecar**, shrinking the app dramatically.

---

## 4. Android → Google Play  🔜 planned (no app yet)

`android/` is a README only — no code. A Play release needs a native Kotlin/Compose app
first (on-device Gemma via MediaPipe/LiteRT-LM; Android `SpeechRecognizer` or Whisper),
re-implementing the record → transcribe → refine → summarize → note flow. Then: signed AAB
(Play App Signing), Data Safety form (no data collected), target-API compliance, privacy
URL. Scope + estimate this on its own; it's a multi-week build.

---

## Versioning

Build numbers auto-increment from the git commit count; marketing version defaults to the
plist value (override both with `MB_VERSION` / `MB_BUILD`).

Nothing reconciles these files automatically, so bump every one that the release touches:

| File | Field | Covers |
|---|---|---|
| `pyproject.toml` | `version` | Python package / CLI |
| `meetingbot/__init__.py` | `__version__` | Python package / CLI |
| `mac/MeetingBot/Info.plist` | `CFBundleShortVersionString` | **the release DMG** (`build-app.sh` reads it, and `build-dmg.sh` names the file from it) |
| `mac/project.yml` | `MARKETING_VERSION` | the Xcode/archive build of the same app |
| `ios/MB/project.yml` | `CFBundleShortVersionString` + `MARKETING_VERSION` | iOS app |
| `chrome-extension/manifest.json` + `package.json` | `version` | extension (also names the Web Store zip) |
| `INSTALL.md` | download filenames | what users are told to download |

Platforms may version independently — a Python-only patch does not need to re-version
iOS or the extension — but say so in the CHANGELOG entry. `tests/test_version.py` enforces
the pairs that must never diverge (package vs. `pyproject`, and the macOS plist vs.
`mac/project.yml` vs. the embedded Python sidecar). Then tag the release (`vX.Y.Z`) and
attach the DMG + extension zip to the GitHub release.
