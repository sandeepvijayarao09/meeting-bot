# Roadmap

Where Meeting Bot stands vs. commercial AI notetakers (Granola, Otter, Fathom,
Fireflies, tl;dv) and what's next. Everything stays local-first.

## Shipped

- ✅ Any-app capture (mic + system audio), no bot joins the call
- ✅ Local Whisper transcription with Me/Them attribution
- ✅ Speaker diarization (Speaker A/B/C among "Them"), opt-in `MBOT_DIARIZE`
- ✅ AI summaries (decisions, action items) via free NVIDIA NIM
- ✅ **Meeting templates / "Recipes"** — general, standup, 1:1, interview, sales call
- ✅ **Talk-time analytics** — Me/Them ratio, words, turns, longest monologue
- ✅ Ask-my-meetings (retrieval + AI answer with sources)
- ✅ Exports: Markdown, Apple Notes (iCloud/device), Google Docs (cloud)
- ✅ Full-text search across meetings
- ✅ Calendar titles (read only on Start)
- ✅ Native macOS app (Meetings window + Settings/Access) + Chrome extension
- ✅ Packaging: `.app`, DMG, sign/notarize scripts
- ✅ Click-to-record only — no auto-detect, no background daemons

## Next (to match / beat the field)

| Feature | Who has it | Notes |
|---|---|---|
| **MCP server** (feed meetings to Claude/ChatGPT) | Granola (2026) | Expose search/ask/get-note as MCP tools — on-brand and unique among local tools. |
| **Live transcript view** during the call | Otter, Granola | Stream segments into the app UI in real time (already transcribed live; needs the view). |
| **In-meeting notepad** (type sparse notes → AI expands) | Granola (signature) | UI for the existing `notes.txt` merge. |
| **In-app chat panel** over a meeting / all meetings | Fireflies AskFred | `mbot ask` exists as CLI; add a chat UI. |
| **Semantic search** (embeddings) | most | Beat keyword FTS with a local embedding model. |
| **Editable / shareable notes** | most | Edit summaries in the app; share links. |
| **Integrations** (Slack / Notion / CRM) | Fireflies (widest) | Outbound webhooks; opt-in, keeps audio local. |
| **Notarized distribution + auto-update** | all | Developer-ID notarize (scripts ready) + Sparkle. |

## Where we already win

Privacy (audio never leaves the device — none of the others), $0 cost, MIT-open,
and any-app capture with no bot joining the call.

Have a request? Open an issue.
