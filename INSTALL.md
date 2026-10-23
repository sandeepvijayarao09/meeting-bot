# Install & Use Meeting Bot

Local-first meeting notes: your audio is transcribed **on your Mac** with Whisper,
turned into notes, and (optionally) summarized. Nothing is uploaded except the
transcript *text* when you opt into cloud summaries with your own key.

- **Requirements:** a Mac with **Apple Silicon** (M-series) running **macOS 14 (Sonoma)
  or later**. ~165 MB download (~406 MB installed) + ~1.5 GB for the speech model,
  which you download separately with one click (see
  [Download the speech model](#2-download-the-speech-model)).
- **For AI summaries:** a second on-device model (~5 GB), downloaded with one click — see
  [Download the summary model](#4-download-the-summary-model). Skip it and you still
  get transcripts, on-device cleanup, and notes. No API key is needed either way.

---

## 1. Install the macOS app

1. Download **`MB-1.0.1-<build>.dmg`** from the
   [latest release](https://github.com/sandeepvijayarao09/meeting-bot/releases/latest).
2. Open the DMG and **drag `MB.app` into Applications**.
3. **First launch (important).** Releases up to and including **1.0.1** are ad-hoc signed
   — not yet notarized by Apple — so macOS blocks the first launch with *"MB" Not Opened
   — Apple could not verify "MB" is free of malware*. **Click `Done`, not `Move to
   Trash`** (Trash is the highlighted button). Then, on **macOS 15 Sequoia or later**:

   1. **Apple menu** ▸ **System Settings** ▸ **Privacy & Security**.
   2. Scroll to **Security**. You'll see *"MB" was blocked to protect your Mac*.
   3. Click **Open Anyway**, authenticate, and confirm **Open Anyway** once more.

   That button only appears for about an hour after a blocked launch, so if it's gone,
   double-click the app again first. On **macOS 14 Sonoma** you can instead right-click
   `MB.app` → **Open** → **Open** — Apple removed that shortcut in macOS 15.

   Either way it's once per install. A 🎤 icon appears in the menu bar and the
   **Meetings** window opens.

   <details><summary>Terminal alternative (any version)</summary>

   ```bash
   xattr -dr com.apple.quarantine /Applications/MB.app
   ```
   This strips the download-quarantine flag, so Gatekeeper stops gating the app.
   </details>

> Why any of this: Gatekeeper only lets unsigned apps through by explicit user consent.
> A **notarized** build opens with no warning at all — that needs an Apple Developer ID
> ($99/yr). See [RELEASE.md](RELEASE.md#ship-a-notarized-download) to produce one.

## 2. Download the speech model

Transcription runs on your Mac, which means the speech model has to live on your Mac
— about 1.5 GB of it. It ships **separately from the app** so the download above stays
small, and so you are not paying for it before you have decided to keep the app.

In MB: menu bar 🎤 → **Settings…** → **Speech model** → **Download**. It runs once,
takes a few minutes on a normal connection, and you can close the window while it works.
The download resumes if it is interrupted.

From the terminal instead:

```bash
mbot download-model
```

Do this **before your first meeting**. If you skip it, the model is fetched the moment
you stop your first recording — which works, but turns a 10-second wait into a multi-minute
one at exactly the wrong time. `mbot doctor` tells you which state you are in.

## 3. Grant permissions (first recording)

On your first recording macOS asks for two permissions:

- **Microphone** — records your side ("Me").
- **Screen & System Audio Recording** — captures the meeting audio the *other*
  participants make ("Them"). This is audio-only; **no screenshots or video are ever
  captured** (the screen-capture API is used solely to tap system audio).

After you enable **Screen Recording**, macOS requires you to **quit and reopen MB.app**
for the grant to take effect. Do that once and you're set.

## 4. Download the summary model

Summaries are written by **Gemma 4 running on your Mac** — no account, no key, and
the transcript never leaves the device.

In MB: menu bar 🎤 → **Settings… → Summaries & Ask → Download**. One-time ~5 GB, on
top of the speech model. From the terminal instead:

```bash
mbot download-model --llm
```

Skip it and the app still records, transcribes, cleans up the transcript, and saves a
**transcript-only** note — it just leaves the summary blank until you run
`mbot summarize` later.

<details><summary>Prefer a cloud model?</summary>

On-device summaries are slower than a hosted model, and Gemma 4 E4B is a ~4B-class
model rather than a frontier one. If you would rather trade privacy for quality, set
`MBOT_LLM_BACKEND=cloud` with your own key and any OpenAI-compatible endpoint
(Settings ▸ Summaries & Ask ▸ *Use a cloud model instead*). Transcript **text** then
leaves your Mac for that provider; audio never does either way.
</details>

## 5. Record & take notes

1. Menu bar 🎤 → **Start Recording** (or open **Meetings…** to browse past notes).
2. Pick a **Template** (General / Standup / 1:1 / Interview / Sales call) and a
   **destination** (Apple Notes / Google Docs / Markdown files).
3. When the meeting ends → **Stop & Make Note**. The transcript is cleaned up, a note
   is written (and summarized if you set a key), and it opens automatically.

Everything is click-to-record — nothing runs in the background or auto-joins calls.

---

## 6. Connect the Chrome extension (browser-tab meetings)

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

## 7. Command line (optional, power users)

The bundled `mbot` CLI drives the whole pipeline:

```bash
mbot download-model --llm    # on-device summary model (~5 GB)
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
runs on your Mac by default. See [PRIVACY.md](PRIVACY.md). A fully
offline, on-device summary path (Gemma via LiteRT-LM) is opt-in and on the roadmap —
see [docs/on-device-llm.md](docs/on-device-llm.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "MB Not Opened" / "Apple could not verify MB" | Click **Done**, then System Settings ▸ Privacy & Security ▸ **Open Anyway** (macOS 15+). Full steps in [step 1](#1-install-the-macos-app). |
| First recording captures no "Them" audio | Enable **Screen & System Audio Recording** in System Settings → Privacy & Security, then **quit and reopen** MB.app. |
| Notes save but there's no summary | You haven't set an API key (step 3), or the request failed — the transcript-only note is expected. |
| Extension won't connect | Make sure `mbot serve` is running (`ws://127.0.0.1:8765`) on the same Mac. |
| Permissions stuck after re-install | `tccutil reset Microphone` and `tccutil reset ScreenCapture`, then re-grant. |
