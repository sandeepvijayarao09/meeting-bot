import AppKit
import CoreAudio
import Foundation

/// Detects when a meeting likely starts by watching whether any app is using the
/// microphone (a universal signal — works for Zoom, Meet in a browser, Teams, etc.),
/// optionally enriched with the name of a running meeting app.
///
/// Polls on a timer while the recorder is idle and fires `onMeetingLikelyStarted`
/// once per call (debounced until the mic goes idle again).
@MainActor
final class MeetingDetector {
  /// Called with a human-readable reason, e.g. "Zoom is using your microphone".
  var onMeetingLikelyStarted: ((String) -> Void)?

  private var timer: Timer?
  private var wasActive = false

  private static let meetingApps: [String: String] = [
    "us.zoom.xos": "Zoom",
    "com.microsoft.teams2": "Teams",
    "com.microsoft.teams": "Teams",
    "com.cisco.webexmeetingsapp": "Webex",
    "com.google.Chrome": "a browser meeting",
    "com.apple.Safari": "a browser meeting",
    "com.hnc.Discord": "Discord",
  ]

  func start() {
    guard timer == nil else { return }
    timer = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.poll() }
    }
  }

  func stop() {
    timer?.invalidate()
    timer = nil
    wasActive = false
  }

  private func poll() {
    let active = Self.micInUse()
    defer { wasActive = active }
    guard active, !wasActive else { return }  // rising edge only
    onMeetingLikelyStarted?(reason())
  }

  private func reason() -> String {
    let running = NSWorkspace.shared.runningApplications
    for app in running {
      if let id = app.bundleIdentifier, let name = Self.meetingApps[id] {
        return "\(name) is using your microphone"
      }
    }
    return "an app is using your microphone"
  }

  /// True if any process is currently using the default input device.
  static func micInUse() -> Bool {
    guard let device = defaultInputDevice() else { return false }
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var running: UInt32 = 0
    var size = UInt32(MemoryLayout<UInt32>.size)
    let status = AudioObjectGetPropertyData(device, &address, 0, nil, &size, &running)
    return status == noErr && running != 0
  }

  private static func defaultInputDevice() -> AudioObjectID? {
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDefaultInputDevice,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
    var device = AudioObjectID(0)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    let status = AudioObjectGetPropertyData(
      AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device)
    return status == noErr ? device : nil
  }
}
