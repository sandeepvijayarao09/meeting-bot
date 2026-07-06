import Foundation

/// The finished note for one meeting.
public struct MeetingNote: Sendable {
  public let title: String
  public let summaryMarkdown: String
  public let transcriptMarkdown: String
  public let date: Date

  public init(title: String, summaryMarkdown: String, transcriptMarkdown: String, date: Date) {
    self.title = title
    self.summaryMarkdown = summaryMarkdown
    self.transcriptMarkdown = transcriptMarkdown
    self.date = date
  }

  /// Note filename, matching the Python `notes` naming (`YYYY-MM-DD-HHmm-<slug>.md`).
  /// Shared by every front-end so the same meeting yields one consistent filename.
  public var fileName: String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd-HHmm"
    return "\(formatter.string(from: date))-\(Self.slug(title)).md"
  }

  /// Lowercase, hyphenated filename slug (letters/numbers only), capped at 40 chars.
  public static func slug(_ title: String) -> String {
    let mapped = title.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "-" }
    let collapsed = String(mapped).split(separator: "-").joined(separator: "-")
    return collapsed.isEmpty ? "meeting" : String(collapsed.prefix(40))
  }

  /// The full Markdown document (frontmatter + summary + transcript), matching the
  /// layout written by the Python `notes.write_note`.
  public var markdown: String {
    let iso = ISO8601DateFormatter().string(from: date)
    return """
      ---
      title: \(title)
      date: \(iso)
      ---

      # \(title)

      \(summaryMarkdown.isEmpty ? "_Transcript only — no summary._" : summaryMarkdown)

      ## Transcript

      \(transcriptMarkdown)
      """
  }
}

/// Orchestrates a finished session into a note: transcribe each audio chunk
/// (ASRProvider), merge + refine the transcript, then summarize (LLMProvider).
/// The Swift analog of `meetingbot/recorder.py`'s finalize path, mic-only on iOS.
public struct MeetingPipeline {
  private let asr: ASRProvider
  private let llm: LLMProvider?
  private let refine: RefineTier

  /// - Parameters:
  ///   - asr: on-device transcription.
  ///   - llm: summary/refine backend (on-device Gemma or NIM); `nil` → transcript-only note.
  ///   - refine: cleanup tier; "cloud" polishes via `llm` when available, else local.
  public init(asr: ASRProvider, llm: LLMProvider? = nil, refine: RefineTier = .local) {
    self.asr = asr
    self.llm = llm
    self.refine = refine
  }

  public func process(sessionDir: URL, title: String? = nil) async throws -> MeetingNote {
    let entries = Self.readManifest(sessionDir).sorted { $0.start < $1.start }
    var segments: [Segment] = []
    for entry in entries {
      // Tolerate a per-chunk ASR failure (e.g. a silent chunk that the recognizer
      // rejects): skip that chunk rather than abandoning the whole meeting note.
      let text = (try? await asr.transcribe(sessionDir.appendingPathComponent(entry.file))) ?? ""
      let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty {
        segments.append(
          Segment(start: entry.start, end: entry.end, speaker: entry.stream, text: trimmed))
      }
    }

    let turns = Transcript.mergeTurns(segments)
    let transcriptMarkdown = try await refinedTranscript(turns)

    var summary = ""
    if let llm, !transcriptMarkdown.isEmpty {
      // Best-effort: a summary or network failure must never lose the meeting — fall
      // back to a transcript-only note (the transcript is the irreplaceable artifact).
      summary =
        (try? await llm.complete(
          system: Prompts.summarySystem, user: Prompts.summaryUser(transcriptMarkdown),
          maxTokens: 4096)) ?? ""
    }

    let finalTitle = try await resolveTitle(title, summary: summary, transcript: transcriptMarkdown)
    return MeetingNote(
      title: finalTitle, summaryMarkdown: summary, transcriptMarkdown: transcriptMarkdown,
      date: Date())
  }

  // MARK: - Private

  private func refinedTranscript(_ turns: [Turn]) async throws -> String {
    if refine == .off {
      return Transcript.formatTranscript(turns)
    }
    let localMarkdown = Transcript.formatTranscript(Refiner.cleanTurns(turns))
    if refine == .cloud, let llm, !localMarkdown.isEmpty {
      // Best-effort cloud polish; fall back to the local-cleaned text on any failure
      // so a refinement problem never blocks note creation (mirrors refine.py).
      if let polished = try? await llm.complete(
        system: Prompts.refineSystem, user: localMarkdown, maxTokens: 4096), !polished.isEmpty
      {
        return polished
      }
    }
    return localMarkdown
  }

  private func resolveTitle(_ provided: String?, summary: String, transcript: String) async throws
    -> String
  {
    if let provided, !provided.isEmpty { return provided }
    let source = summary.isEmpty ? transcript : summary
    if let llm, !source.isEmpty,
      let raw = try? await llm.complete(
        system: Prompts.titleSystem, user: Prompts.titleUser(source), maxTokens: 64)
    {
      let cleaned = raw.trimmingCharacters(in: CharacterSet(charactersIn: " \"'\n#"))
        .replacingOccurrences(of: "Title:", with: "")
        .trimmingCharacters(in: .whitespaces)
      if !cleaned.isEmpty { return String(cleaned.prefix(80)) }
    }
    return "Meeting \(Self.fallbackTimestamp())"
  }

  private static func fallbackTimestamp() -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d HH:mm"
    return formatter.string(from: Date())
  }

  struct ManifestEntry {
    let stream: String
    let file: String
    let start: Double
    let end: Double
  }

  static func readManifest(_ dir: URL) -> [ManifestEntry] {
    guard
      let text = try? String(
        contentsOf: dir.appendingPathComponent("manifest.jsonl"), encoding: .utf8)
    else { return [] }
    var entries: [ManifestEntry] = []
    for line in text.split(separator: "\n") {
      guard let data = line.data(using: .utf8),
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let stream = object["stream"] as? String,
        let file = object["file"] as? String
      else { continue }
      let start = (object["start"] as? Double) ?? 0
      let end = (object["end"] as? Double) ?? 0
      entries.append(ManifestEntry(stream: stream, file: file, start: start, end: end))
    }
    return entries
  }
}

/// Prompts shared by the on-device and cloud LLM backends. Compact ports of the
/// templates under `prompts/` on the Python side.
enum Prompts {
  static let summarySystem =
    "You are an expert meeting notetaker. You write crisp, factual, well-structured "
    + "Markdown notes and never invent details that are not in the source material."

  static func summaryUser(_ transcript: String) -> String {
    """
    Write polished meeting notes in Markdown with these sections: ## Summary (2-4 bullets),
    ## Key points, ## Decisions, ## Action items (as `- [ ] task — owner — due`), and
    ## Open questions. Use ONLY facts from the transcript; never invent names, numbers,
    owners, or dates. If a section has nothing, write "None." Output only the note.

    # Transcript
    \(transcript)
    """
  }

  static let refineSystem =
    "You clean up a speech-to-text meeting transcript. Remove filler words, false starts, "
    + "and stutters, and fix punctuation and capitalization. Keep EVERY fact, name, number, "
    + "and the speaker's exact meaning — never add, summarize, reorder, or invent content. "
    + "Preserve the '**Speaker** [mm:ss]: text' line structure exactly. Output only the transcript."

  static let titleSystem =
    "You write short, specific meeting titles, like a smart calendar entry. Capture the main "
    + "topic or outcome, never the date."

  static func titleUser(_ source: String) -> String {
    "Give a short, specific title (3 to 8 words) for this meeting. Title Case, no quotes, no "
      + "date, no trailing punctuation. Output the title only.\n\n" + String(source.prefix(4000))
  }
}
