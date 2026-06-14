import AVFoundation

/// Captures the default microphone via AVAudioEngine ("me" in the transcript).
final class MicCapture {
  private let engine = AVAudioEngine()
  private let writer: StreamWriter

  init(writer: StreamWriter) {
    self.writer = writer
  }

  func start() throws {
    let input = engine.inputNode
    let format = input.outputFormat(forBus: 0)
    input.installTap(onBus: 0, bufferSize: 4800, format: format) { [writer] buffer, _ in
      writer.append(buffer)
    }
    try engine.start()
  }

  func stop() {
    engine.inputNode.removeTap(onBus: 0)
    engine.stop()
  }
}
