import AVFoundation
import Foundation

/// Resamples incoming audio to 16 kHz mono and writes it as chunked WAV files.
///
/// Each chunk is registered in the manifest when it closes, with start/end
/// offsets derived from the running frame count (sample-accurate, immune to
/// wall-clock drift). All work happens on a private serial queue so capture
/// callbacks return immediately.
final class StreamWriter {
  static let sampleRate = 16000.0

  private let stream: String
  private let directory: URL
  private let chunkFrames: Int64
  private let manifest: Manifest
  private let queue: DispatchQueue
  private let outputFormat: AVAudioFormat
  private var converter: AVAudioConverter?
  private var inputFormat: AVAudioFormat?
  private var file: AVAudioFile?
  private var currentFileName = ""
  private var chunkIndex = 0
  private var framesInChunk: Int64 = 0
  private var totalFrames: Int64 = 0

  init(stream: String, directory: URL, chunkSeconds: Int, manifest: Manifest) {
    guard
      let format = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
        sampleRate: Self.sampleRate,
        channels: 1,
        interleaved: false)
    else {
      preconditionFailure("16 kHz mono Float32 is always a valid AVAudioFormat")
    }
    self.outputFormat = format
    self.stream = stream
    self.directory = directory
    self.chunkFrames = Int64(chunkSeconds) * Int64(Self.sampleRate)
    self.manifest = manifest
    self.queue = DispatchQueue(label: "capturekit.writer.\(stream)")
  }

  /// Enqueues a buffer in any format; safe to call from capture callbacks.
  func append(_ buffer: AVAudioPCMBuffer) {
    queue.async { self.process(buffer) }
  }

  /// Flushes the current partial chunk. Call once when capture has stopped.
  func finish() {
    queue.sync { self.closeChunk() }
  }

  // MARK: - Private

  private func process(_ inputBuffer: AVAudioPCMBuffer) {
    guard inputBuffer.frameLength > 0 else { return }
    // (Re)build the converter when the input format changes mid-session — e.g. a route
    // change (AirPods connect) swaps the mic's sample rate. A converter cached against
    // the old format would fail every subsequent buffer and silently drop the audio.
    if inputFormat == nil || !inputFormat!.isEqual(inputBuffer.format) {
      converter = AVAudioConverter(from: inputBuffer.format, to: outputFormat)
      inputFormat = inputBuffer.format
    }
    guard let converter else {
      logError("\(stream): no converter for format \(inputBuffer.format)")
      return
    }
    let ratio = outputFormat.sampleRate / inputBuffer.format.sampleRate
    let capacity = AVAudioFrameCount(Double(inputBuffer.frameLength) * ratio) + 64
    guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity)
    else { return }

    var supplied = false
    var conversionError: NSError?
    let status = converter.convert(to: outputBuffer, error: &conversionError) { _, outStatus in
      if supplied {
        outStatus.pointee = .noDataNow
        return nil
      }
      supplied = true
      outStatus.pointee = .haveData
      return inputBuffer
    }
    if status == .error {
      logError("\(stream): convert error: \(conversionError?.localizedDescription ?? "unknown")")
      return
    }
    guard outputBuffer.frameLength > 0 else { return }
    write(outputBuffer)
  }

  private func write(_ buffer: AVAudioPCMBuffer) {
    if file == nil { openChunk() }
    guard let file else { return }
    do {
      try file.write(from: buffer)
    } catch {
      logError("\(stream): write failed: \(error.localizedDescription)")
      return
    }
    framesInChunk += Int64(buffer.frameLength)
    totalFrames += Int64(buffer.frameLength)
    if framesInChunk >= chunkFrames { closeChunk() }
  }

  private func openChunk() {
    chunkIndex += 1
    currentFileName = String(format: "%@-%04d.wav", stream, chunkIndex)
    let url = directory.appendingPathComponent(currentFileName)
    let settings: [String: Any] = [
      AVFormatIDKey: kAudioFormatLinearPCM,
      AVSampleRateKey: Self.sampleRate,
      AVNumberOfChannelsKey: 1,
      AVLinearPCMBitDepthKey: 16,
      AVLinearPCMIsFloatKey: false,
      AVLinearPCMIsBigEndianKey: false,
    ]
    do {
      file = try AVAudioFile(
        forWriting: url,
        settings: settings,
        commonFormat: .pcmFormatFloat32,
        interleaved: false)
      framesInChunk = 0
    } catch {
      logError("\(stream): cannot open \(currentFileName): \(error.localizedDescription)")
      file = nil
    }
  }

  private func closeChunk() {
    guard file != nil else { return }
    file = nil  // AVAudioFile flushes and closes on release
    guard framesInChunk > 0 else { return }
    let end = Double(totalFrames) / Self.sampleRate
    let start = Double(totalFrames - framesInChunk) / Self.sampleRate
    manifest.append(stream: stream, file: currentFileName, start: start, end: end)
    framesInChunk = 0
  }
}
