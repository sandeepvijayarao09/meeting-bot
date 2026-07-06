import SwiftUI

struct ContentView: View {
  var body: some View {
    TabView {
      RecordView()
        .tabItem { Label("Record", systemImage: "mic.circle") }
      NotesView()
        .tabItem { Label("Notes", systemImage: "note.text") }
      SettingsView()
        .tabItem { Label("Settings", systemImage: "gearshape") }
    }
  }
}

struct RecordView: View {
  @StateObject private var controller = RecordingController()
  @EnvironmentObject private var secrets: Secrets

  var body: some View {
    NavigationStack {
      VStack(spacing: 28) {
        Spacer()
        Text(timeString(controller.elapsed))
          .font(.system(size: 48, weight: .semibold, design: .monospaced))
          .monospacedDigit()
        actionButton
        if !controller.statusMessage.isEmpty {
          Text(controller.statusMessage)
            .font(.footnote)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
        }
        Spacer()
        Text(
          secrets.nimKey.isEmpty
            ? "On-device transcription · summary off (add a key in Settings)"
            : "On-device transcription · cloud summary"
        )
        .font(.caption)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
      }
      .padding()
      .navigationTitle("MB")
    }
  }

  @ViewBuilder private var actionButton: some View {
    switch controller.phase {
    case .idle:
      Button {
        Task { await controller.start() }
      } label: {
        pillLabel("Start Recording", systemImage: "record.circle")
      }
    case .recording:
      Button {
        Task { await controller.stop(apiKey: secrets.nimKey) }
      } label: {
        pillLabel("Stop", systemImage: "stop.circle")
      }
    case .processing:
      HStack(spacing: 10) {
        ProgressView()
        Text("Processing…")
      }
      .font(.title3)
    }
  }

  private func pillLabel(_ title: String, systemImage: String) -> some View {
    Label(title, systemImage: systemImage)
      .font(.title2.bold())
      .foregroundStyle(.white)
      .padding(.vertical, 14)
      .frame(maxWidth: .infinity)
      .background(.red, in: Capsule())
      .padding(.horizontal, 32)
  }

  private func timeString(_ seconds: TimeInterval) -> String {
    let total = Int(seconds)
    return String(format: "%02d:%02d", total / 60, total % 60)
  }
}

struct SettingsView: View {
  @EnvironmentObject private var secrets: Secrets

  var body: some View {
    NavigationStack {
      Form {
        Section("Summaries (cloud fallback)") {
          SecureField("NVIDIA NIM API key", text: $secrets.nimKey)
          Text(
            "Used only when on-device Gemma isn't available. Transcript text only — audio never "
              + "leaves your device. Free key at build.nvidia.com."
          )
          .font(.caption)
          .foregroundStyle(.secondary)
        }
        Section("On-device model (Gemma 4 E4B)") {
          LabeledContent("Status", value: "Not installed")
          Text(
            "On-device summarization with Gemma 4 E4B arrives in a later update — it needs a "
              + "high-RAM iPhone and a one-time ~3–4 GB model download."
          )
          .font(.caption)
          .foregroundStyle(.secondary)
        }
        Section("About") {
          LabeledContent("Capture", value: "Microphone")
          Text(
            "MB records the mic for in-person meetings and speakerphone calls. iOS can't capture "
              + "other apps' audio — use the Mac app or Chrome extension for virtual calls."
          )
          .font(.caption)
          .foregroundStyle(.secondary)
        }
      }
      .navigationTitle("Settings")
    }
  }
}
