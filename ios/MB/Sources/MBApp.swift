import SwiftUI

/// MB for iOS — a local-first, mic-based meeting notetaker. Records the microphone
/// (in-person meetings, speakerphone calls), transcribes on-device, refines locally
/// (Eloquent-style), and summarizes via on-device Gemma (M2) or the NIM cloud (M1).
@main
struct MBApp: App {
  @StateObject private var secrets = Secrets()

  var body: some Scene {
    WindowGroup {
      ContentView()
        .environmentObject(secrets)
    }
  }
}
