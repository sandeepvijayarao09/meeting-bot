# Distributing MeetingBot.app

The native menu bar app lives in `mac/` (a SwiftPM package: `CaptureKit` library +
`audiocap` CLI + `MeetingBot` app). These scripts turn it into a shippable, signed,
notarized `.app` + DMG.

## TL;DR

```bash
make app                       # build dist/MeetingBot.app (ad-hoc signed, runs locally)
open dist/MeetingBot.app       # 🎤 appears in the menu bar
bash scripts/build-dmg.sh      # dist/MeetingBot-<version>.dmg (drag-to-Applications)
```

For a build other people can run without Gatekeeper warnings, you need an Apple
Developer account and your own credentials (the one step I can't do for you):

```bash
DEVELOPER_ID="Developer ID Application: Your Name (TEAMID)" \
NOTARY_PROFILE=meetingbot-notary \
bash scripts/sign-notarize.sh
```

## The pieces

| Script | What it does |
|---|---|
| `scripts/build-app.sh` | compiles the app, assembles `MeetingBot.app` (Info.plist, entitlements, icon), signs it (ad-hoc, or Developer ID if `DEVELOPER_ID` is set) |
| `scripts/build-sidecar.sh` | freezes the `mbot` Python pipeline into a standalone binary via PyInstaller, so users need no Python/venv |
| `scripts/build-dmg.sh` | packages the app into a drag-to-install DMG |
| `scripts/sign-notarize.sh` | full release: Developer-ID sign → notarize → staple |

## How the app finds the transcription pipeline

The app captures audio natively (CaptureKit) and shells out to `mbot process <dir>`
for local Whisper transcription + NIM summary + export. It locates `mbot` in this
order (`mac/Sources/MeetingBot/Paths.swift`):

1. **Bundled sidecar** — `MeetingBot.app/Contents/Resources/mbot` (a shipped build).
2. **`MBOT_BIN`** env var — an explicit path.
3. **Dev venv** — `<project>/.venv/bin/mbot` (what you get during development).

So during development `make app` + `open` Just Works against your venv. For a real
release, bundle the sidecar:

```bash
bash scripts/build-sidecar.sh          # -> dist/sidecar/mbot
EMBED_SIDECAR=1 bash scripts/build-app.sh
```

## One-time Apple setup for notarization

1. Enroll in the Apple Developer Program ($99/yr).
2. Create a **Developer ID Application** certificate (Xcode → Settings → Accounts →
   Manage Certificates, or developer.apple.com) and install it in your login keychain.
3. Store a notarytool credential profile:
   ```bash
   xcrun notarytool store-credentials meetingbot-notary \
     --apple-id you@example.com --team-id TEAMID --password <app-specific-password>
   ```
   (App-specific password from appleid.apple.com → Sign-In and Security.)
4. Run `scripts/sign-notarize.sh` with `DEVELOPER_ID` + `NOTARY_PROFILE` set.

## Size note / going fully native

Bundling the Python sidecar with `mlx-whisper` makes the app a few hundred MB (the
Whisper model itself downloads on first run to `~/.cache`). If you want a small,
single-binary app, the path is to replace the Python transcription with
[whisper.cpp](https://github.com/ggerganov/whisper.cpp) called directly from Swift —
then `CaptureKit` + a Whisper Swift wrapper make the whole product native, and the
Python pipeline becomes optional (CLI/extension only). The summary step can call
NVIDIA NIM directly over HTTPS from Swift. This wasn't done here because you chose to
keep the Python pipeline, but the architecture (app → `mbot process`) is deliberately
swappable: replace that one call site and the rest is unaffected.

## Permissions on first launch

The app's `Info.plist` declares microphone + audio-capture usage strings, and the
entitlements request the audio-input device. On first recording, macOS prompts for
**Microphone** and **Screen Recording** (system audio rides on screen recording).
For a notarized app these prompts attribute to "Meeting Bot" itself rather than your
terminal.
