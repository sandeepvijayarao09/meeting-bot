import EventKit
import Foundation

/// Reads the calendar to auto-name recordings from the meeting happening now.
/// Calendar access is requested lazily and only when auto-naming is used.
enum CalendarService {
  private static let store = EKEventStore()

  /// Title of an event occurring right now, if any and if access is granted.
  static func currentEventTitle() async -> String? {
    guard await requestAccess() else { return nil }
    let now = Date()
    // Look at a small window around "now" so we catch a meeting just starting.
    let predicate = store.predicateForEvents(
      withStart: now.addingTimeInterval(-5 * 60),
      end: now.addingTimeInterval(5 * 60),
      calendars: nil)
    let events = store.events(matching: predicate)
      .filter { !$0.isAllDay && ($0.title?.isEmpty == false) }
      .sorted { $0.startDate < $1.startDate }
    // Prefer an event currently in progress, else the next one starting soon.
    let ongoing = events.first { $0.startDate <= now && $0.endDate >= now }
    return (ongoing ?? events.first)?.title
  }

  private static func requestAccess() async -> Bool {
    // Deployment target is macOS 14, so full-access async API is always available.
    (try? await store.requestFullAccessToEvents()) ?? false
  }
}
