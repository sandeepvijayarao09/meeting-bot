# Contributing to Meeting Bot

Thanks for your interest! This project is local-first and privacy-first; please keep
those principles in mind for any change (raw audio must never leave the device; only
finished transcript text may be sent to a summarization API, and only opt-in).

## Development setup

Requirements: macOS (Apple Silicon), full Xcode (for the iOS simulator),
[uv](https://docs.astral.sh/uv/), Node 20+, and [XcodeGen](https://github.com/yonaskolb/XcodeGen)
(`brew install xcodegen`, for the iOS app project).

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

It runs: `ruff` (lint + format), `mypy --strict`, `pytest` (with **≥ 80 % coverage**),
`swift build`, `swift format lint --strict`, `swift test`, the extension `tsc --noEmit`
+ Node tests, and the **iOS build + unit tests** on a simulator.

- **Python**: fully type-annotated, `mypy --strict` clean, `ruff` clean, coverage ≥ 80 %.
  Add tests in `tests/` for new behavior (we mock the network/LLM and the Whisper model —
  no test hits the cloud or downloads weights).
- **Swift** (`mac/`): no force-unwraps; `swift format --strict` clean; keep capture code in
  `CaptureKit` and shared pipeline logic in `MeetingBotKit` so macOS/iOS/CLI share one
  implementation. Unit tests live in `mac/Tests/` and run via `swift test`.
- **iOS** (`ios/MB/`): generated from `project.yml` via XcodeGen (`make ios-build` /
  `make ios-test`); tests in `ios/MB/Tests/`.
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
| `mac/` | Swift package: `CaptureKit` + `MeetingBotKit` libs + `audiocap` CLI + `MeetingBot` macOS app |
| `ios/MB/` | iOS app (XcodeGen `project.yml`); reuses `CaptureKit` + `MeetingBotKit` |
| `meetingbot/` | Python pipeline: transcribe, summarize, notes + search, exporters, CLI, server |
| `chrome-extension/` | MV3 extension for browser-tab meetings |
| `scripts/` | install, app/DMG build, sign + notarize, benchmarks |
| `tests/` | pytest suite |

See `ROADMAP.md` for planned work and good first issues.
