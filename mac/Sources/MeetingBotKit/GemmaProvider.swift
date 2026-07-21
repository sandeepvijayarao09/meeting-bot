import Foundation

/// Which backend produces the summary (and the cloud-tier refinement polish).
///
/// Mirrors the `MBOT_LLM` setting. `.cloud` is today's default (NVIDIA NIM); the
/// roadmap target is fully-local `.localGemma` (on-device, no network) once the
/// LiteRT-LM engine is wired and verified on a real device — at which point the
/// cloud backend can be removed. `.none` keeps a deterministic, model-free,
/// network-free product (transcript + local cleanup, no AI summary).
public enum LLMBackend: String, Sendable {
  case none
  case cloud
  case localGemma
}

/// The on-device model this app targets, mirroring Google AI Edge Eloquent's
/// stack: **Gemma 4 E4B** run through **LiteRT-LM**. Downloaded once to the app's
/// Application Support directory (not bundled — the default ships no model).
public enum GemmaModel {
  /// Identifier for the cache directory / download.
  public static let identifier = "gemma-4-e4b"
  /// LiteRT-LM bundle filename expected on device (a `.litertlm` / `.task` model).
  public static let bundleName = "gemma-4-e4b.litertlm"
  /// Approximate on-disk size, documented so the UI can warn before downloading.
  public static let approxBytes: Int64 = 4_000_000_000  // ~4 GB (E4B, 4-bit)

  /// Where the model lives once downloaded, under an Application Support root.
  public static func url(appSupport: URL) -> URL {
    appSupport
      .appendingPathComponent("meetingbot/models", isDirectory: true)
      .appendingPathComponent(bundleName)
  }
}

/// Fully-local, on-device Gemma summarizer/refiner — the network-free backend,
/// mirroring Google AI Edge Eloquent (Gemma 4 E4B via LiteRT-LM). When selected,
/// transcript text never leaves the device.
///
/// **Scaffold.** The seam, model descriptor, availability check, and fallback
/// contract are complete and unit-tested; the concrete LiteRT-LM inference is a
/// device-side finish. It needs the LiteRT-LM Swift framework (an SPM/binary
/// dependency this deliberately dependency-free package does not pull in) plus the
/// ~4 GB model present on the device. Until that is wired, `complete` throws
/// `.modelUnavailable`, so `MeetingPipeline`'s best-effort summary path degrades to
/// a transcript-only note — exactly like a missing cloud key. The default backend
/// is not `.localGemma`, so this never changes shipped behavior on its own.
///
/// To finish on device:
///   1. Add the LiteRT-LM Swift package to the *app* target (not this package).
///   2. Download + verify `GemmaModel.bundleName` into `GemmaModel.url(appSupport:)`.
///   3. Replace the `throw` in `complete` with a LiteRT-LM session that runs
///      `system` + `user` and returns the text, honoring `maxTokens`.
public struct GemmaProvider: LLMProvider {
  private let modelURL: URL?

  /// - Parameter modelURL: the on-disk LiteRT-LM bundle, or `nil` when not installed.
  public init(modelURL: URL? = nil) {
    self.modelURL = modelURL
  }

  /// True only when the model bundle exists on disk. The app checks this before
  /// offering the on-device backend so it can prompt a download instead of failing.
  public var isModelInstalled: Bool {
    guard let modelURL else { return false }
    return FileManager.default.fileExists(atPath: modelURL.path)
  }

  public func complete(system: String, user: String, maxTokens: Int) async throws -> String {
    // Device-side finish: run LiteRT-LM inference on Gemma 4 E4B here (feed `system`
    // + `user`, cap output at `maxTokens`). Until the runtime + model are wired on a
    // real device, report unavailability so callers fall back gracefully and never
    // block note creation.
    throw LLMError.modelUnavailable
  }
}
