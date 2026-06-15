import AppKit
import SwiftUI

@main
struct MeetingBotApp: App {
  @StateObject private var controller = RecordingController()

  var body: some Scene {
    MenuBarExtra {
      MenuContent(controller: controller)
    } label: {
      MenuBarLabel(isRecording: controller.isRecording, elapsed: controller.elapsedString)
    }
    .menuBarExtraStyle(.menu)

    Window("Meetings", id: "notes") {
      NotesWindow()
    }
    .defaultSize(width: 860, height: 560)

    Settings {
      SettingsView(controller: controller)
    }
  }
}

/// The always-visible menu bar icon. Also honors MBOT_OPEN_NOTES=1 to open the
/// Meetings window at launch (used for verification/screenshots).
struct MenuBarLabel: View {
  let isRecording: Bool
  let elapsed: String
  @Environment(\.openWindow) private var openWindow
  @Environment(\.openSettings) private var openSettings

  var body: some View {
    Label("Meeting Bot", systemImage: isRecording ? "record.circle.fill" : "mic")
      .help(isRecording ? "Recording \(elapsed)" : "Meeting Bot")
      .onAppear {
        // Open the main window on launch so the app is visible and usable
        // (it also has a Dock icon now). The menu bar item remains for quick control.
        openWindow(id: "notes")
        NSApplication.shared.activate(ignoringOtherApps: true)
        if ProcessInfo.processInfo.environment["MBOT_OPEN_SETTINGS"] == "1" {
          openSettings()
        }
      }
  }
}

struct MenuContent: View {
  @ObservedObject var controller: RecordingController
  @Environment(\.openWindow) private var openWindow

  var body: some View {
    Group {
      statusRow

      Button(action: controller.toggle) {
        Text(toggleTitle)
      }
      .disabled(controller.state == .processing)

      Divider()

      Button("Meetings…") {
        openWindow(id: "notes")
        NSApplication.shared.activate(ignoringOtherApps: true)
      }
      .keyboardShortcut("m")

      Button("Open Last Note") {
        if let path = controller.lastNotePath {
          NSWorkspace.shared.open(URL(fileURLWithPath: path))
        }
      }
      .disabled(controller.lastNotePath == nil)

      Divider()

      Picker("Save notes to", selection: $controller.destination) {
        ForEach(RecordingController.destinations, id: \.id) { dest in
          Text(dest.label).tag(dest.id)
        }
      }

      Toggle("Auto-detect meetings", isOn: $controller.autoDetect)

      SettingsLink {
        Text("Settings…")
      }
      .keyboardShortcut(",")

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
