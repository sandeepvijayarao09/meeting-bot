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
- **The only outbound network call** is the optional summarization request to NVIDIA NIM,
  which sends finished **transcript text** (never audio) and runs only if you configure
  an API key. Google Docs export, if enabled, sends the note via your own OAuth token.
- **Secrets** (NVIDIA key, Google OAuth client/token) live in `~/.config/meetingbot/`
  and are never committed. The Chrome extension talks only to `127.0.0.1`.

## Supported versions

This is pre-1.0 software; security fixes are applied to `main`.
