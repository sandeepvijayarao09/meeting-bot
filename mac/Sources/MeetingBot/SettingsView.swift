import AppKit
import Foundation
import SwiftUI

/// Reads/writes the bits of configuration the app can own on the user's behalf:
/// the NVIDIA key (in ~/.config/meetingbot/.env) and Google connection state.
@MainActor
final class SettingsModel: ObservableObject {
  @Published var nvidiaKey = ""
  @Published var googleConnected = false
  @Published var status = ""
  /// nil until the first check comes back, so the UI can stay quiet instead of
  /// flashing "not downloaded" at someone who has had the model for months.
  @Published var modelPresent: Bool?
  @Published var modelBytes: Int64?
  @Published var modelDownloading = false
  @Published var modelStatus = ""

  private var configDir: URL {
    FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/meetingbot")
  }
  private var envFile: URL { configDir.appendingPathComponent(".env") }
  private var googleToken: URL { configDir.appendingPathComponent("google_token.json") }

  func refresh() {
    nvidiaKey = readEnv("NVIDIA_API_KEY") ?? ""
    googleConnected = FileManager.default.fileExists(atPath: googleToken.path)
  }

  // MARK: - NVIDIA key

  func saveNvidiaKey() {
    upsertEnv("NVIDIA_API_KEY", nvidiaKey.trimmingCharacters(in: .whitespacesAndNewlines))
    status = nvidiaKey.isEmpty ? "Key cleared." : "Key saved. Summaries & Ask are enabled."
  }

  private func readEnv(_ key: String) -> String? {
    guard let text = try? String(contentsOf: envFile, encoding: .utf8) else { return nil }
    for line in text.components(separatedBy: "\n") where line.hasPrefix("\(key)=") {
      return String(line.dropFirst(key.count + 1)).trimmingCharacters(in: .whitespaces)
    }
    return nil
  }

  /// Insert or replace `key=value`, preserving any other lines in the file.
  private func upsertEnv(_ key: String, _ value: String) {
    try? FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
    var lines =
      (try? String(contentsOf: envFile, encoding: .utf8))?
      .components(separatedBy: "\n").filter { !$0.isEmpty } ?? []
    lines.removeAll { $0.hasPrefix("\(key)=") }
    if !value.isEmpty { lines.append("\(key)=\(value)") }
    try? (lines.joined(separator: "\n") + "\n").write(
      to: envFile, atomically: true, encoding: .utf8)
  }

  // MARK: - Google

  func connectGoogle() {
    guard let mbot = Paths.mbotExecutable() else {
      status = "Pipeline not found — run scripts/install-macos.sh."
      return
    }
    status = "Opening Google sign-in…"
    Task.detached {
      let process = Process()
      process.executableURL = mbot
      process.arguments = ["auth-google"]
      let pipe = Pipe()
      process.standardOutput = pipe
      process.standardError = pipe
      try? process.run()
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      process.waitUntilExit()
      let ok = process.terminationStatus == 0
      let message =
        ok
        ? "Google connected. Notes can now export to Google Docs."
        : (String(data: data, encoding: .utf8) ?? "Google sign-in failed.")
          .trimmingCharacters(in: .whitespacesAndNewlines)
      await MainActor.run {
        self.status = message
        self.refresh()
      }
    }
  }

  func disconnectGoogle() {
    try? FileManager.default.removeItem(at: googleToken)
    refresh()
    status = "Google disconnected."
  }

  // MARK: - Speech model

  /// Ask the pipeline whether the Whisper model is cached. Cheap (a cache stat, no
  /// network), so it is safe to call whenever Settings appears.
  func refreshModel() {
    guard let mbot = Paths.mbotExecutable() else { return }
    Task.detached {
      let process = Process()
      process.executableURL = mbot
      process.arguments = ["download-model", "--check"]
      let pipe = Pipe()
      process.standardOutput = pipe
      process.standardError = Pipe()
      try? process.run()
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      process.waitUntilExit()
      let present = process.terminationStatus == 0
      // "present <bytes>" — show the real size rather than the ~1.5 GB estimate.
      let bytes = String(data: data, encoding: .utf8)?
        .split(separator: " ").last
        .flatMap { Int64($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
      await MainActor.run {
        self.modelPresent = present
        self.modelBytes = present ? bytes : nil
      }
    }
  }

  /// One-click fetch. Resumable, so a failure here is worth retrying rather than
  /// starting over; the button simply becomes available again.
  func downloadModel() {
    guard let mbot = Paths.mbotExecutable() else {
      modelStatus = "Pipeline not found — run scripts/install-macos.sh."
      return
    }
    modelDownloading = true
    modelStatus = "Downloading… this runs once and can take a few minutes."
    Task.detached {
      let process = Process()
      process.executableURL = mbot
      process.arguments = ["download-model"]
      let pipe = Pipe()
      process.standardOutput = pipe
      process.standardError = pipe
      try? process.run()
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      process.waitUntilExit()
      let ok = process.terminationStatus == 0
      let message =
        ok
        ? "Speech model ready. Recordings transcribe immediately from now on."
        : (String(data: data, encoding: .utf8) ?? "Download failed.")
          .trimmingCharacters(in: .whitespacesAndNewlines)
          .components(separatedBy: "\n").last ?? "Download failed."
      await MainActor.run {
        self.modelDownloading = false
        self.modelStatus = message
        self.refreshModel()
      }
    }
  }
}

struct SettingsView: View {
  @ObservedObject var controller: RecordingController
  @StateObject private var access = AccessModel()
  @StateObject private var model = SettingsModel()

  var body: some View {
    TabView {
      generalTab.tabItem { Label("General", systemImage: "gearshape") }
      accessTab.tabItem { Label("Access", systemImage: "lock.shield") }
    }
    .frame(width: 460, height: 360)
    .onAppear {
      access.refresh()
      model.refresh()
      model.refreshModel()
    }
  }

  /// The model is not shipped inside the app — bundling it would add ~1.5 GB to every
  /// download, including for people who never record. Offering it here means the
  /// fetch happens once, deliberately, instead of silently during a first meeting.
  private var modelRow: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack {
        VStack(alignment: .leading) {
          Text("On-device transcription")
          Text(modelSubtitle).font(.caption).foregroundStyle(.secondary)
        }
        Spacer()
        if model.modelDownloading {
          ProgressView().controlSize(.small)
        } else if model.modelPresent == false {
          Button("Download") { model.downloadModel() }
            .buttonStyle(.borderedProminent)
        } else if model.modelPresent == true {
          Text("Ready").font(.caption).foregroundStyle(.secondary)
        }
      }
      if !model.modelStatus.isEmpty {
        Text(model.modelStatus).font(.caption).foregroundStyle(.secondary)
      }
    }
  }

  private var modelSubtitle: String {
    if model.modelDownloading { return "Downloading once — you can close this window." }
    switch model.modelPresent {
    case .some(true):
      if let bytes = model.modelBytes, bytes > 0 {
        let gb = Double(bytes) / 1_000_000_000
        return String(format: "Cached on this Mac (%.1f GB)", gb)
      }
      return "Cached on this Mac"
    case .some(false):
      return "One-time ~1.5 GB download. Needed before the first recording."
    case .none:
      return "Checking…"
    }
  }

  // MARK: - General (saving + integrations)

  private var generalTab: some View {
    Form {
      Section("Meeting") {
        Picker("Template", selection: $controller.template) {
          ForEach(RecordingController.templates, id: \.id) { t in
            Text(t.label).tag(t.id)
          }
        }
        Text("Shapes the summary for the meeting type (standup, 1:1, interview, sales).")
          .font(.caption).foregroundStyle(.secondary)
      }

      Section("Saving") {
        Picker("Save notes to", selection: $controller.destination) {
          ForEach(RecordingController.destinations, id: \.id) { dest in
            Text(dest.label).tag(dest.id)
          }
        }
        Text("A Markdown copy is always kept locally so search and the Meetings window work.")
          .font(.caption).foregroundStyle(.secondary)
      }

      Section("Speech model") {
        modelRow
      }

      Section("Summaries & Ask (NVIDIA NIM)") {
        SecureField("API key (nvapi-…)", text: $model.nvidiaKey)
        HStack {
          Button("Save Key") { model.saveNvidiaKey() }
          Link("Get a free key", destination: URL(string: "https://build.nvidia.com")!)
            .font(.caption)
        }
      }

      Section("Google Docs") {
        if model.googleConnected {
          HStack {
            Label("Connected", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
            Spacer()
            Button("Disconnect") { model.disconnectGoogle() }
          }
        } else {
          Button("Connect Google…") { model.connectGoogle() }
        }
      }

      if !model.status.isEmpty {
        Text(model.status).font(.caption).foregroundStyle(.secondary)
      }
    }
    .formStyle(.grouped)
  }

  // MARK: - Access (permissions)

  private var accessTab: some View {
    Form {
      Section("Permissions") {
        accessRow(
          "Microphone", "Record your side of the meeting", access.microphone,
          request: access.requestMicrophone, pane: "Privacy_Microphone")
        accessRow(
          "Screen & System Audio", "Capture what other people say", access.screenRecording,
          request: access.requestScreenRecording, pane: "Privacy_ScreenCapture")
        accessRow(
          "Calendar", "Name notes from your meeting (optional)", access.calendar,
          request: access.requestCalendar, pane: "Privacy_Calendars")
      }
      Text("Meeting Bot is local-first: audio is transcribed on your Mac and never uploaded.")
        .font(.caption).foregroundStyle(.secondary)
      Button("Re-check") { access.refresh() }
    }
    .formStyle(.grouped)
  }

  @ViewBuilder private func accessRow(
    _ title: String, _ subtitle: String, _ status: AccessModel.Status,
    request: @escaping () -> Void, pane: String
  ) -> some View {
    HStack {
      VStack(alignment: .leading) {
        Text(title)
        Text(subtitle).font(.caption).foregroundStyle(.secondary)
      }
      Spacer()
      Circle().fill(status.color).frame(width: 8, height: 8)
      Text(status.label).font(.caption).foregroundStyle(.secondary)
      switch status {
      case .notDetermined:
        Button("Grant", action: request)
      case .denied:
        Button("Open Settings") { access.openSettings(pane) }
      case .granted:
        EmptyView()
      }
    }
  }
}
