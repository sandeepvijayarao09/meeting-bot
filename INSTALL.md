# Install & Use Meeting Bot

Local-first meeting notes: your audio is transcribed **on your Mac** with Whisper,
turned into notes, and (optionally) summarized. Nothing is uploaded except the
transcript *text* when you opt into cloud summaries with your own key.

- **Requirements:** a Mac with **Apple Silicon** (M-series) running **macOS 14 (Sonoma)
  or later**. ~1 GB free for the app + ~1.5 GB for the Whisper model (downloaded once
  on first use).
- **Optional (for AI summaries):** a free **NVIDIA NIM** API key — see
  [Set your API key](#3-set-your-api-key-optional-for-ai-summaries). Without a key you
  still get transcripts, on-device cleanup, and notes.

---

## 1. Install the macOS app

1. Download **`MB-1.0.1-<build>.dmg`** from the
   [latest release](https://github.com/sandeepvijayarao09/meeting-bot/releases/latest).
2. Open the DMG and **drag `MB.app` into Applications**.
3. **First launch (important).** This build is signed ad-hoc (not yet notarized by
   Apple), so Gatekeeper will block a normal double-click. Open it once the safe way:
   - **Right-click `MB.app` → Open → Open.** (You only do this once.)
   - If macOS still refuses, run:
     ```bash
     xattr -dr com.apple.quarantine /Applications/MB.app
     ```
   A 🎤 icon appears in the menu bar and the **Meetings** window opens.

> Why the extra step: a notarized build (no warning) needs an Apple Developer ID.
> See [DISTRIBUTION.md](DISTRIBUTION.md) to produce one with your own account.

## 2. Grant permissions (first recording)

On your first recording macOS asks for two permissions:

- **Microphone** — records your side ("Me").
- **Screen & System Audio Recording** — captures the meeting audio the *other*
  participants make ("Them"). This is audio-only; **no screenshots or video are ever
  captured** (the screen-capture API is used solely to tap system audio).

After you enable **Screen Recording**, macOS requires you to **quit and reopen MB.app**
for the grant to take effect. Do that once and you're set.

## 3. Set your API key (optional — for AI summaries)

Summaries use **your own** free NVIDIA NIM key (nothing is bundled, and your key never
leaves your machine except in requests to NVIDIA).

1. Get a free key at **https://build.nvidia.com**.
2. In MB: menu bar 🎤 → **Settings… → API key** → paste → save.
   (This writes `~/.config/meetingbot/.env`, shared with the CLI and the extension.)

No key? The app still records, transcribes, cleans up the transcript, and saves a
**transcript-only** note — it just skips the AI summary.

## 4. Record & take notes

1. Menu bar 🎤 → **Start Recording** (or open **Meetings…** to browse past notes).
2. Pick a **Template** (General / Standup / 1:1 / Interview / Sales call) and a
   **destination** (Apple Notes / Google Docs / Markdown files).
3. When the meeting ends → **Stop & Make Note**. The transcript is cleaned up, a note
   is written (and summarized if you set a key), and it opens automatically.

Everything is click-to-record — nothing runs in the background or auto-joins calls.

---

## 5. Connect the Chrome extension (browser-tab meetings)

The extension captures a **browser tab's** audio + your mic and streams it to a local
server on your Mac — useful for Google Meet / Zoom-web / any tab. Audio never leaves
your device.

**a. Start the local server.** The extension talks to `mbot serve` on
`ws://127.0.0.1:8765`. Start it using the copy bundled inside the app:

```bash
/Applications/MB.app/Contents/Resources/mbot serve
```

(Tip: alias it — `alias mbot="/Applications/MB.app/Contents/Resources/mbot"` — then
just `mbot serve`. The first run downloads the Whisper model.)

**b. Load the extension.** Until it's on the Chrome Web Store, install it unpacked:

1. Download **`meeting-bot-extension-1.0.0.zip`** from the
   [release](https://github.com/sandeepvijayarao09/meeting-bot/releases/latest) and unzip it.
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** →
   select the unzipped folder. Pin the extension.

**c. Record a tab.** Open the meeting tab → click the Meeting Bot extension → **Start**
→ grant tab capture. Audio streams to the running server; click **Stop** to finalize
the note. The extension is keyless — summaries use the server's key from step 3.

> The extension only works while `mbot serve` is running on the same Mac.

---

## 6. Command line (optional, power users)

The bundled `mbot` CLI drives the whole pipeline:

```bash
mbot set-key                 # store your NVIDIA NIM key
mbot record                  # record from the terminal
mbot process <session-dir>   # transcribe + summarize + export a finished session
mbot transcribe <dir>        # transcript only
mbot search "query"          # full-text search across your notes
mbot serve                   # localhost server for the Chrome extension
mbot doctor                  # environment / connectivity check
mbot --version               # version (quote it in bug reports)
```

`mbot --help` lists everything.

---

## Privacy in one line

Audio is captured and transcribed **entirely on your device**. The only thing that can
leave your Mac is the transcript *text*, and only when you've set a key and a summary
runs (sent to NVIDIA, not retained by this app). See [PRIVACY.md](PRIVACY.md). A fully
offline, on-device summary path (Gemma via LiteRT-LM) is opt-in and on the roadmap —
see [docs/on-device-llm.md](docs/on-device-llm.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "MB.app can't be opened / unidentified developer" | Right-click → Open → Open, or `xattr -dr com.apple.quarantine /Applications/MB.app` (see step 1). |
| First recording captures no "Them" audio | Enable **Screen & System Audio Recording** in System Settings → Privacy & Security, then **quit and reopen** MB.app. |
| Notes save but there's no summary | You haven't set an API key (step 3), or the request failed — the transcript-only note is expected. |
| Extension won't connect | Make sure `mbot serve` is running (`ws://127.0.0.1:8765`) on the same Mac. |
| Permissions stuck after re-install | `tccutil reset Microphone` and `tccutil reset ScreenCapture`, then re-grant. |
