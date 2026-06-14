// audiocap — capture microphone + system audio into chunked 16 kHz mono WAVs.
//
// Usage: audiocap <session-dir> [--chunk-seconds N]
//
// Emits JSON events on stdout ({"event": "started"|"stopped"|"error", ...}).
// Stops cleanly on SIGINT/SIGTERM, flushing partial chunks. Thin CLI wrapper
// around CaptureKit.SessionRecorder (shared with the MeetingBot app).

import CaptureKit
import Foundation

func emit(_ object: [String: Any]) {
  guard let data = try? JSONSerialization.data(withJSONObject: object),
    let line = String(data: data, encoding: .utf8)
  else { return }
  print(line)
  fflush(stdout)
}

func fail(_ message: String, code: Int32) -> Never {
  emit(["event": "error", "message": message])
  exit(code)
}

// MARK: - Argument parsing

var sessionPath: String?
var chunkSeconds = 30
var arguments = CommandLine.arguments.dropFirst().makeIterator()
while let argument = arguments.next() {
  switch argument {
  case "--chunk-seconds":
    guard let value = arguments.next(), let parsed = Int(value), parsed > 0 else {
      fail("--chunk-seconds requires a positive integer", code: 64)
    }
    chunkSeconds = parsed
  case "-h", "--help":
    print("usage: audiocap <session-dir> [--chunk-seconds N]")
    exit(0)
  default:
    guard sessionPath == nil else { fail("unexpected argument: \(argument)", code: 64) }
    sessionPath = argument
  }
}
guard let sessionPath else {
  fail("usage: audiocap <session-dir> [--chunk-seconds N]", code: 64)
}

let sessionURL = URL(fileURLWithPath: sessionPath)

let recorder: SessionRecorder
do {
  recorder = try SessionRecorder(sessionDirectory: sessionURL, chunkSeconds: chunkSeconds)
} catch {
  fail("cannot start session: \(error.localizedDescription)", code: 1)
}
recorder.onError = { error in
  fail("system audio capture stopped: \(error.localizedDescription)", code: 1)
}

// MARK: - Graceful shutdown

var isShuttingDown = false
func shutdown() {
  guard !isShuttingDown else { return }
  isShuttingDown = true
  Task {
    await recorder.stop()
    emit(["event": "stopped"])
    exit(0)
  }
}

signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let interruptSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
interruptSource.setEventHandler { shutdown() }
interruptSource.resume()
let terminateSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
terminateSource.setEventHandler { shutdown() }
terminateSource.resume()

// MARK: - Start

Task {
  do {
    try await recorder.start()
  } catch {
    let message = (error as? CaptureError)?.description ?? error.localizedDescription
    fail(message, code: 2)
  }
  emit(["event": "started", "session": sessionURL.path])
}

dispatchMain()
