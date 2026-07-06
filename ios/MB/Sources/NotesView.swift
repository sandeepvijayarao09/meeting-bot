import SwiftUI

struct NotesView: View {
  @State private var notes: [NoteFile] = []

  var body: some View {
    NavigationStack {
      Group {
        if notes.isEmpty {
          ContentUnavailableView(
            "No notes yet", systemImage: "note.text",
            description: Text("Record a meeting to create your first note."))
        } else {
          List(notes) { note in
            NavigationLink(value: note) {
              Text(note.title).lineLimit(1)
            }
          }
        }
      }
      .navigationTitle("Notes")
      .navigationDestination(for: NoteFile.self) { note in
        ScrollView {
          Text(note.body)
            .font(.system(.body, design: .monospaced))
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle(note.title)
        .navigationBarTitleDisplayMode(.inline)
      }
      .onAppear { notes = NotesIndex.list() }
      .refreshable { notes = NotesIndex.list() }
    }
  }
}
