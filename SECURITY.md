# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's
[private vulnerability reporting](https://github.com/sandeepvijayarao09/meeting-bot/security/advisories/new)
or by email to vijayarao.s@northeastern.edu. Do not open a public issue for a
suspected vulnerability.

We aim to acknowledge reports within a few days.

## Security & privacy model

Meeting Bot is local-first by design:

- **Audio never leaves your device.** Microphone and system audio are captured locally,
  written to your machine, and transcribed locally with Whisper.
- **Your content stays local.** The only time meeting content leaves your device is the
  optional NVIDIA NIM summary (finished **transcript text**, never audio, and only with
  your own API key) and, if you enable it, Google Docs export (the note, via your own
  OAuth token). On first run MB also downloads the local Whisper (and optional Gemma)
  model from its public model host — a one-time software download that transfers **none
  of your audio, transcripts, or personal data**.
- **Secrets** (NVIDIA key, Google OAuth client/token) live in `~/.config/meetingbot/`
  with owner-only (`0600`) permissions and are never committed.
- **The local capture server** (`mbot serve`, used by the Chrome extension) binds to
  `127.0.0.1` only and accepts WebSocket connections only from the extension's origin,
  rejecting any web page (defends against cross-site WebSocket hijacking).

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x   | ✅        |
| < 1.0   | ❌        |

Security fixes land on `main` and ship in the next `1.0.x` release.
