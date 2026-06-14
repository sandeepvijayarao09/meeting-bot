# Roadmap

Where Meeting Bot is, and what would bring it to parity with commercial AI notetakers
(Granola, Otter, Fathom, Fireflies, tl;dv). Everything stays local-first.

## Shipped (v0.1)

- ✅ Any-app capture (mic + system audio), no bot joins the call
- ✅ Local Whisper transcription with Me/Them attribution
- ✅ AI summaries (decisions, action items) via free NVIDIA NIM
- ✅ Exports: Markdown, Apple Notes (iCloud/device), Google Docs (cloud)
- ✅ Full-text search across meetings
- ✅ Native macOS menu bar app + Chrome extension
- ✅ Packaging: `.app`, DMG, sign/notarize scripts

## Gap to commercial notetakers (planned)

| Feature | Status | Notes |
|---|---|---|
| **Speaker diarization** (Speaker A/B/C among "Them") | planned | `pyannote.audio`, local, opt-in (`MBOT_DIARIZE`). Adds per-speaker labels the single stream can't give today. |
| **In-app notes browser** (list, read, search, edit in the app) | planned | SwiftUI window so it feels like a product, not "opens a .md file". |
| **Live transcript view** during the meeting | planned | Stream segments into the app/extension UI in real time. |
| **Calendar integration** | planned | EventKit: auto-name notes from the current event, list upcoming meetings. |
| **Auto-detect meetings** | planned | Prompt to record when Zoom/Meet/Teams starts (process / mic-in-use detection). |
| **Ask my meetings** (chat over transcripts) | planned | FTS retrieval + NIM answer: "what did we decide about pricing?" |
| **Meeting templates** | planned | Different summary prompts for standups, 1:1s, interviews. |
| **Editable / shareable notes** | planned | Edit summaries; share links. |

## Good first issues

- Add a meeting-type template selector to the summary prompt.
- Add `mbot export --to clipboard`.
- Surface NIM credit usage in `mbot doctor`.

Have a request? Open an issue.
