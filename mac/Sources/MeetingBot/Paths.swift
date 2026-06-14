import Foundation

/// Resolves where data lives and how to invoke the Python `mbot` pipeline.
///
/// The app captures audio natively (CaptureKit) and hands the finished session
/// to `mbot process <dir>` for local transcription, summarization, and export.
/// In a shipped bundle the `mbot` sidecar lives in Contents/Resources; during
/// development it falls back to the project venv.
enum Paths {
  static let dataDirectory: URL = {
    let override = ProcessInfo.processInfo.environment["MBOT_DATA_DIR"]
    if let override, !override.isEmpty {
      return URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
    }
    return FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".local/share/meetingbot")
  }()

  static var sessionsDirectory: URL { dataDirectory.appendingPathComponent("sessions") }

  /// The `mbot` executable: bundled sidecar first, then env override, then dev venv.
  static func mbotExecutable() -> URL? {
    if let bundled = Bundle.main.url(forResource: "mbot", withExtension: nil),
      FileManager.default.isExecutableFile(atPath: bundled.path)
    {
      return bundled
    }
    let env = ProcessInfo.processInfo.environment["MBOT_BIN"]
    if let env, FileManager.default.isExecutableFile(atPath: env) {
      return URL(fileURLWithPath: env)
    }
    let devVenv = projectRoot()?.appendingPathComponent(".venv/bin/mbot")
    if let devVenv, FileManager.default.isExecutableFile(atPath: devVenv.path) {
      return devVenv
    }
    // Installed CLI wrapper (scripts/install-macos.sh) — works from /Applications.
    let installed = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".local/bin/mbot")
    if FileManager.default.isExecutableFile(atPath: installed.path) {
      return installed
    }
    return nil
  }

  /// Best-effort project root when running from a dev build (…/mac/.build/…).
  private static func projectRoot() -> URL? {
    var url = URL(fileURLWithPath: Bundle.main.bundlePath)
    for _ in 0..<8 {
      if FileManager.default.fileExists(atPath: url.appendingPathComponent("pyproject.toml").path) {
        return url
      }
      url.deleteLastPathComponent()
    }
    return nil
  }
}
