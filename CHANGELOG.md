# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MIT license, packaging metadata, GitHub Actions CI, and contribution/security docs.

## [0.1.0] - 2026-06-13

### Added
- **Local capture** (`mac/CaptureKit`): microphone + system audio via ScreenCaptureKit,
  chunked 16 kHz WAVs + manifest. Shared by the `audiocap` CLI and the app.
- **Native SwiftUI menu bar app** (`MeetingBot.app`) with `.app` bundle + DMG build
  and sign/notarize scripts.
- **Local transcription** with mlx-whisper; mic/system streams merged into Me/Them turns.
- **Summaries** via NVIDIA NIM (OpenAI-compatible), optional and key-gated.
- **Notes** as Markdown with SQLite FTS5 search; exporters for **Apple Notes** and
  **Google Docs** alongside Markdown.
- **Chrome extension** (MV3) for browser-tab meetings, streaming to a localhost server.
- **CLI** `mbot`: record, process, transcribe, summarize, export, search, doctor, serve.
- Quality gate (`make check`): ruff, mypy --strict, pytest, swift build + format,
  extension tsc.

[Unreleased]: https://github.com/sandeepvijayarao09/meeting-bot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sandeepvijayarao09/meeting-bot/releases/tag/v0.1.0
