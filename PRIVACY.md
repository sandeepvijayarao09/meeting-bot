# Privacy Policy — MB (Meeting Bot)

_Last updated: 2026-06-23_

MB is a **local-first** meeting notetaker. Our design principle is simple: your
recordings and transcripts stay on your device. This policy explains exactly what
happens to your data.

## What MB does on your device

- **Audio** captured during a recording is written to your device's local storage and
  transcribed **on your device** (Apple Speech / Whisper on iOS, Whisper on macOS).
  Audio is never uploaded to us or anyone else.
- **Transcripts and notes** are stored as files in your app's local folder (and, on
  macOS, a local search index). They are not sent to us.
- MB contains **no analytics, no tracking, no advertising, and no third-party SDKs**
  that collect data. We (the developers) receive **no data** from your use of the app.
- **On first use**, MB downloads the local Whisper speech-to-text model (about 1.5 GB)
  from its public model host. This is a one-time software download and sends **none of
  your audio, transcripts, or personal data**.

## Optional features that send data off your device (you control these)

These are **off by default** and only operate when you explicitly enable them:

- **Cloud summary (NVIDIA NIM).** If you add your own API key, MB sends the meeting's
  **transcript text** (never audio) to NVIDIA's NIM service to generate the summary.
  That request is governed by NVIDIA's privacy policy. On-device summarization (Gemma)
  keeps even this step local.
- **Exports (macOS).** If you enable Apple Notes or Google Docs export, the finished
  note is sent to that destination. Apple Notes may sync via your iCloud account;
  Google Docs uploads to your Google Drive under your own Google account.

## Permissions MB requests, and why

- **Microphone** — to record meeting audio for transcription.
- **Speech Recognition** (iOS) — to transcribe recorded audio on-device.
- **Screen & System Audio Recording** (macOS) — to capture the meeting audio playing
  on your Mac (this is how macOS exposes other apps' audio; it is not a screen capture).
- **Calendar** (optional) — read-only, only to title a note from the current event.

## Data retention and deletion

All MB data lives in your app's storage. To delete it, delete the notes/recordings in
the app (or delete the app). We hold nothing to delete on our side.

## Children

MB is not directed at children and collects no personal data.

## Contact

Questions: vijayarao.s@northeastern.edu ·
Source: https://github.com/sandeepvijayarao09/meeting-bot
