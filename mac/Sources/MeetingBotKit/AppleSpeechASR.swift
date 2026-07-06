#if canImport(Speech)
  import Foundation
  import Speech

  /// On-device speech-to-text using Apple's `SFSpeechRecognizer` (Speech.framework).
  ///
  /// Fully offline (`requiresOnDeviceRecognition = true`), no external dependencies.
  /// Shared by the iOS and macOS apps as the default `ASRProvider`; WhisperKit can
  /// replace it later for higher accuracy without changing the rest of the pipeline.
  public struct AppleSpeechASR: ASRProvider {
    public let locale: Locale

    public init(locale: Locale = Locale(identifier: "en-US")) {
      self.locale = locale
    }

    /// Request Speech recognition authorization once (call at app start / before use).
    public static func requestAuthorization() async -> Bool {
      await withCheckedContinuation { continuation in
        SFSpeechRecognizer.requestAuthorization { status in
          continuation.resume(returning: status == .authorized)
        }
      }
    }

    public func transcribe(_ wav: URL) async throws -> String {
      guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
        return ""
      }
      let request = SFSpeechURLRecognitionRequest(url: wav)
      request.requiresOnDeviceRecognition = true
      request.shouldReportPartialResults = false

      let box = ResumeOnce()
      return try await withCheckedThrowingContinuation { continuation in
        recognizer.recognitionTask(with: request) { result, error in
          if let error {
            box.run { continuation.resume(throwing: error) }
          } else if let result, result.isFinal {
            box.run { continuation.resume(returning: result.bestTranscription.formattedString) }
          }
        }
      }
    }
  }

  /// Guards a checked continuation against the multiple callbacks `recognitionTask`
  /// can deliver, so it resumes exactly once.
  private final class ResumeOnce: @unchecked Sendable {
    private var done = false
    private let lock = NSLock()
    func run(_ body: () -> Void) {
      lock.lock()
      defer { lock.unlock() }
      guard !done else { return }
      done = true
      body()
    }
  }
#endif
