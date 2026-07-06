import Foundation
import MeetingBotKit

/// App-sandbox storage: sessions (audio) and notes (Markdown) under Documents,
/// mirroring the layout the Python pipeline uses on macOS.
enum Storage {
  static var documents: URL {
    FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
  }
  static var sessionsDir: URL { documents.appendingPathComponent("sessions") }
  static var notesDir: URL { documents.appendingPathComponent("notes") }

  /// A fresh, timestamped session directory (SessionRecorder creates it on disk).
  static func newSessionDir() -> URL {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    return sessionsDir.appendingPathComponent("\(formatter.string(from: Date()))-meeting")
  }

  @discardableResult
  static func saveNote(_ note: MeetingNote, to directory: URL = notesDir) throws -> URL {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    // Filename/slug come from the shared MeetingBotKit helper so iOS names a meeting
    // identically to the macOS app and the Python pipeline (single source of truth).
    let file = directory.appendingPathComponent(note.fileName)
    try note.markdown.write(to: file, atomically: true, encoding: .utf8)
    return file
  }
}

/// A note on disk, for the notes list.
struct NoteFile: Identifiable, Hashable {
  let id: URL
  let title: String
  let body: String
}

enum NotesIndex {
  static func list(in directory: URL = Storage.notesDir) -> [NoteFile] {
    let dir = directory
    let keys: [URLResourceKey] = [.contentModificationDateKey]
    guard
      let urls = try? FileManager.default.contentsOfDirectory(
        at: dir, includingPropertiesForKeys: keys)
    else { return [] }
    return
      urls
      .filter { $0.pathExtension == "md" }
      .sorted { modified($0) > modified($1) }
      .map { url in
        let body = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        return NoteFile(id: url, title: title(from: body, fallback: url), body: body)
      }
  }

  private static func modified(_ url: URL) -> Date {
    (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate)
      ?? .distantPast
  }

  private static func title(from body: String, fallback url: URL) -> String {
    for line in body.split(separator: "\n") {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if trimmed.hasPrefix("title:") {
        return trimmed.replacingOccurrences(of: "title:", with: "").trimmingCharacters(
          in: .whitespaces)
      }
    }
    return url.deletingPathExtension().lastPathComponent
  }
}
