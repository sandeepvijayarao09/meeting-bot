# MB for Android — planned (not yet implemented)

> **Status: design only.** There is no Android app in this repo yet. This file records
> the intended architecture so the Play Store milestone can be scoped and built. Do not
> treat anything here as shipping code.

## Why a from-scratch app

The macOS/iOS apps share a Swift package (`CaptureKit` + `MeetingBotKit`); **none of it
runs on Android**. Android is a separate, native build. The good news: Android is the
**best-supported platform for on-device Gemma**, so the AI step can be fully local.

## Intended architecture (mirrors the iOS app's flow)

```
Mic (AudioRecord, 16 kHz mono PCM) → chunked WAV + manifest
  → ASR: Android SpeechRecognizer (offline) or a Whisper build (whisper.cpp / LiteRT)
  → Refine: Kotlin port of refine.py Tier-1 (the same deterministic cleanup)
  → Summarize: Gemma 4 E4B via MediaPipe LLM Inference / LiteRT-LM (on-device),
               NVIDIA NIM as cloud fallback (transcript text only)
  → Note: Markdown saved to app storage; list/detail UI
Jetpack Compose UI: Record / Notes / Settings (parity with the iOS app).
```

- **Language/UI:** Kotlin + Jetpack Compose, min SDK 26+, target the current API level.
- **On-device LLM:** `com.google.mediapipe:tasks-genai` (or LiteRT-LM) loading the
  `gemma-4-E4B-it` `.task`/`.litertlm` model, downloaded on first launch (~3–4 GB; gated
  to high-RAM devices), NIM fallback otherwise — same hybrid policy as iOS.
- **Capture:** mic-only (Android can't capture other apps' audio without MediaProjection +
  user consent, same constraint class as iOS).

## Play Store requirements (when built)

- Signed **AAB** with Play App Signing; **Data Safety** form = no data collected/shared
  (audio/transcripts on-device); privacy-policy URL ([../PRIVACY.md](../PRIVACY.md));
  target-API-level compliance.

## Tooling note

An Android SDK is present on this machine (`~/Library/Android/sdk`) and `gradle` is
installed, but the build-out (Compose UI, LiteRT integration, model download, tests) is a
multi-week effort and should be its own milestone.
