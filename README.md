# Meeting Bot

**A local-first AI meeting notetaker for macOS.** Like Granola or Otter, but your audio
never leaves your Mac — it's transcribed on-device with Whisper, and only the finished
text is (optionally) summarized via a free API.

[![CI](https://github.com/sandeepvijayarao09/meeting-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/sandeepvijayarao09/meeting-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform: macOS](https://img.shields.io/badge/platform-macOS%2014%2B-blue)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Swift 5.9](https://img.shields.io/badge/swift-5.9-orange)

No bot joins your calls. It captures the meeting audio already playing on your Mac
(any app: Zoom, Meet, Teams, FaceTime, or a browser tab), so it works everywhere and
needs no meeting-platform integration.

- 🔒 **Private by default** — raw audio is transcribed locally and never uploaded.
- 🗣️ **Speaker attribution** — your mic is "Me", system audio is "Them" (+ optional Speaker A/B/C diarization).
- 📝 **Structured notes** — summary, decisions, action items, full transcript per meeting.
- 🧩 **Templates** — general, standup, 1:1, interview, sales call (Granola-style "Recipes").
- ✨ **Clean transcripts & AI text tools** — Eloquent-style on-device cleanup (strips "um"/stutters/false starts) plus on-demand Key points / Formal / Short / Long rewrites.
- 📊 **Talk-time analytics** — Me/Them ratio, words, turns, longest monologue per note.
- 📤 **Exports** — Markdown, Apple Notes (iCloud or on-device), Google Docs.
- 🔎 **Search & Ask** — full-text across every meeting, plus AI Q&A over your meetings.
- 💻 **Three front-ends** — a native macOS SwiftUI app, a Chrome extension, and an iOS app (mic-based, on-device; see [ios/README.md](ios/README.md)).
- 💸 **$0** — local Whisper + NVIDIA NIM's free tier (~500 meetings on signup credits).

> **Why local-first?** Cloud notetakers upload your meeting audio to their servers.
> Meeting Bot keeps the recording and transcript on your machine; the only optional
> network call sends finished transcript *text* to summarize it — and you can point
> that at a local model instead.

See [ROADMAP.md](ROADMAP.md) for what's planned (speaker diarization, in-app notes
browser, calendar integration, ask-your-meetings) and [CONTRIBUTING.md](CONTRIBUTING.md)
to help.

## Setup (once)

1. **NVIDIA NIM key (free):** sign up at <https://build.nvidia.com> (email only), create
   an API key, then:

   ```bash
   mkdir -p ~/.config/meetingbot
   echo 'NVIDIA_API_KEY=nvapi-...' > ~/.config/meetingbot/.env
   ```

   No key yet? Everything still works — transcripts are saved and you run
   `mbot summarize` once the key exists.

2. **Build & install** (audiocap is already built if `.build/release/audiocap` exists):

   ```bash
   cd mac && swift build -c release && cd ..
   uv sync
   ```

3. **Check:** `uv run mbot doctor`

4. **Permissions:** the first `mbot record` triggers macOS prompts for **Microphone**
   and **Screen Recording** (system audio rides on the screen-capture permission).
   Approve both for your terminal. If you miss the prompt: System Settings →
   Privacy & Security.

## Daily use

```bash
uv run mbot record -t "Design review"   # Ctrl+C when the meeting ends
uv run mbot list                        # recent notes
uv run mbot search "budget"             # full-text search
uv run mbot open                        # open the latest note
uv run mbot status                      # is something recording?
uv run mbot stop                        # stop a recording from another shell
uv run mbot summarize                   # (re)summarize the latest session
uv run mbot transcribe                  # re-run local transcription for a session
uv run mbot refine                      # preview the cleaned-up transcript (--tier off = verbatim)
uv run mbot transform key_points        # AI text tools: key_points | formal | short | long
```

Menu bar app instead of the terminal:

```bash
uv run mbot-menubar    # 🎙 quick Python menu bar (dev): Start/Stop, open notes
```

### Native macOS app (recommended)

The native **SwiftUI** app in `mac/` is the real product (one `.app`, no terminal):
a Dock app with a Meetings window and a menu-bar 🎤. It captures audio in-process and
hands each meeting to the local pipeline.

```bash
make app                  # build dist/MB.app
open dist/MB.app          # opens the Meetings window; 🎤 in the menu bar
```

**Click-to-record only.** The app does nothing until you click **Start Recording** —
there's no meeting auto-detection, no background mic watching, and nothing auto-starts
at login or runs as a daemon. Open it when you want it; quit it when you don't. Click
Stop to make the note. (It reads your calendar *only when you click Start*, to title
the note — like Granola.)

Packaging it into a signed, notarized DMG for other Macs is documented in
[DISTRIBUTION.md](DISTRIBUTION.md).

## Chrome extension (for browser meetings)

For Google Meet / Zoom web / Teams web, the extension captures **only the meeting
tab's audio** + your mic (no Spotify/notification pollution) and streams it to the
same local pipeline.

Setup (once):

1. `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select the
   `chrome-extension/` folder.
2. Click the 🎙 toolbar icon → **Enable microphone** (one-time permission page).

Use:

```bash
uv run mbot serve      # keep running while you take browser meetings
```

Then in the meeting tab: 🎙 icon → **Start recording this tab**. Stop the same way —
the note is written and opened automatically. Notes, search, and `mbot summarize`
work identically for extension-recorded meetings.

While recording, you can jot rough notes into the session's `notes.txt` (path is
printed at start) — the summarizer expands and corrects them against the transcript,
Granola-style.

## Where notes are saved (Apple Notes, Google Docs, on device or cloud)

Every meeting always writes a local Markdown note (the source of truth that search
reads). You can additionally fan out to Apple Notes and/or Google Docs by setting
`MBOT_EXPORTERS`:

```bash
# in ~/.config/meetingbot/.env
MBOT_EXPORTERS=markdown,apple_notes,google_docs
```

| Target | Where it lives | Setup |
|---|---|---|
| `markdown` (always on) | local `.md` file in your notes dir | none — point `MBOT_NOTES_DIR` at an iCloud Drive / Google Drive folder to sync the files |
| `apple_notes` | Apple Notes app | none. Set `MBOT_APPLE_NOTES_FOLDER`; an **iCloud** folder syncs to cloud + iPhone/iPad, an **On My Mac** folder stays on-device |
| `google_docs` | a Google Doc in your Drive (cloud) | one-time `mbot auth-google` (see below) |

Re-send any past meeting to a target without re-recording:

```bash
mbot export --to apple_notes          # latest meeting → Apple Notes
mbot export <session> --to google_docs
```

### Google Docs one-time setup

1. In [Google Cloud Console](https://console.cloud.google.com): create a project,
   enable the **Google Docs API** and **Google Drive API**, and create an OAuth
   client of type **Desktop app**.
2. Download its JSON to `~/.config/meetingbot/google_client_secret.json`.
3. Run `mbot auth-google` once and approve in the browser. Done — `google_docs`
   exports now work and the token refreshes itself.

`mbot doctor` shows which targets are ready.

## Configuration

Environment variables (in `~/.config/meetingbot/.env` or a repo-local `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `NVIDIA_API_KEY` | — | free key from build.nvidia.com |
| `MBOT_NIM_MODEL` | `openai/gpt-oss-120b` | summary model (any NIM chat model, e.g. `meta/llama-3.3-70b-instruct`) |
| `MBOT_NIM_REASONING` | `low` | gpt-oss reasoning effort: `low`/`medium`/`high`/`none` (low ≈ 40% faster, equal quality for notes) |
| `MBOT_WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | local ASR model (≈1.6 GB, downloads on first use; use `mlx-community/whisper-small` on low disk/RAM) |
| `MBOT_VOCAB` | — | domain words to spell right (product names, jargon, people), e.g. `Postgres, Kubernetes, OAuth` |
| `MBOT_REFINE` | `local` | transcript cleanup tier: `off` (raw) / `local` (on-device, $0) / `cloud` (local + NIM polish, opt-in) |
| `MBOT_NOTES_DIR` | `./notes` | where Markdown notes go |
| `MBOT_DATA_DIR` | `~/.local/share/meetingbot` | sessions, search index, usage log |
| `MBOT_CHUNK_SECONDS` | `30` | audio chunk size for live transcription |
| `MBOT_EXPORTERS` | `markdown` | extra note destinations: `markdown,apple_notes,google_docs` |
| `MBOT_APPLE_NOTES_FOLDER` | `Meeting Bot` | Apple Notes folder (iCloud = cloud, On My Mac = device) |
| `MBOT_GOOGLE_DRIVE_FOLDER_ID` | — | optional Drive folder for Google Docs exports |

The summary prompt is `prompts/meeting_summary.md` — edit it to taste.

## How it works

1. `audiocap` (Swift) captures system audio via ScreenCaptureKit and the mic via
   AVAudioEngine, writing 16 kHz mono WAV chunks + a manifest.
2. `meetingbot` (Python) transcribes each chunk with mlx-whisper *while you're still
   in the meeting*, merging both streams by timestamp into Me/Them turns.
3. When you stop, the transcript is **refined** (Eloquent-style): an on-device pass
   strips fillers, stutters, and false starts and fixes punctuation — all locally and
   for free. The raw transcript is kept; with `MBOT_REFINE=cloud` a NIM pass polishes
   it further.
4. One request to NVIDIA NIM turns the cleaned transcript (plus your rough notes) into
   polished meeting notes. At 1–2 requests per meeting, the 1,000 free credits cover
   ~500+ meetings; NIM usage is logged to `~/.local/share/meetingbot/usage.log`. You
   can also reshape any meeting on demand with `mbot transform key_points|formal|short|long`.

See `PLAN.md` for the full build plan and roadmap (auto-detection of meetings,
calendar titles, ask-my-meetings Q&A…).

## Development

One command runs the full quality gate (Python lint+format+types+tests, Swift
build+format-lint, extension type-check against Chrome's official API types):

```bash
make check
```

| Layer | Tooling |
|---|---|
| Python (`meetingbot/`, `tests/`) | ruff (lint+format), mypy `--strict`, pytest (211 tests) |
| Swift (`audiocap/`) | swift-format (Apple style), no force-unwraps, modular sources |
| Extension (`chrome-extension/`) | `tsc --noEmit` with `checkJs` + JSDoc types + chrome-types |

`make models` benchmarks every supported Whisper variant on synthesized speech
(speed + keyword accuracy) so you can choose `MBOT_WHISPER_MODEL` for your machine.
Measured on this M-series Mac (warm, 13.7 s clip): tiny 222×, base 152×, small 67×,
medium 24×, large-v3-turbo 29× realtime — all with identical accuracy on clean
speech, so the default `large-v3-turbo` (best on real-world audio) costs nothing
in practice.

> ⚖️ Recording calls may require participant consent in your jurisdiction — announce
> it or get consent where required.
