# MB for iOS

A local-first, **microphone-based** meeting notetaker — the iOS sibling of the macOS
app. It records the mic (in-person meetings, speakerphone calls), transcribes
**on-device**, refines locally (Eloquent-style cleanup), and summarizes via the
NVIDIA NIM cloud fallback (Milestone 1) or **on-device Gemma 4 E4B** (Milestone 2).

> iOS cannot capture other apps' audio (no ScreenCaptureKit), so for virtual calls
> (Zoom/Meet/Teams) use the macOS app or the Chrome extension. iOS shines for
> in-person and speakerphone meetings.

## Architecture

The app links two products from the shared SwiftPM package in `../mac`:

- **CaptureKit** — mic capture → 16 kHz WAV chunks + manifest (system-audio capture
  is `#if os(macOS)`-guarded out).
- **MeetingBotKit** — `Refiner` (Swift port of the Python Tier-1 cleanup), `Transcript`
  merge/format, `MeetingPipeline` (transcribe → refine → summarize → note), and the
  `ASRProvider` / `LLMProvider` protocols + `NIMProvider`.

App-side adapters: `AppleSpeechASR` (on-device `SFSpeechRecognizer`), `RecordingController`,
and SwiftUI (`ContentView` tabs: Record / Notes / Settings).

## Build & run

Requires Xcode 16+ and [XcodeGen](https://github.com/yonaskolb/XcodeGen)
(`brew install xcodegen`).

```bash
cd ios/MB
xcodegen generate          # writes MB.xcodeproj from project.yml
open MB.xcodeproj          # then Run on a simulator or device
```

Or from the command line (simulator, no signing needed):

```bash
xcodebuild -project MB.xcodeproj -scheme MB \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' build
```

On a real device, set your Team in Signing & Capabilities first.

## Milestones

- **M1 (this):** mic capture + on-device Apple Speech transcription + local refine +
  notes; cloud summary via a NIM key in Settings (optional).
- **M2:** on-device **Gemma 4 E4B** via LiteRT-LM (summaries fully offline), a
  first-launch model download + device-capability gate, and optionally WhisperKit for
  higher-accuracy transcription. The pipeline already abstracts both behind
  `LLMProvider` / `ASRProvider`, so M2 is additive.
