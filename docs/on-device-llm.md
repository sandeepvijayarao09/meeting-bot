# On-device LLM (Gemma 4 E4B via LiteRT-LM)

Status: **scaffolded, opt-in, off by default. On-device inference is a device-side
finish** (see "Remaining work"). Today's default summary backend is unchanged
(NVIDIA NIM cloud); nothing here alters shipped behavior until it's explicitly enabled
and the model is installed.

## Goal

Run the meeting **summary** (and the optional refinement polish) with an on-device
Gemma model — the same stack Google AI Edge **Eloquent** uses: **Gemma 4 E4B** via
**LiteRT-LM**. When selected, transcript text never leaves the device (no network),
so the whole product can be fully local.

## Backends

Selected by `MBOT_LLM` (env) or the `llmBackend` default:

| Value | Behavior |
|---|---|
| `cloud` (default) | NVIDIA NIM summary — today's behavior, unchanged. |
| `local` / `gemma` | On-device Gemma 4 E4B (LiteRT-LM). Fully local, no network. |
| `none` | No summary — deterministic transcript + local cleanup only. |

The default ships **no model** (nothing to download, no size cost) and does not select
the local backend, so this is purely additive until you turn it on.

## Architecture (already in place)

- `LLMProvider` (`mac/Sources/MeetingBotKit/Providers.swift`) is the one seam every
  summary/refine/title call goes through.
- `GemmaProvider` (`mac/Sources/MeetingBotKit/GemmaProvider.swift`) is the fully-local
  backend. It's a **scaffold**: the model descriptor (`GemmaModel`), the
  model-installed check, and the fallback contract are done and unit-tested; the
  concrete LiteRT-LM inference is stubbed. Until it's wired, `complete` throws
  `LLMError.modelUnavailable`.
- `MeetingPipeline` runs the summary **best-effort**: if the backend throws (no model
  yet, no cloud key, or a network error), the meeting is still saved as a
  transcript-only note. So enabling `local` before the model is installed degrades
  safely rather than losing a meeting. This is covered by
  `testLocalGemmaBackendDegradesToTranscriptOnly`.
- `RecordingController.processNatively` picks the provider from `Paths.llmBackend`
  (the in-process native pipeline, `MBOT_NATIVE_PIPELINE=1`).

## Model

- **Gemma 4 E4B**, 4-bit — the ~4 B-effective edge variant, LiteRT-LM `.litertlm`
  bundle. ~4 GB on disk (`GemmaModel.approxBytes`).
- Downloaded once to Application Support (`GemmaModel.url(appSupport:)`), like the
  Whisper model cache — **not** bundled in the app.
- Note on size: this is the largest single asset in the product; keep it opt-in and
  behind an explicit, size-warned download.

## Remaining work (device-side finish)

1. Add the **LiteRT-LM Swift package** to the *app* target (macOS + iOS) — not the
   dependency-free `MeetingBotKit` package.
2. Implement a model manager that downloads + verifies `GemmaModel.bundleName` into
   `GemmaModel.url(appSupport:)`, with a size-warned prompt and progress UI.
3. Replace the `throw` in `GemmaProvider.complete` with a LiteRT-LM session that runs
   `system` + `user` and returns the text, honoring `maxTokens`.
4. Verify on a real device (macOS + iOS): quality vs. the cloud summary, latency, RAM,
   thermals. Tune the prompts (`Prompts` in `MeetingPipeline.swift`) for the smaller model.
5. Once validated, consider flipping the default to `local` and removing the NIM cloud
   backend — the "fully local, no cloud" end state.

## Why the inference isn't implemented here

LiteRT-LM is a native, device-only runtime and the model is a ~4 GB download; neither
can be built, run, or verified in CI / a headless environment. Shipping a stubbed
provider that fails safe (transcript-only) is deliberate — it keeps `make check` green
and the product working, and leaves a clean, tested seam for the on-device finish.
