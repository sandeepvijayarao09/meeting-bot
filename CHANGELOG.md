# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Summaries, Ask, refinement and transforms now run on device via Gemma 4; NVIDIA
  NIM is gone.** The product's claim was that a meeting never leaves your Mac, and
  the summary step was the one place that leaked — finished transcript text went to
  NVIDIA's cloud, and you needed an account and an API key before the app was much
  use. Generation now happens locally through MLX, which was already bundled for
  Whisper, so the marginal cost is ~75 MB of tokenizer dependencies rather than a
  new runtime.

  - New `meetingbot/llm.py` is the single seam; `summarize.complete()` delegates to
    it, so all four consumers changed in one place.
  - `MBOT_LLM_BACKEND` selects `local` (default, Gemma 4 E4B via MLX), `cloud` (any
    OpenAI-compatible endpoint — vendor-neutral, no provider hard-coded) or `none`
    (transcript-only notes).
  - `NVIDIA_API_KEY` → `MBOT_LLM_API_KEY`, and it is now only consulted for the cloud
    backend. `MBOT_NIM_*` → `MBOT_LLM_*`. Swift's `NIMProvider` → `OpenAICompatProvider`.
  - The gpt-oss `reasoning_effort` shim is deleted; it was specific to the model being
    dropped.

  **Two honest trade-offs.** Gemma 4 E4B is a ~4B-class model where gpt-oss-120b was
  120B, so summaries of long multi-topic meetings will be weaker; and on-device
  generation is slower than a datacenter. In exchange there is no key, no account, no
  per-meeting cost, and nothing to disclose in a privacy policy. `MBOT_LLM_BACKEND=cloud`
  remains for anyone who wants the other side of that trade.

  iOS deliberately keeps the cloud backend: the on-device build is ~5 GB, which is not
  a reasonable footprint on most iPhones.

### Changed (packaging)
- **The macOS download is 47% smaller: 312 MB → 164 MB (861 MB → 406 MB installed.)**
  PyInstaller resolves imports statically, so it was bundling everything *reachable*
  rather than everything *reached*. Removed, after verifying each is unreachable:
  - **PyTorch (319 MB)** — `mlx-whisper` declares it, but only its `torch_whisper.py`
    imports it, and nothing imports that module; it converts PyTorch checkpoints to
    MLX, which is irrelevant when loading an already-converted `mlx-community` repo.
  - **582 Google API discovery documents (96 MB)** — the Docs exporter builds its
    services with `cache_discovery=False`, so not one was ever read. Only the two
    APIs we actually build are kept.
  - **Dev tooling (mypy, coverage)** that reached the bundle via the build venv.

  `numba`, `llvmlite` and `scipy` (147 MB) are deliberately kept: `mlx_whisper`'s
  `transcribe.py` imports `.timing` at module scope, so excluding them shrinks the
  bundle and breaks transcription. Tests pin both halves of that decision.

### Fixed
- **Gemma 4's chain of thought leaked into every note.** The model reasons out loud
  inside `<|channel>…<channel|>` tokens before answering. Unstripped, that block was
  written verbatim into the user's note, and `generate_title` turned its first line
  into the title *and* the filename — the first real summary produced
  `2026-10-22-2308-channel-thought.md` titled `<|channel>thought`. Reasoning measurably
  improves the summaries, so it stays on and is now stripped from the output, with
  token headroom (`MBOT_GEMMA_THINKING_HEADROOM`) so the answer is not truncated by
  the thinking that precedes it. No unit test could have caught this; it took running
  a real meeting through the real model.
- **The frozen sidecar printed two bogus usage errors and killed its semaphore
  tracker on every transcription.** In a PyInstaller build `sys.executable` is the
  `mbot` binary, so when multiprocessing started a child it re-ran `mbot` with
  Python's own flags; Typer rejected them (`No such option: -B`), the child died,
  and `resource_tracker` logged `process died unexpectedly, relaunching` while
  leaking the semaphores it exists to clean up. The entry point now calls
  `multiprocessing.freeze_support()` before anything touches argv. Present in
  1.0.1; found by running a real transcription against the shipped bundle, which
  no automated test does.

### Added
- **`mbot download-model --llm`** and a **Download button in Settings ▸ Summaries &
  Ask** — the ~5 GB Gemma model is fetched on request, never bundled, so the app
  download stays at 164 MB.
- **`mbot download-model`** and a **Download button in Settings ▸ Speech model** —
  the ~1.5 GB speech model is not bundled, and previously it was fetched implicitly
  the first time anything transcribed. That put a multi-minute download in the middle
  of a user's first meeting with no progress indication and no way to distinguish it
  from a hang. The fetch is now explicit, resumable, and offered up front.
- **`mbot doctor` reports whether the model is actually cached**, with the one command
  that fixes it, instead of the unfalsifiable "downloads on first use".

## [1.0.1] - 2026-08-29

Security + correctness patch. Marketing version bumped for the Python/CLI and
macOS app (which embeds the Python sidecar); the iOS app and Chrome extension
contain none of these changes and stay at 1.0.0.

### Added
- **`mbot --version` (`-V`)** — the CLI could not report its own version, which
  made bug reports ambiguous. `mbot doctor` now prints it too.
- **On-device LLM scaffold (Gemma 4 E4B via LiteRT-LM)** — an opt-in, fully-local
  summary backend mirroring Google AI Edge Eloquent, selected by `MBOT_LLM=local`
  (`cloud` remains the default; no model is bundled, so shipped behavior is unchanged).
  The `LLMProvider` seam, `GemmaProvider`, the `GemmaModel` descriptor, and a
  transcript-only fallback are in place and unit-tested; the on-device LiteRT-LM
  inference is a device-side finish. See [docs/on-device-llm.md](docs/on-device-llm.md).

### Security
- **Capture WebSocket now enforces an origin allow-list.** `mbot serve` (the local
  server the Chrome extension streams to) rejects WebSocket handshakes from any web-page
  origin, admitting only browser-extension origins (and originless CLI/native clients).
  Closes a cross-site WebSocket hijacking vector where a visited web page could drive
  recordings on `127.0.0.1`. Pin one exact origin with `MBOT_ALLOWED_ORIGIN`.
- **Secrets are written owner-only (`0600`).** The NVIDIA API key (`~/.config/meetingbot/.env`)
  and the Google OAuth token are now `chmod 600`, and the config dir is `0700`.

### Fixed
- **The macOS app could not summarize anything.** `config.PROMPTS_DIR` was resolved
  relative to the package directory, which inside the PyInstaller sidecar is
  `MB.app/Contents/Resources/_internal` — and `prompts/` was never bundled at all, so
  every summary died on `FileNotFoundError` reading its template. The sidecar now ships
  the templates (`--add-data`) and `config` resolves bundled resources from
  `sys._MEIPASS`. The 1.0.0 DMG was affected; running from a source checkout was not.
- **The frozen build no longer defaults to writing inside the app bundle.** Without an
  `MBOT_NOTES_DIR` override, notes resolved to `Contents/Resources/_internal/notes` — a
  read-only location in a signed app. Frozen builds now default to
  `~/.local/share/meetingbot/notes`, matching `Paths.notesDirectory` in the app.
- **Release builds no longer embed a stale sidecar.** `build-app.sh` only checked that
  `dist/sidecar/mbot` *existed*, and `dist/` survives across releases — so a months-old
  sidecar was silently re-embedded into a freshly versioned app. `build-sidecar.sh` now
  fingerprints its inputs and `--if-stale` rebuilds whenever they change.
- **`mbot doctor` verifies the prompt template** (and stops reporting a missing
  `audiocap` as a failure in the bundled sidecar, which never captures — the app does).
- **macOS app bundle now reports 1.0.1.** `mac/MeetingBot/Info.plist` was left at
  1.0.0 when the version was bumped elsewhere, so `scripts/build-app.sh` (which reads
  the marketing version from that plist) would have stamped the app — and named the
  DMG — `1.0.0`. `tests/test_version.py` now fails on that drift.
- **`websockets` floor raised to `>=15`.** The capture server passes `re.Pattern` entries
  to `serve(origins=...)`, which only websockets 15.0+ matches; on 13.x/14.x every
  browser-extension handshake was rejected with 403. The lockfile already pinned 16.0, so
  only non-locked installs were affected.

## [1.0.0] - 2026-07-08

First public release. Marketing version bumped to 1.0.0 across all platforms
(Python/CLI, macOS app, iOS app, Chrome extension).

### Added
- **Store-submission readiness**: privacy manifests (`PrivacyInfo.xcprivacy`) for the iOS
  and macOS apps (no tracking, no data collection, required-reason APIs declared), an
  App Store-compliant 1024² opaque app icon for iOS, export-compliance flag, plus
  [PRIVACY.md](PRIVACY.md) (privacy policy) and [RELEASE.md](RELEASE.md) (per-store
  submission checklist). Decisions: iOS → App Store; macOS → Developer ID + notarization
  (the sidecar/ScreenCaptureKit architecture is incompatible with the Mac App Store
  sandbox); Android/Play Store scoped as a future milestone ([android/README.md](android/README.md)).
- **Industry-standard CI/test gate**: `make check` now also runs `swift test`, the iOS
  build + unit tests on a simulator, and pytest with a ≥80% coverage floor; CI runs the
  same gate verbatim.
- **iOS app** (`ios/MB`, Milestone 1): a mic-based, local-first notetaker for in-person
  meetings — on-device transcription (Apple Speech), Eloquent-style local refine, notes,
  and an optional NVIDIA NIM cloud summary. Built on a new multiplatform Swift package:
  `CaptureKit` is now iOS-ready (system-audio capture is macOS-only and `#if`-guarded) and
  a dependency-free **`MeetingBotKit`** holds the shared pipeline — `Refiner` (a Swift port
  of `refine.py` Tier-1, unit-tested for parity), transcript merge/format, and the
  `ASRProvider`/`LLMProvider` protocols. On-device **Gemma 4 E4B** (LiteRT-LM) lands in M2.
- **Transcript refinement** (Eloquent-style, `meetingbot/refine.py`): on-device cleanup
  of filler words, stutters, and false starts — always-on, deterministic, `$0`
  (`MBOT_REFINE=local`, the default) — with an optional NIM cloud polish (`cloud`).
  Notes and summaries now use the cleaned transcript; the raw `transcript.jsonl` is
  preserved verbatim (talk-time analytics still reflects what was actually said).
- **AI text tools** (`meetingbot/transform.py`): `mbot transform key_points|formal|short|long`
  reshapes a meeting's transcript on demand, plus `mbot refine` to preview the cleaned
  transcript (`--tier off` for verbatim).
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

[Unreleased]: https://github.com/sandeepvijayarao09/meeting-bot/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/sandeepvijayarao09/meeting-bot/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/sandeepvijayarao09/meeting-bot/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/sandeepvijayarao09/meeting-bot/releases/tag/v0.1.0
