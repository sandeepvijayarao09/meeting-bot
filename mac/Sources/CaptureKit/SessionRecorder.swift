import AVFoundation
import Foundation

/// Records the microphone and system audio of a meeting into a session directory.
///
/// Output layout (consumed by the Python transcription pipeline):
///   mic-0001.wav, mic-0002.wav, ...   microphone ("me")
///   sys-0001.wav, sys-0002.wav, ...   system audio ("them")
///   manifest.jsonl                    one line per closed chunk
///   session.json                      session metadata
///
/// Shared by the `audiocap` CLI and the MeetingBot app. Capture errors after a
/// successful `start()` are delivered to `onError` rather than crashing.
public final class SessionRecorder {
  public static let sampleRate = Int(StreamWriter.sampleRate)

  /// Invoked if capture stops unexpectedly mid-session (e.g. permission revoked).
  public var onError: ((Error) -> Void)?

  private let directory: URL
  private let chunkSeconds: Int
  private let manifest: Manifest
  private let micWriter: StreamWriter
  private let sysWriter: StreamWriter
  private let microphone: MicCapture
  private let systemAudio: SystemAudioCapture

  public init(sessionDirectory: URL, chunkSeconds: Int = 30) throws {
    try FileManager.default.createDirectory(
      at: sessionDirectory, withIntermediateDirectories: true)
    self.directory = sessionDirectory
    self.chunkSeconds = chunkSeconds
    self.manifest = try Manifest(url: sessionDirectory.appendingPathComponent("manifest.jsonl"))
    self.micWriter = StreamWriter(
      stream: "mic", directory: sessionDirectory, chunkSeconds: chunkSeconds, manifest: manifest)
    self.sysWriter = StreamWriter(
      stream: "sys", directory: sessionDirectory, chunkSeconds: chunkSeconds, manifest: manifest)
    self.microphone = MicCapture(writer: micWriter)
    self.systemAudio = SystemAudioCapture(writer: sysWriter)
    self.systemAudio.onStop = { [weak self] error in self?.onError?(error) }
  }

  /// Requests microphone permission, then starts system-audio + mic capture.
  /// Throws if permission is denied or capture cannot start.
  public func start() async throws {
    guard await AVCaptureDevice.requestAccess(for: .audio) else {
      throw CaptureError(
        "microphone permission denied — enable it in System Settings > Privacy & Security "
          + "> Microphone")
    }
    do {
      try await systemAudio.start()
    } catch {
      throw CaptureError(
        "system audio capture failed: \(error.localizedDescription) — grant Screen Recording "
          + "permission in System Settings > Privacy & Security > Screen & System Audio Recording")
    }
    try microphone.start()
    writeSessionInfo()
  }

  /// Stops capture and flushes any partial chunks. Safe to call once.
  public func stop() async {
    await systemAudio.stop()
    microphone.stop()
    micWriter.finish()
    sysWriter.finish()
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
