# Contributing to Meeting Bot

Thanks for your interest! This project is local-first and privacy-first; please keep
those principles in mind for any change (raw audio must never leave the device; only
finished transcript text may be sent to a summarization API, and only opt-in).

## Development setup

Requirements: macOS (Apple Silicon), Xcode command-line tools, [uv](https://docs.astral.sh/uv/),
Node 20+.

```bash
git clone https://github.com/sandeepvijayarao09/meeting-bot
cd meeting-bot
uv sync
cd mac && swift build -c release && cd ..
```

## The quality gate

Everything must pass before a PR is merged — this is exactly what CI runs:

```bash
make check
```

It runs: `ruff` (lint + format), `mypy --strict`, `pytest`, `swift build`,
`swift format lint`, and the extension `tsc --noEmit`.

- **Python**: fully type-annotated, `mypy --strict` clean, `ruff` clean. Add tests in
  `tests/` for new behavior (we mock the network/LLM and the Whisper model — no test
  hits the cloud or downloads weights).
- **Swift** (`mac/`): no force-unwraps; `swift format` clean; keep capture code in
  `CaptureKit` so the CLI and the app share one implementation.
- **Extension** (`chrome-extension/`): JS with JSDoc types, `tsc --noEmit` clean against
  `chrome-types`.

## Commit / PR conventions

- Keep changes focused; one logical change per PR.
- Write a clear description; link any related issue.
- Make sure `make check` is green and include new tests.
- Be kind in review (see `CODE_OF_CONDUCT.md`).

## Project layout

| Path | What |
|---|---|
| `mac/` | Swift package: `CaptureKit` lib + `audiocap` CLI + `MeetingBot` SwiftUI app |
| `meetingbot/` | Python pipeline: transcribe, summarize, notes + search, exporters, CLI, server |
| `chrome-extension/` | MV3 extension for browser-tab meetings |
| `scripts/` | install, app/DMG build, sign + notarize, benchmarks |
| `tests/` | pytest suite |

See `ROADMAP.md` for planned work and good first issues.
