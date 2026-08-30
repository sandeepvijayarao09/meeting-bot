# Chrome Web Store listing — copy & submission guide

## Basic info

- **Name:** Meeting Bot — Local Meeting Notes
- **Summary (132 chars max):**
  Record this tab's meeting and your mic into private meeting notes on your own Mac. Audio never leaves your device.
- **Category:** Productivity → Tools
- **Language:** English

## Detailed description

```
Meeting Bot turns your browser meetings (Google Meet, Zoom web, Teams web — any tab)
into polished meeting notes, without sending your audio to anyone's cloud.

HOW IT WORKS
• Click the mic icon on your meeting tab and press "Start recording this tab".
• The extension captures the tab's audio (everyone else) and your microphone (you),
  and streams both to the Meeting Bot app running on YOUR OWN Mac.
• Your Mac transcribes the meeting locally with Whisper while it happens.
• When you stop, you get a Markdown note: summary, key points, decisions, action
  items, and the full transcript labeled Me/Them — searchable across all meetings.

PRIVACY FIRST
• Raw audio never leaves your computer. The extension only talks to 127.0.0.1.
• No accounts, no analytics, no tracking, no third-party servers.
• Optional: summaries use NVIDIA's free API — transcript text only, only if you
  configure a key, and only from your own machine.

REQUIREMENTS
• The free Meeting Bot companion app running on macOS (Apple Silicon).
  Setup instructions: see the project README.
• Recording only starts when you press the button, and a red REC badge is shown
  the whole time. Please follow your local laws on recording consent.
```

## Single purpose statement (review questionnaire)

> Records the current tab's meeting audio together with the user's microphone, at the
> user's explicit request, and delivers it to the user's own local note-taking
> application for transcription into meeting notes.

## Permission justifications (review questionnaire)

- **tabCapture** — Captures the audio of the meeting tab the user explicitly chose to
  record; this is the core function of the extension.
- **activeTab** — Identifies the tab to record and reads its title as the default
  meeting-note title, only after the user invokes the extension.
- **offscreen** — Hosts the audio pipeline and the localhost connection for the
  duration of a recording, so capture survives the popup closing (offscreen documents
  are the required MV3 mechanism for getUserMedia).
- **Remote code:** none. **Host permissions:** none.

## Data-use disclosures (Privacy tab of the dashboard)

- Collects: **Audio** (tab + microphone, user-initiated) — processed locally on the
  user's device; not transmitted to the developer; not sold; not used for unrelated
  purposes; not transferred for creditworthiness/lending.
- Privacy policy URL — the repo is public, so this is already live; paste it as-is:
  <https://github.com/sandeepvijayarao09/meeting-bot/blob/main/chrome-extension/PRIVACY.md>

## Assets (in this folder)

- `screenshot-1.png` — 1280×800 store screenshot (required; you can add real captures later)
- `promo-tile-440x280.png` — small promo tile (optional)
- Store icon: the dashboard takes `icons/icon128.png` from the uploaded zip automatically.

## Submission steps

1. Pay the one-time $5 developer fee at https://chrome.google.com/webstore/devconsole
   (sign in with the Google account you want to own the extension).
2. "New item" → upload `dist/meeting-bot-extension-1.0.0.zip`.
3. Paste the copy above into the listing; upload `screenshot-1.png`.
4. Fill the Privacy tab using the disclosures above + the privacy policy URL above.
5. Set visibility (consider **Unlisted** — installable via link, no public listing —
   since the extension requires the companion Mac app).
6. Submit for review. Audio-capture extensions get human review; expect a few days.
