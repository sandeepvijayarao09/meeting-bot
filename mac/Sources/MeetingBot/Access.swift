import AVFoundation
import AppKit
import CoreGraphics
import EventKit
import SwiftUI

/// Tracks and controls the app's access to system resources (the "access control"
/// surface): Microphone, Screen Recording, and Calendar. Each can be granted, or
/// the user is sent to the right System Settings pane when macOS requires it.
@MainActor
final class AccessModel: ObservableObject {
  enum Status {
    case granted
    case denied
    case notDetermined

    var label: String {
      switch self {
      case .granted: return "Granted"
      case .denied: return "Denied"
      case .notDetermined: return "Not requested"
      }
    }

    var color: Color {
      switch self {
      case .granted: return .green
      case .denied: return .red
      case .notDetermined: return .orange
      }
    }
  }

  @Published var microphone: Status = .notDetermined
  @Published var screenRecording: Status = .notDetermined
  @Published var calendar: Status = .notDetermined

  private let eventStore = EKEventStore()

  func refresh() {
    microphone = micStatus()
    screenRecording = CGPreflightScreenCaptureAccess() ? .granted : .notDetermined
    calendar = calendarStatus()
  }

  // MARK: - Microphone

  private func micStatus() -> Status {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized: return .granted
    case .denied, .restricted: return .denied
    default: return .notDetermined
    }
  }

  func requestMicrophone() {
    AVCaptureDevice.requestAccess(for: .audio) { _ in
      Task { @MainActor in self.refresh() }
    }
  }

  // MARK: - Screen Recording

  func requestScreenRecording() {
    // Prompts on first call; subsequent calls no-op if already decided, so we
    // also offer "Open Settings" for the denied case.
    _ = CGRequestScreenCaptureAccess()
    refresh()
  }

  // MARK: - Calendar

  private func calendarStatus() -> Status {
    switch EKEventStore.authorizationStatus(for: .event) {
    case .fullAccess, .authorized: return .granted
    case .denied, .restricted: return .denied
    default: return .notDetermined
    }
  }

  func requestCalendar() {
    Task {
      _ = try? await eventStore.requestFullAccessToEvents()
      refresh()
    }
  }

  // MARK: - System Settings deep links

  func openSettings(_ pane: String) {
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)") {
      NSWorkspace.shared.open(url)
    }
  }
}
