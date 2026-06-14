# Meeting Bot — Privacy Policy

_Last updated: June 12, 2026_

Meeting Bot is a local-first meeting notetaker. The extension records the audio of the
tab you choose plus your microphone, **only while you have explicitly started a
recording**, and streams it to the Meeting Bot application running on **your own
computer** (`127.0.0.1`). Nothing is sent to the extension developer or any third-party
server by the extension.

## What the extension accesses

- **Tab audio (`tabCapture`)** — captured only for the tab you press "Start recording"
  on, only after you press it, and only until you press stop or close the tab.
- **Microphone** — captured during a recording so your side of the meeting can be
  transcribed. You grant this permission explicitly and can revoke it at any time in
  Chrome's site settings.
- **Active tab title (`activeTab`)** — used once, as the default title of your note.

## Where your data goes

- Audio is streamed to `ws://127.0.0.1:8765` — a server on your own machine. It is
  transcribed locally (Whisper running on your device) and stored as files in folders
  you control.
- The extension itself performs **no** remote network requests, hosts **no** analytics,
  and stores **no** data beyond the in-memory state of an active recording.
- If you configure an NVIDIA API key in the companion Mac app, the finished transcript
  **text** (never audio) is sent to NVIDIA's API to generate a summary. This happens in
  the Mac app, is entirely optional, and is under your control. See NVIDIA's privacy
  policy for how they handle API requests.

## Data retention and deletion

All recordings, transcripts, and notes live on your computer. Delete them at any time
by deleting the files (`~/.local/share/meetingbot` and your notes folder).

## Consent

You are responsible for complying with the laws of your jurisdiction regarding
recording conversations, including obtaining participant consent where required.

## Contact

Questions: vijayarao.s@northeastern.edu
