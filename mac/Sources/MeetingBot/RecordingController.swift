import AppKit
import CaptureKit
import Combine
import CoreGraphics
import Foundation
import MeetingBotKit
@preconcurrency import UserNotifications

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

  /// Where finished notes are saved. "apple_notes" | "google_docs" | "markdown".
  /// (A local Markdown copy is always kept too — it backs search and the Meetings
  /// window — but this is the destination the user actually reads.)
  @Published var destination: String {
    didSet { UserDefaults.standard.set(destination, forKey: "destination") }
  }

  /// Meeting-type template ("Recipe") that shapes the summary.
  @Published var template: String {
    didSet { UserDefaults.standard.set(template, forKey: "template") }
  }

  static let destinations: [(id: String, label: String)] = [
    ("apple_notes", "Apple Notes"),
    ("google_docs", "Google Docs"),
    ("markdown", "Markdown files"),
  ]

  static let templates: [(id: String, label: String)] = [
    ("default", "General"),
    ("standup", "Standup"),
    ("one_on_one", "1:1"),
    ("interview", "Interview"),
    ("sales_call", "Sales call"),
  ]

  private var recorder: SessionRecorder?
  private var sessionURL: URL?
  private var startedAt: Date?
  private var pendingTitle: String?
  private var timer: Timer?

  init() {
    destination = UserDefaults.standard.string(forKey: "destination") ?? "apple_notes"
    template = UserDefaults.standard.string(forKey: "template") ?? "default"
    // Ask for notification permission once at launch; notify() then just posts.
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    // Register + prompt for Screen Recording up front so it's granted before the
    // first recording (the grant only takes effect on the next launch, so doing
    // this at launch avoids a failed first recording mid-meeting). This only
    // requests permission — it never records; recording happens solely on Start.
    if !CGPreflightScreenCaptureAccess() {
      DispatchQueue.global(qos: .userInitiated).async { _ = CGRequestScreenCaptureAccess() }
    }
    // Never lose a recording: finish any session interrupted by a crash/force-quit.
    recoverInterrupted()
  }

  var isRecording: Bool { state == .recording }

  /// On launch, hand any interrupted recordings to the pipeline to finish.
  private func recoverInterrupted() {
    guard let mbot = Paths.mbotExecutable() else { return }
    let dest = destination
    let tmpl = template
    Task.detached {
      let process = Process()
      process.executableURL = mbot
      process.arguments = ["recover", "--print-note-paths"]
      var env = ProcessInfo.processInfo.environment
      env["MBOT_EXPORTERS"] = dest
      env["MBOT_TEMPLATE"] = tmpl
      env["MBOT_NOTES_DIR"] = Paths.notesDirectory.path
      process.environment = env
      let pipe = Pipe()
      process.standardOutput = pipe
      process.standardError = Pipe()
      guard (try? process.run()) != nil else { return }
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      process.waitUntilExit()
      let paths =
        (String(data: data, encoding: .utf8) ?? "")
        .split(separator: "\n").map(String.init).filter { !$0.isEmpty }
      guard !paths.isEmpty else { return }
      await MainActor.run {
        self.lastNotePath = paths.last
        self.notify("Recovered meeting", "Finished \(paths.count) interrupted recording(s).")
      }
    }
  }

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
      // Name the meeting from the current calendar event, if any.
      self.pendingTitle = await CalendarService.currentEventTitle()
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

  /// Hand the finished session to the transcription + notes pipeline. Runs the
  /// in-process native pipeline when opted in (the App Store path), else the Python
  /// sidecar (the current notarized-download default).
  private func process(_ sessionURL: URL) async {
    if Paths.useNativePipeline {
      await processNatively(sessionURL)
      return
    }
    guard let mbot = Paths.mbotExecutable() else {
      fail("mbot pipeline not found — run scripts/install-macos.sh or set MBOT_BIN")
      return
    }
    do {
      let notePath = try await runPipeline(mbot: mbot, sessionURL: sessionURL, title: pendingTitle)
      lastNotePath = notePath
      state = .idle
      if let notePath { NSWorkspace.shared.open(URL(fileURLWithPath: notePath)) }
      notify("Note ready", notePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "")
    } catch {
      fail("processing failed: \(error.localizedDescription)")
    }
  }

  private func runPipeline(mbot: URL, sessionURL: URL, title: String?) async throws -> String? {
    let process = Process()
    process.executableURL = mbot
    var args = ["process", sessionURL.path, "--print-note-path"]
    if let title, !title.isEmpty { args += ["--title", title] }
    process.arguments = args
    // Save to the chosen destination (Apple Notes / Google Docs); markdown is
    // always kept too as the local search index. Pin the notes dir so the pipeline
    // writes exactly where the Meetings window reads, wherever the app is installed.
    var env = ProcessInfo.processInfo.environment
    env["MBOT_EXPORTERS"] = destination
    env["MBOT_TEMPLATE"] = template
    env["MBOT_NOTES_DIR"] = Paths.notesDirectory.path
    process.environment = env
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

  /// In-process native pipeline (MeetingBotKit) — no Python sidecar, no external
  /// process. The same code path the iOS app uses; the App Store build will make this
  /// the only path. Summary is best-effort inside the pipeline, so a note always saves.
  private func processNatively(_ sessionURL: URL) async {
    // Request Speech authorization before touching SFSpeechRecognizer. Required: the
    // usage-description prompt gates on-device transcription, and accessing Speech
    // without it (and without NSSpeechRecognitionUsageDescription in Info.plist) trips
    // macOS TCC. Denied → chunks transcribe to "" and the note is transcript-empty.
    _ = await AppleSpeechASR.requestAuthorization()
    let llm: LLMProvider? = Paths.nvidiaKey().map { NIMProvider(apiKey: $0) }
    let pipeline = MeetingPipeline(asr: AppleSpeechASR(), llm: llm, refine: .local)
    do {
      let note = try await pipeline.process(sessionDir: sessionURL, title: pendingTitle)
      let path = try Self.writeNote(note)
      lastNotePath = path
      state = .idle
      NSWorkspace.shared.open(URL(fileURLWithPath: path))
      notify("Note ready", URL(fileURLWithPath: path).lastPathComponent)
    } catch {
      fail("processing failed: \(error.localizedDescription)")
    }
  }

  /// Write a finished note as Markdown into the notes directory, matching the layout
  /// NotesStore reads. Filename/slug come from the shared MeetingBotKit helper so the
  /// mac, iOS, and Python front-ends all name the same meeting identically.
  private static func writeNote(_ note: MeetingBotKit.MeetingNote) throws -> String {
    let dir = Paths.notesDirectory
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let url = dir.appendingPathComponent(note.fileName)
    try note.markdown.write(to: url, atomically: true, encoding: .utf8)
    return url.path
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
    logInfo("\(title): \(body)")
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = body
    let request = UNNotificationRequest(
      identifier: UUID().uuidString, content: content, trigger: nil)
    UNUserNotificationCenter.current().add(request)
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
