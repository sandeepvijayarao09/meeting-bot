import Foundation

/// Appends one JSON line per closed audio chunk to `manifest.jsonl`.
///
/// Thread-safe: both stream writers append from their own queues.
final class Manifest {
  private let handle: FileHandle
  private let queue = DispatchQueue(label: "capturekit.manifest")

  init(url: URL) throws {
    FileManager.default.createFile(atPath: url.path, contents: nil)
    handle = try FileHandle(forWritingTo: url)
  }

  func append(stream: String, file: String, start: Double, end: Double) {
    queue.sync {
      let entry: [String: Any] = [
        "stream": stream,
        "file": file,
        "start": (start * 1000).rounded() / 1000,
        "end": (end * 1000).rounded() / 1000,
      ]
      guard let data = try? JSONSerialization.data(withJSONObject: entry) else { return }
      handle.write(data)
      handle.write(Data("\n".utf8))
    }
  }
}
