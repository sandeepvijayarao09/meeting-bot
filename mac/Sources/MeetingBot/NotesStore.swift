import Combine
import Foundation

/// One meeting note parsed from a Markdown file in the notes directory.
struct MeetingNote: Identifiable, Hashable {
  let id: String  // file path
  let title: String
  let date: Date
  let summaryMarkdown: String
  let transcriptMarkdown: String
  let url: URL

  var dateLabel: String {
    let f = DateFormatter()
    f.dateStyle = .medium
    f.timeStyle = .short
    return f.string(from: date)
  }
}

/// Loads and watches the Markdown notes the pipeline writes. Read-only here;
/// the source of truth stays on disk (and the SQLite FTS index).
@MainActor
final class NotesStore: ObservableObject {
  @Published private(set) var notes: [MeetingNote] = []

  func reload() {
    let dir = Paths.notesDirectory
    let files =
      (try? FileManager.default.contentsOfDirectory(
        at: dir, includingPropertiesForKeys: nil)) ?? []
    notes =
      files
      .filter { $0.pathExtension == "md" }
      .compactMap(Self.parse)
      .sorted { $0.date > $1.date }
  }

  /// Filter by title or content (used by the search field).
  func filtered(_ query: String) -> [MeetingNote] {
    let q = query.trimmingCharacters(in: .whitespaces).lowercased()
    guard !q.isEmpty else { return notes }
    return notes.filter {
      $0.title.lowercased().contains(q)
        || $0.summaryMarkdown.lowercased().contains(q)
        || $0.transcriptMarkdown.lowercased().contains(q)
    }
  }

  // MARK: - Parsing

  static func parse(_ url: URL) -> MeetingNote? {
    guard let body = try? String(contentsOf: url, encoding: .utf8) else { return nil }
    let front = frontmatter(body)
    let title = front["title"] ?? url.deletingPathExtension().lastPathComponent
    let date = front["date"].flatMap(parseDate) ?? fileDate(url)

    // Split the body (after frontmatter) into the summary and transcript halves.
    let afterFront = stripFrontmatter(body)
    let parts = afterFront.components(separatedBy: "## Transcript")
    let summary = stripLeadingH1(parts.first ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let transcript =
      parts.count > 1 ? parts[1].trimmingCharacters(in: .whitespacesAndNewlines) : ""

    return MeetingNote(
      id: url.path, title: title, date: date,
      summaryMarkdown: summary, transcriptMarkdown: transcript, url: url)
  }

  private static func frontmatter(_ body: String) -> [String: String] {
    guard body.hasPrefix("---") else { return [:] }
    let lines = body.components(separatedBy: "\n")
    var result: [String: String] = [:]
    for line in lines.dropFirst() {
      if line == "---" { break }
      if let colon = line.firstIndex(of: ":") {
        let key = String(line[..<colon]).trimmingCharacters(in: .whitespaces)
        let value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
        result[key] = value
      }
    }
    return result
  }

  private static func stripFrontmatter(_ body: String) -> String {
    guard body.hasPrefix("---") else { return body }
    let parts = body.components(separatedBy: "\n---\n")
    return parts.count > 1 ? parts.dropFirst().joined(separator: "\n---\n") : body
  }

  private static func stripLeadingH1(_ text: String) -> String {
    var lines = text.components(separatedBy: "\n")
    while let first = lines.first, first.trimmingCharacters(in: .whitespaces).isEmpty {
      lines.removeFirst()
    }
    if let first = lines.first, first.hasPrefix("# ") {
      lines.removeFirst()
    }
    return lines.joined(separator: "\n")
  }

  private static func parseDate(_ s: String) -> Date? {
    ISO8601DateFormatter().date(from: s)
      ?? {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.date(from: s)
      }()
  }

  private static func fileDate(_ url: URL) -> Date {
    (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate)
      ?? Date.distantPast
  }
}
