import SwiftUI

/// The product's main window: browse past meetings, read summary + transcript, search.
struct NotesWindow: View {
  @StateObject private var store = NotesStore()
  @State private var query = ""
  @State private var selection: MeetingNote.ID?

  private var results: [MeetingNote] { store.filtered(query) }

  var body: some View {
    NavigationSplitView {
      List(results, selection: $selection) { note in
        VStack(alignment: .leading, spacing: 2) {
          Text(note.title).font(.headline).lineLimit(1)
          Text(note.dateLabel).font(.caption).foregroundStyle(.secondary)
        }
        .tag(note.id)
      }
      .searchable(text: $query, placement: .sidebar, prompt: "Search meetings")
      .navigationTitle("Meetings")
      .frame(minWidth: 240)
      .overlay {
        if store.notes.isEmpty {
          ContentUnavailableView(
            "No meetings yet", systemImage: "mic",
            description: Text("Record a meeting from the menu bar to see it here."))
        }
      }
    } detail: {
      if let id = selection, let note = store.notes.first(where: { $0.id == id }) {
        NoteDetail(note: note)
      } else {
        ContentUnavailableView("Select a meeting", systemImage: "doc.text")
      }
    }
    .toolbar {
      ToolbarItem(placement: .primaryAction) {
        Button {
          store.reload()
        } label: {
          Label("Refresh", systemImage: "arrow.clockwise")
        }
      }
    }
    .onAppear {
      store.reload()
      if selection == nil { selection = store.notes.first?.id }
    }
    .frame(minWidth: 720, minHeight: 460)
  }
}

private struct NoteDetail: View {
  let note: MeetingNote

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        VStack(alignment: .leading, spacing: 4) {
          Text(note.title).font(.largeTitle.bold())
          Text(note.dateLabel).foregroundStyle(.secondary)
        }
        MarkdownText(note.summaryMarkdown)
        if !note.transcriptMarkdown.isEmpty {
          Divider()
          Text("Transcript").font(.title2.bold())
          MarkdownText(note.transcriptMarkdown).textSelection(.enabled)
        }
        HStack {
          Button {
            NSWorkspace.shared.open(note.url)
          } label: {
            Label("Open .md", systemImage: "doc")
          }
          Button {
            NSWorkspace.shared.activateFileViewerSelecting([note.url])
          } label: {
            Label("Reveal in Finder", systemImage: "folder")
          }
        }
        .padding(.top, 4)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(24)
    }
  }

}

/// Renders our Markdown dialect (## headings, - bullets, - [ ] checkboxes, **bold**,
/// paragraphs) as native SwiftUI rather than showing raw markers.
struct MarkdownText: View {
  private let lines: [Substring]

  init(_ text: String) {
    self.lines = text.split(separator: "\n", omittingEmptySubsequences: false)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      ForEach(Array(lines.enumerated()), id: \.offset) { _, raw in
        line(String(raw))
      }
    }
  }

  @ViewBuilder private func line(_ text: String) -> some View {
    let trimmed = text.trimmingCharacters(in: .whitespaces)
    if trimmed.isEmpty {
      Spacer().frame(height: 2)
    } else if let heading = headingBody(trimmed) {
      Text(inline(heading)).font(.headline).padding(.top, 6)
    } else if let (checked, body) = checkboxBody(trimmed) {
      HStack(alignment: .firstTextBaseline, spacing: 6) {
        Image(systemName: checked ? "checkmark.square" : "square")
          .foregroundStyle(.secondary)
        Text(inline(body))
      }
    } else if let bullet = bulletBody(trimmed) {
      HStack(alignment: .firstTextBaseline, spacing: 6) {
        Text("•").foregroundStyle(.secondary)
        Text(inline(bullet))
      }
    } else {
      Text(inline(text))
    }
  }

  private func headingBody(_ s: String) -> String? {
    guard s.hasPrefix("#") else { return nil }
    return String(s.drop(while: { $0 == "#" })).trimmingCharacters(in: .whitespaces)
  }

  private func checkboxBody(_ s: String) -> (Bool, String)? {
    for prefix in ["- [ ] ", "- [x] ", "- [X] ", "* [ ] ", "* [x] "] {
      if s.hasPrefix(prefix) {
        return (prefix.lowercased().contains("[x]"), String(s.dropFirst(prefix.count)))
      }
    }
    return nil
  }

  private func bulletBody(_ s: String) -> String? {
    for prefix in ["- ", "* "] where s.hasPrefix(prefix) {
      return String(s.dropFirst(prefix.count))
    }
    return nil
  }

  /// Inline styling (**bold**, _italic_) via AttributedString; plain text on failure.
  private func inline(_ text: String) -> AttributedString {
    (try? AttributedString(
      markdown: text,
      options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
      ?? AttributedString(text)
  }
}
