import AppKit
import CaptureKit
import Combine
import Foundation

@MainActor
final class RecordingController: ObservableObject {
  enum State: Equatable {
    case idle
    case recording
    case processing
    case error(String)
  }

  @Published private(set) var state: State = .idle
  @Published private(set) var elapsed: TimeInterval = 0
  @Published private(set) var lastNotePath: String?

  private var recorder: SessionRecorder?
  private var sessionURL: URL?
  private var startedAt: Date?
  private var timer: Timer?

  var isRecording: Bool { state == .recording }

  var elapsedString: String {
    let total = Int(elapsed)
    return String(format: "%02d:%02d", total / 60, total % 60)
  }

  func toggle() {
    switch state {
    case .idle, .error: start()
    case .recording: stop()
    case .processing: break
    }
  }

  // MARK: - Recording

  private func start() {
    let stamp = Self.timestampFormatter.string(from: Date())
    let url = Paths.sessionsDirectory.appendingPathComponent("\(stamp)-meeting")
    Task {
      do {
        let recorder = try SessionRecorder(sessionDirectory: url)
        recorder.onError = { [weak self] error in
          Task { @MainActor in self?.fail(error.localizedDescription) }
        }
        try await recorder.start()
        self.recorder = recorder
        self.sessionURL = url
        self.startedAt = Date()
        self.elapsed = 0
        self.state = .recording
        self.startTimer()
      } catch {
        let message = (error as? CaptureError)?.description ?? error.localizedDescription
        self.fail(message)
      }
    }
  }

  private func stop() {
    guard let recorder, let sessionURL else { return }
    stopTimer()
    state = .processing
    Task {
      await recorder.stop()
      self.recorder = nil
      await self.process(sessionURL)
    }
  }

  /// Hand the finished session to the Python pipeline for transcription + notes.
  private func process(_ sessionURL: URL) async {
    guard let mbot = Paths.mbotExecutable() else {
      fail("mbot pipeline not found — run scripts/install-macos.sh or set MBOT_BIN")
      return
    }
    do {
      let notePath = try await runPipeline(mbot: mbot, sessionURL: sessionURL)
      lastNotePath = notePath
      state = .idle
      if let notePath { NSWorkspace.shared.open(URL(fileURLWithPath: notePath)) }
      notify("Note ready", notePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "")
    } catch {
      fail("processing failed: \(error.localizedDescription)")
    }
  }

  private func runPipeline(mbot: URL, sessionURL: URL) async throws -> String? {
    let process = Process()
    process.executableURL = mbot
    process.arguments = ["process", sessionURL.path, "--print-note-path"]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    try process.run()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    let output = String(data: data, encoding: .utf8) ?? ""
    guard process.terminationStatus == 0 else {
      throw CaptureError(output.trimmingCharacters(in: .whitespacesAndNewlines))
    }
    // The pipeline prints the note path on its last non-empty line.
    return output.split(separator: "\n").map(String.init).last { !$0.isEmpty }
  }

  // MARK: - Helpers

  private func fail(_ message: String) {
    stopTimer()
    recorder = nil
    state = .error(message)
    notify("Meeting Bot error", message)
  }

  private func startTimer() {
    timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
      Task { @MainActor in
        guard let self, let startedAt = self.startedAt else { return }
        self.elapsed = Date().timeIntervalSince(startedAt)
      }
    }
  }

  private func stopTimer() {
    timer?.invalidate()
    timer = nil
  }

  private func notify(_ title: String, _ body: String) {
    let content = "\(title): \(body)"
    logInfo(content)
  }

  private static let timestampFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    return formatter
  }()
}

private func logInfo(_ message: String) {
  FileHandle.standardError.write(Data((message + "\n").utf8))
}
