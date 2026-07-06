import CaptureKit
import Foundation
import MeetingBotKit
import SwiftUI

/// Drives one iOS meeting: mic capture (CaptureKit.SessionRecorder) → on-device
/// transcription + refine + summarize (MeetingBotKit.MeetingPipeline) → saved note.
@MainActor
final class RecordingController: ObservableObject {
  enum Phase: Equatable { case idle, recording, processing }

  @Published var phase: Phase = .idle
  @Published var elapsed: TimeInterval = 0
  @Published var statusMessage = ""

  private var recorder: SessionRecorder?
  private var sessionDir: URL?
  private var startedAt: Date?
  private var ticker: Task<Void, Never>?

  func start() async {
    guard phase == .idle else { return }
    // Ask for Speech recognition up front — requesting it only at stop() means a
    // denial silently wastes a whole recorded meeting.
    let speechAuthorized = await AppleSpeechASR.requestAuthorization()
    do {
      let dir = Storage.newSessionDir()
      let recorder = try SessionRecorder(sessionDirectory: dir)
      // Surface an unrecoverable capture failure (e.g. the engine couldn't resume
      // after an interruption) instead of silently losing the rest of the meeting.
      recorder.onError = { [weak self] error in
        Task { @MainActor in
          self?.statusMessage = "Recording interrupted: \(error.localizedDescription)"
        }
      }
      try await recorder.start()
      self.recorder = recorder
      self.sessionDir = dir
      self.startedAt = Date()
      self.statusMessage =
        speechAuthorized ? "" : "Recording — enable Speech Recognition in Settings to transcribe."
      self.phase = .recording
      startTicker()
    } catch {
      statusMessage = Self.friendlyStartError(error)
      phase = .idle
    }
  }

  func stop(apiKey: String) async {
    guard phase == .recording, let recorder, let sessionDir else { return }
    stopTicker()
    phase = .processing
    await recorder.stop()
    self.recorder = nil

    let llm: LLMProvider? = apiKey.isEmpty ? nil : NIMProvider(apiKey: apiKey)
    let pipeline = MeetingPipeline(asr: AppleSpeechASR(), llm: llm, refine: .local)
    do {
      let note = try await pipeline.process(sessionDir: sessionDir, title: nil)
      try Storage.saveNote(note)
      // Summary is best-effort (see MeetingPipeline); an empty one with a key set
      // means the cloud call failed — tell the user, but the note still saved.
      statusMessage =
        (!apiKey.isEmpty && note.summaryMarkdown.isEmpty)
        ? "Saved “\(note.title)” — summary unavailable (check your key or connection)."
        : "Saved “\(note.title)”."
    } catch {
      statusMessage = Self.friendlySaveError(error)
    }
    self.sessionDir = nil
    phase = .idle
  }

  /// User-facing copy for a capture failure — never a raw `\(error)` dump.
  private static func friendlyStartError(_ error: Error) -> String {
    if let capture = error as? CaptureError { return capture.description }
    return "Couldn't start recording. Check Microphone access in Settings › Privacy."
  }

  private static func friendlySaveError(_ error: Error) -> String {
    "Couldn't finish the note. Please try again."
  }

  // MARK: - Elapsed ticker

  private func startTicker() {
    elapsed = 0
    ticker = Task { [weak self] in
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 1_000_000_000)
        await MainActor.run {
          guard let self, let started = self.startedAt else { return }
          self.elapsed = Date().timeIntervalSince(started)
        }
      }
    }
  }

  private func stopTicker() {
    ticker?.cancel()
    ticker = nil
  }
}
