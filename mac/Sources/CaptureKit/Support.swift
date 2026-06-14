import Foundation

/// Writes a diagnostic line to stderr. Capture code uses this for non-fatal notes;
/// fatal stream errors are surfaced through `SessionRecorder.onError` instead.
func logError(_ message: String) {
  FileHandle.standardError.write(Data((message + "\n").utf8))
}

/// An error originating in the capture pipeline.
public struct CaptureError: Error, CustomStringConvertible {
  public let description: String
  public init(_ description: String) { self.description = description }
}
