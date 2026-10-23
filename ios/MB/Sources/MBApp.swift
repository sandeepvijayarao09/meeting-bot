import SwiftUI

/// MB for iOS — a local-first, mic-based meeting notetaker. Records the microphone
/// (in-person meetings, speakerphone calls), transcribes on-device, refines locally
/// (Eloquent-style), and summarizes via a Gemma endpoint. Unlike the Mac app, iOS
/// keeps the cloud backend: the on-device Gemma 4 build the Mac uses is ~5 GB,
/// which is not a reasonable download or memory footprint on most iPhones.
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
