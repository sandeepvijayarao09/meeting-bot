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

  /// Where Markdown notes are written. Mirrors the Python config resolution:
  /// MBOT_NOTES_DIR, else the dev project's `notes/`, else a data-dir fallback.
  static var notesDirectory: URL {
    let override = ProcessInfo.processInfo.environment["MBOT_NOTES_DIR"]
    if let override, !override.isEmpty {
      return URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
    }
    if let root = projectRoot() {
      return root.appendingPathComponent("notes")
    }
    return dataDirectory.appendingPathComponent("notes")
  }

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

  /// Opt-in: run the in-process native pipeline (MeetingBotKit) instead of the Python
  /// sidecar — the migration path toward a sandboxed Mac App Store build. Default off,
  /// so the shipping Python path is unchanged until the native path is validated.
  static var useNativePipeline: Bool {
    if let env = ProcessInfo.processInfo.environment["MBOT_NATIVE_PIPELINE"], !env.isEmpty {
      return env == "1" || env.lowercased() == "true"
    }
    return UserDefaults.standard.bool(forKey: "useNativePipeline")
  }

  /// The user's NVIDIA NIM key from ~/.config/meetingbot/.env (written by Settings),
  /// for the native pipeline's cloud summary. Phase C moves this into the container.
  static func nvidiaKey() -> String? {
    let envFile = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".config/meetingbot/.env")
    guard let text = try? String(contentsOf: envFile, encoding: .utf8) else { return nil }
    let prefix = "NVIDIA_API_KEY="
    for line in text.components(separatedBy: "\n") where line.hasPrefix(prefix) {
      var value = String(line.dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces)
      // Strip surrounding quotes, matching how python-dotenv reads the same file, so a
      // hand-edited `NVIDIA_API_KEY="nvapi-…"` doesn't send quotes to NIM (401).
      if value.count >= 2, let first = value.first, first == value.last,
        first == "\"" || first == "'"
      {
        value = String(value.dropFirst().dropLast())
      }
      return value.isEmpty ? nil : value
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
