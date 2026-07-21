import XCTest

@testable import MeetingBotKit

final class TranscriptTests: XCTestCase {
  func testInterleavesAndLabelsSpeakers() {
    let segments = [
      Segment(start: 10, end: 12, speaker: "sys", text: "world"),
      Segment(start: 0, end: 2, speaker: "mic", text: "hello"),
    ]
    let turns = Transcript.mergeTurns(segments)
    XCTAssertEqual(turns.map(\.speaker), ["Me", "Them"])
    XCTAssertEqual(turns.map(\.text), ["hello", "world"])
  }

  func testCoalescesSameSpeakerWithinGap() {
    let segments = [
      Segment(start: 0, end: 2, speaker: "mic", text: "one"),
      Segment(start: 2.5, end: 4, speaker: "mic", text: "two"),
    ]
    let turns = Transcript.mergeTurns(segments)
    XCTAssertEqual(turns.count, 1)
    XCTAssertEqual(turns[0].text, "one two")
    XCTAssertEqual(turns[0].end, 4)
  }

  func testDedupesBoundaryEcho() {
    let segments = [
      Segment(start: 0, end: 2, speaker: "sys", text: "ship the beta"),
      Segment(start: 30, end: 32, speaker: "sys", text: "Ship the beta"),  // echo
    ]
    let joined = Transcript.formatTranscript(Transcript.mergeTurns(segments)).lowercased()
    XCTAssertEqual(joined.components(separatedBy: "ship the beta").count - 1, 1)
  }

  func testFormatTranscript() {
    let turns = [Turn(speaker: "Me", start: 65, end: 67, text: "hi")]
    XCTAssertEqual(Transcript.formatTranscript(turns), "**Me** [01:05]: hi")
    let long = [Turn(speaker: "Me", start: 3725, end: 3726, text: "x")]
    XCTAssertTrue(Transcript.formatTranscript(long).contains("[1:02:05]"))
  }
}

/// A fake ASR that returns canned text per file name, so the pipeline can be tested
/// without WhisperKit or real audio.
private struct FakeASR: ASRProvider {
  let byFile: [String: String]
  func transcribe(_ wav: URL) async throws -> String { byFile[wav.lastPathComponent] ?? "" }
}

/// An ASR that throws for one chunk (e.g. a silent chunk the recognizer rejects),
/// to prove the pipeline tolerates per-chunk failures instead of aborting the note.
private struct PartiallyFailingASR: ASRProvider {
  let failFile: String
  let text: [String: String]
  struct Boom: Error {}
  func transcribe(_ wav: URL) async throws -> String {
    if wav.lastPathComponent == failFile { throw Boom() }
    return text[wav.lastPathComponent] ?? ""
  }
}

/// A fake LLM that records prompts and returns canned responses.
private actor FakeLLM: LLMProvider {
  private(set) var prompts: [String] = []
  let response: String
  init(response: String) { self.response = response }
  func complete(system: String, user: String, maxTokens: Int) async throws -> String {
    prompts.append(user)
    return response
  }
}

/// An LLM that always fails (network down / bad key), to prove a summary failure never
/// loses the meeting — the pipeline must degrade to a transcript-only note.
private struct FailingLLM: LLMProvider {
  struct Down: Error {}
  func complete(system: String, user: String, maxTokens: Int) async throws -> String {
    throw Down()
  }
}

final class PipelineTests: XCTestCase {
  private func makeSession() throws -> URL {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let manifest = [
      #"{"stream":"mic","file":"mic-0001.wav","start":0.0,"end":3.0}"#,
      #"{"stream":"mic","file":"mic-0002.wav","start":3.0,"end":6.0}"#,
    ].joined(separator: "\n")
    try manifest.write(
      to: dir.appendingPathComponent("manifest.jsonl"), atomically: true, encoding: .utf8)
    return dir
  }

  func testRefinesTranscriptAndSummarizes() async throws {
    let dir = try makeSession()
    defer { try? FileManager.default.removeItem(at: dir) }
    let asr = FakeASR(byFile: [
      "mic-0001.wav": "um so, I I think we should ship",
      "mic-0002.wav": "the the plan looks good",
    ])
    let llm = FakeLLM(response: "## Summary\n- ok")
    let note = try await MeetingPipeline(asr: asr, llm: llm, refine: .local)
      .process(sessionDir: dir, title: "Sync")

    XCTAssertEqual(note.title, "Sync")
    XCTAssertEqual(note.summaryMarkdown, "## Summary\n- ok")
    // Transcript is locally refined: fillers/stutters gone, sentence-capitalized.
    XCTAssertTrue(note.transcriptMarkdown.contains("I think we should ship"))
    XCTAssertFalse(note.transcriptMarkdown.contains("the the"))
    XCTAssertFalse(note.transcriptMarkdown.lowercased().contains(" um "))
    XCTAssertTrue(note.markdown.contains("## Transcript"))
  }

  func testTranscriptOnlyWhenNoLLM() async throws {
    let dir = try makeSession()
    defer { try? FileManager.default.removeItem(at: dir) }
    let asr = FakeASR(byFile: ["mic-0001.wav": "hello team", "mic-0002.wav": "second chunk"])
    let note = try await MeetingPipeline(asr: asr, llm: nil, refine: .local)
      .process(sessionDir: dir, title: nil)
    XCTAssertEqual(note.summaryMarkdown, "")
    XCTAssertTrue(note.transcriptMarkdown.contains("Hello team"))
  }

  func testSummaryFailureYieldsTranscriptOnlyNote() async throws {
    let dir = try makeSession()
    defer { try? FileManager.default.removeItem(at: dir) }
    let asr = FakeASR(byFile: ["mic-0001.wav": "hello team", "mic-0002.wav": "we shipped it"])
    // The summary LLM throws (network/key failure). The note must still be produced
    // from the transcript rather than process() throwing and losing the meeting.
    let note = try await MeetingPipeline(asr: asr, llm: FailingLLM(), refine: .local)
      .process(sessionDir: dir, title: "Never lost")
    XCTAssertEqual(note.title, "Never lost")
    XCTAssertEqual(note.summaryMarkdown, "", "summary failure should degrade to transcript-only")
    XCTAssertTrue(note.transcriptMarkdown.contains("Hello team"))
    XCTAssertTrue(note.markdown.contains("Transcript only"), "body flags the missing summary")
  }

  func testToleratesPerChunkASRFailure() async throws {
    let dir = try makeSession()
    defer { try? FileManager.default.removeItem(at: dir) }
    // First chunk throws; the note must still be produced from the surviving chunk.
    let asr = PartiallyFailingASR(
      failFile: "mic-0001.wav", text: ["mic-0002.wav": "second chunk survived"])
    let note = try await MeetingPipeline(asr: asr, llm: nil, refine: .local)
      .process(sessionDir: dir, title: "Resilient")
    XCTAssertEqual(note.title, "Resilient")
    XCTAssertTrue(note.transcriptMarkdown.contains("Second chunk survived"))
  }

  func testNIMProviderRequiresKey() async {
    let provider = NIMProvider(apiKey: "")
    do {
      _ = try await provider.complete(system: "s", user: "u")
      XCTFail("expected missingKey")
    } catch {
      XCTAssertEqual(error as? LLMError, .missingKey)
    }
  }

  func testGemmaProviderReportsUnavailableUntilWired() async {
    let provider = GemmaProvider()  // no model installed
    XCTAssertFalse(provider.isModelInstalled)
    do {
      _ = try await provider.complete(system: "s", user: "u", maxTokens: 64)
      XCTFail("expected modelUnavailable")
    } catch {
      XCTAssertEqual(error as? LLMError, .modelUnavailable)
    }
  }

  func testLocalGemmaBackendDegradesToTranscriptOnly() async throws {
    let dir = try makeSession()
    defer { try? FileManager.default.removeItem(at: dir) }
    let asr = FakeASR(byFile: ["mic-0001.wav": "hello team", "mic-0002.wav": "we shipped it"])
    // Fully-local backend selected but the model isn't installed yet: the meeting must
    // still be saved as a transcript-only note, never blocked (same contract as a
    // missing cloud key).
    let note = try await MeetingPipeline(asr: asr, llm: GemmaProvider(), refine: .local)
      .process(sessionDir: dir, title: "Local")
    XCTAssertEqual(note.summaryMarkdown, "")
    XCTAssertTrue(note.transcriptMarkdown.contains("Hello team"))
    XCTAssertTrue(note.markdown.contains("Transcript only"))
  }

  func testNoteFileNameAndSlug() {
    // Slug is deterministic; the date prefix is local-tz so assert on the slug suffix.
    let note = MeetingNote(
      title: "Q3 Launch Planning!!", summaryMarkdown: "", transcriptMarkdown: "", date: Date())
    XCTAssertTrue(note.fileName.hasSuffix("-q3-launch-planning.md"), note.fileName)
    XCTAssertEqual(MeetingNote.slug("  Hello,  World  "), "hello-world")
    XCTAssertEqual(MeetingNote.slug("!!!"), "meeting")  // no alphanumerics → fallback
    XCTAssertEqual(MeetingNote.slug(String(repeating: "a", count: 100)).count, 40)  // capped
  }
}
