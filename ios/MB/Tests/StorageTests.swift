import MeetingBotKit
import XCTest

@testable import MB

final class StorageTests: XCTestCase {
  // Slug/filename logic is unit-tested in MeetingBotKitTests (the single source of
  // truth); testSaveAndListNote below covers the iOS saveNote → filename integration.

  func testSaveAndListNote() throws {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: dir) }

    let note = MeetingNote(
      title: "Sync Up",
      summaryMarkdown: "## Summary\n- ok",
      transcriptMarkdown: "**Me** [00:00]: hi",
      date: Date())
    let url = try Storage.saveNote(note, to: dir)

    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    XCTAssertTrue(url.lastPathComponent.hasSuffix("-sync-up.md"))

    let listed = NotesIndex.list(in: dir)
    XCTAssertEqual(listed.count, 1)
    XCTAssertEqual(listed.first?.title, "Sync Up")  // parsed from frontmatter
    XCTAssertTrue(listed.first?.body.contains("## Transcript") ?? false)
  }

  func testListEmptyDirectory() {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    XCTAssertEqual(NotesIndex.list(in: dir), [])
  }
}
