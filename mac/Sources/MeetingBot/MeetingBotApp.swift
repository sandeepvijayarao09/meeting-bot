import AppKit
import SwiftUI

@main
struct MeetingBotApp: App {
  @StateObject private var controller = RecordingController()

  var body: some Scene {
    MenuBarExtra {
      MenuContent(controller: controller)
    } label: {
      Label("Meeting Bot", systemImage: controller.isRecording ? "record.circle.fill" : "mic")
        .help(controller.isRecording ? "Recording \(controller.elapsedString)" : "Meeting Bot")
    }
    .menuBarExtraStyle(.menu)
  }
}

struct MenuContent: View {
  @ObservedObject var controller: RecordingController

  var body: some View {
    Group {
      statusRow

      Button(action: controller.toggle) {
        Text(toggleTitle)
      }
      .disabled(controller.state == .processing)

      Divider()

      Button("Open Last Note") {
        if let path = controller.lastNotePath {
          NSWorkspace.shared.open(URL(fileURLWithPath: path))
        }
      }
      .disabled(controller.lastNotePath == nil)

      Button("Open Notes Folder") {
        let notes = FileManager.default.homeDirectoryForCurrentUser
          .appendingPathComponent(".local/share/meetingbot")
        NSWorkspace.shared.open(notes)
      }

      Divider()

      Button("Quit Meeting Bot") { NSApplication.shared.terminate(nil) }
        .keyboardShortcut("q")
    }
  }

  @ViewBuilder private var statusRow: some View {
    switch controller.state {
    case .idle:
      Text("Idle").foregroundStyle(.secondary)
    case .recording:
      Text("● Recording — \(controller.elapsedString)").foregroundStyle(.red)
    case .processing:
      Text("Transcribing & summarizing…").foregroundStyle(.secondary)
    case .error(let message):
      Text("Error: \(message)").foregroundStyle(.red)
    }
  }

  private var toggleTitle: String {
    switch controller.state {
    case .recording: return "Stop & Make Note"
    case .processing: return "Working…"
    default: return "Start Recording"
    }
  }
}
