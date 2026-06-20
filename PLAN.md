# Meeting Bot — Build Plan

> **Status (2026-06-11):** Phases 0–4 are built and verified (see README.md for usage).
> Also built: a Chrome extension (`chrome-extension/`) that captures the meeting tab's
> audio + mic and streams to a localhost WebSocket server (`mbot serve`), reusing the
> same session format and pipeline — verified with a simulated client.
> Remaining: add `NVIDIA_API_KEY` to `~/.config/meetingbot/.env`, approve macOS
> permissions on first `mbot record`, load the extension unpacked in Chrome, then
> Phase 5 nice-to-haves as desired.
>
> **Hardened (2026-06-12):** `make check` quality gate — ruff + mypy --strict +
> 63 pytest tests, swift-format-clean modular Swift (no force-unwraps),
> extension type-checked via tsc/checkJs/chrome-types. All Whisper variants
> benchmarked (`make models`); live capture verified on real hardware
> (ScreenCaptureKit → Whisper round-trip of spoken audio).

A Granola-style meeting notetaker that runs entirely on this laptop. No bot joins your
calls — it listens to the meeting audio already playing on your Mac, transcribes it
locally, and uses a free cloud LLM (NVIDIA NIM) only for the final summarization step.

## Goals

- Works with any meeting app (Zoom, Google Meet, Teams, Slack huddles, FaceTime) because
  it captures audio at the OS level, not via meeting-platform APIs.
- $0 running cost: transcription is local (Whisper), summarization uses NVIDIA NIM's
  free tier (1,000 credits on signup, ~40 requests/min, OpenAI-compatible API).
- Privacy-first: raw audio and transcripts never leave the laptop; only the finished
  transcript text is sent to NIM for summarization (and even that can be swapped for a
  local LLM later).
- Output: one Markdown note per meeting (summary, decisions, action items, full
  transcript), saved to a folder you own, searchable from a CLI / menu bar app.

## Architecture

```
Mic (you) ────────────────┐
                          ├── audiocap (Swift helper, ScreenCaptureKit + AVAudioEngine)
System audio (everyone    │     → two 16 kHz mono WAV streams, chunked
else, via Zoom/Meet/…) ───┘
        │
        ▼
Transcriber (Python, local Whisper — mlx-whisper on Apple Silicon)
  - transcribes each stream separately
  - merges by timestamp → "Me:" / "Them:" labeled transcript   ← Granola's core trick
        │
        ▼
Summarizer (NVIDIA NIM, openai/gpt-oss-120b via OpenAI SDK, base_url=integrate.api.nvidia.com/v1)
  - TL;DR, key decisions, action items with owners, open questions
  - optionally merges with rough notes you typed during the meeting
        │
        ▼
notes/2026-06-11-standup.md  +  SQLite full-text index
        ▲
Menu bar app (rumps): Start/Stop, status, open last note  +  CLI: list/search/ask
```

Why two audio streams instead of speaker diarization: your mic is always "you" and
system audio is always "everyone else", which gives useful speaker attribution for free.
Real per-person diarization (pyannote) is a later optional upgrade.

Why ScreenCaptureKit instead of BlackHole: no third-party audio driver to install, no
Audio MIDI Setup fiddling, works fine with headphones. It needs Screen Recording
permission once, and it's Apple's supported path for this on modern macOS.

## Repo layout

```
Meeting Bot/
├── PLAN.md
├── audiocap/                # Swift package — capture helper CLI
│   └── Sources/audiocap/    #   writes mic.wav + system.wav in rolling chunks
├── meetingbot/              # Python package
│   ├── capture.py           # spawns/stops the audiocap binary
│   ├── transcribe.py        # local Whisper, per-channel, timestamp merge
│   ├── summarize.py         # NIM client + prompt assembly
│   ├── notes.py             # Markdown writer + SQLite FTS index
│   ├── detect.py            # (phase 5) auto-detect Zoom/Meet/Teams
│   ├── cli.py               # `mbot record|stop|list|search|ask`
│   └── app.py               # menu bar UI (rumps)
├── prompts/
│   └── meeting_summary.md   # editable summary prompt template
├── notes/                   # generated notes (output)
└── pyproject.toml           # managed with uv
```

## Phases

Each phase ends with something runnable. Don't start a phase until the previous one's
acceptance test passes.

### Phase 0 — Setup (~30 min)

1. Get the free NIM key: sign up at https://build.nvidia.com (email only, no card),
   create an API key (`nvapi-...`). Store it in `~/.config/meetingbot/.env` as
   `NVIDIA_API_KEY=...` — never in the repo.
2. Install tools: Xcode Command Line Tools (`xcode-select --install`), `uv` for Python.
3. `uv init`, add deps: `mlx-whisper` (Apple Silicon) or `faster-whisper` (Intel
   fallback), `openai`, `typer`, `rumps`, `python-dotenv`.
4. Smoke-test NIM with a 5-line script:

   ```python
   from openai import OpenAI
   client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=KEY)
   r = client.chat.completions.create(
       model="openai/gpt-oss-120b",
       messages=[{"role": "user", "content": "say hi"}])
   ```

**Accept:** NIM responds; `uv run python -c "import mlx_whisper"` works.

### Phase 1 — Audio capture (the hard part, do it first)

Build `audiocap`, a small Swift CLI:

- System audio via ScreenCaptureKit audio-only capture (`SCStreamConfiguration` with
  `capturesAudio = true`, video minimized/ignored).
- Mic via `AVAudioEngine` input node.
- Both resampled to 16 kHz mono PCM, written as WAV chunks (e.g. 30 s each) into a
  session directory: `session/mic-0001.wav`, `session/sys-0001.wav`, plus a manifest
  with chunk start timestamps.
- Runs until SIGINT; flushes the final partial chunk on exit.
- First run triggers macOS prompts for Microphone + Screen Recording — approve once.

Notes:
- ScreenCaptureKit records *all* system audio (notification dings included). Acceptable
  for v1; later we can use `SCContentFilter` to capture only the meeting app's audio.
- 16 kHz mono is what Whisper wants; keeps files tiny (~2 MB/min for both streams).

**Accept:** play a YouTube video while talking; stop; get two WAV sets where sys-*.wav
contains the video audio and mic-*.wav contains your voice, timestamps aligned.

### Phase 2 — Local transcription

`transcribe.py`:

- Watch the session directory; as each chunk closes, transcribe it with
  `mlx-whisper` using `whisper-large-v3-turbo` (fast on Apple Silicon; drop to
  `small`/`medium` if the machine struggles). Runs during the meeting, so the
  transcript is ready seconds after it ends.
- Skip silent chunks (cheap RMS check) — most of the mic track is silence.
- Merge the two channels' segments by timestamp into one JSONL transcript:
  `{"t": 123.4, "speaker": "me"|"them", "text": "..."}`.

**Accept:** record a 5-minute test call (or YouTube + your own commentary); merged
transcript reads in correct order with correct me/them labels.

### Phase 3 — Summarization via NIM

`summarize.py` + `prompts/meeting_summary.md`:

- One chat-completions call per meeting (chunk + reduce only if transcript exceeds the
  context window — rarely needed; gpt-oss-120b takes 128k tokens).
- Prompt produces: title, TL;DR (3 bullets), key discussion points, decisions, action
  items as `- [ ] task — owner — due`, open questions.
- Granola-style enhancement: if you jotted rough notes during the meeting (a plain
  `notes.txt` in the session dir for now), the prompt expands/corrects them against the
  transcript instead of summarizing from scratch.
- Budget guard: log credits used; at ~1–2 requests per meeting, 1,000 credits ≈
  500+ meetings. If credits ever run out, switch `base_url` to a local Ollama model —
  one line.

**Accept:** end-to-end: record → transcribe → `notes/<date>-<title>.md` appears with a
good summary and the full transcript appended.

### Phase 4 — Make it a daily tool

- `cli.py` (typer): `mbot record` / `mbot stop` / `mbot list` / `mbot search <query>`.
- `notes.py`: SQLite FTS5 index over titles + transcripts for instant search.
- `app.py` (rumps menu bar): 🎙 icon — Start/Stop recording, elapsed time, "Open last
  note", "Open notes folder". Launch at login via a LaunchAgent plist.

**Accept:** run a real meeting end-to-end using only the menu bar; find it later with
`mbot search`.

### Phase 5 — Nice-to-haves (pick as desired)

- **Auto-detect meetings:** poll for Zoom/Teams/Meet (browser tab detection is harder;
  process + mic-in-use check covers most) → menu bar asks "Meeting detected — record?"
- **Calendar titles:** read the current event via AppleScript/EventKit so notes are
  named "Design review" instead of a timestamp.
- **Live transcript window** while the meeting runs.
- **Ask-my-meetings:** `mbot ask "what did we decide about pricing?"` — FTS retrieves
  relevant transcripts, NIM answers.
- **Real diarization:** pyannote-audio on the system track to split "them" into
  Speaker A/B/C.
- **Meeting-type templates:** different prompts for standups, 1:1s, interviews.

## Cost summary

| Component        | What                                   | Cost |
|------------------|----------------------------------------|------|
| Audio capture    | ScreenCaptureKit (built into macOS)    | $0   |
| Transcription    | Whisper, runs locally                  | $0   |
| Summarization    | NVIDIA NIM free tier (1,000 credits)   | $0   |
| Storage/search   | Markdown files + SQLite                | $0   |

## Risks & mitigations

- **macOS permissions:** Screen Recording + Microphone prompts must be approved for the
  audiocap binary (and re-approved if the binary is rebuilt/moved — keep it at a stable
  path).
- **NIM credits exhausted / model deprecated:** OpenAI-compatible client means swapping
  to another NIM model or a local Ollama model is a one-line change.
- **Whisper too slow on long meetings:** use `large-v3-turbo` or `distil`/`small`
  models; transcription happens during the meeting so it never blocks at the end.
- **Consent:** recording calls may require participant consent depending on
  jurisdiction — same caveat as Granola; announce or get consent where required.
