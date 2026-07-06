import AVFoundation
import Foundation

/// Records a meeting into a session directory.
///
/// Output layout (consumed by the transcription pipeline):
///   mic-0001.wav, mic-0002.wav, ...   microphone ("me")
///   sys-0001.wav, sys-0002.wav, ...   system audio ("them") — macOS only
///   manifest.jsonl                    one line per closed chunk
///   session.json                      session metadata
///
/// On macOS this captures mic + system audio (ScreenCaptureKit). On iOS, which
/// cannot capture other apps' audio, it is a **mic-only** recorder. Capture errors
/// after a successful `start()` are delivered to `onError` rather than crashing.
public final class SessionRecorder {
  public static let sampleRate = Int(StreamWriter.sampleRate)

  /// Invoked if capture stops unexpectedly mid-session (e.g. permission revoked).
  public var onError: ((Error) -> Void)?

  private let directory: URL
  private let chunkSeconds: Int
  private let manifest: Manifest
  private let micWriter: StreamWriter
  private let microphone: MicCapture
  #if os(macOS)
    private let sysWriter: StreamWriter
    private let systemAudio: SystemAudioCapture
  #endif

  public init(sessionDirectory: URL, chunkSeconds: Int = 30) throws {
    try FileManager.default.createDirectory(
      at: sessionDirectory, withIntermediateDirectories: true)
    self.directory = sessionDirectory
    self.chunkSeconds = chunkSeconds
    self.manifest = try Manifest(url: sessionDirectory.appendingPathComponent("manifest.jsonl"))
    self.micWriter = StreamWriter(
      stream: "mic", directory: sessionDirectory, chunkSeconds: chunkSeconds, manifest: manifest)
    self.microphone = MicCapture(writer: micWriter)
    #if os(macOS)
      self.sysWriter = StreamWriter(
        stream: "sys", directory: sessionDirectory, chunkSeconds: chunkSeconds, manifest: manifest)
      self.systemAudio = SystemAudioCapture(writer: sysWriter)
      self.systemAudio.onStop = { [weak self] error in self?.onError?(error) }
    #endif
    // Wire after every stored property is initialized (macOS sets sysWriter/
    // systemAudio above) so these closures may legally capture self.
    self.microphone.onError = { [weak self] error in self?.onError?(error) }
  }

  /// Requests microphone permission, configures audio, and starts capture.
  /// Throws if permission is denied or capture cannot start.
  public func start() async throws {
    guard await AVCaptureDevice.requestAccess(for: .audio) else {
      throw CaptureError(
        "microphone permission denied — enable it in Settings > Privacy & Security > Microphone")
    }
    #if os(iOS)
      let session = AVAudioSession.sharedInstance()
      try session.setCategory(.record, mode: .default)
      try session.setActive(true)
    #endif
    #if os(macOS)
      do {
        try await systemAudio.start()
      } catch {
        throw CaptureError(
          "Screen Recording permission is needed to capture meeting audio. Grant the app in "
            + "System Settings > Privacy & Security > Screen & System Audio Recording, then QUIT "
            + "and REOPEN the app (the grant only applies on relaunch).")
      }
    #endif
    try microphone.start()
    writeSessionInfo()
  }

  /// Stops capture and flushes any partial chunks. Safe to call once.
  public func stop() async {
    #if os(macOS)
      await systemAudio.stop()
    #endif
    microphone.stop()
    micWriter.finish()
    #if os(macOS)
      sysWriter.finish()
    #endif
    #if os(iOS)
      // Notify other apps so their audio can resume after we release the session.
      try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    #endif
  }

  private func writeSessionInfo() {
    let info: [String: Any] = [
      "started_at": ISO8601DateFormatter().string(from: Date()),
      "sample_rate": Self.sampleRate,
      "chunk_seconds": chunkSeconds,
    ]
    if let data = try? JSONSerialization.data(withJSONObject: info, options: [.prettyPrinted]) {
      try? data.write(to: directory.appendingPathComponent("session.json"))
    }
  }
}
