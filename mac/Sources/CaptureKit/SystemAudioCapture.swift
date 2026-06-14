import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

/// Captures system audio via ScreenCaptureKit ("them" in the transcript).
///
/// Audio-only: no video output is attached, and the mandatory video leg of the
/// stream is configured down to its cheapest settings. Requires the Screen
/// Recording permission. A mid-session stream failure is reported via `onStop`.
final class SystemAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
  private let writer: StreamWriter
  private var stream: SCStream?
  private let sampleQueue = DispatchQueue(label: "capturekit.sck")

  /// Called if the stream stops unexpectedly (e.g. permission revoked).
  var onStop: ((Error) -> Void)?

  init(writer: StreamWriter) {
    self.writer = writer
  }

  func start() async throws {
    let content = try await SCShareableContent.excludingDesktopWindows(
      false, onScreenWindowsOnly: false)
    guard let display = content.displays.first else {
      throw CaptureError("no display found")
    }
    let filter = SCContentFilter(display: display, excludingWindows: [])
    let configuration = SCStreamConfiguration()
    configuration.capturesAudio = true
    configuration.excludesCurrentProcessAudio = true
    configuration.sampleRate = 48000
    configuration.channelCount = 2
    configuration.width = 2
    configuration.height = 2
    configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)

    let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
    try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: sampleQueue)
    try await stream.startCapture()
    self.stream = stream
  }

  func stop() async {
    guard let stream else { return }
    self.stream = nil
    try? await stream.stopCapture()
  }

  // MARK: - SCStreamOutput

  func stream(
    _ stream: SCStream,
    didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
    of type: SCStreamOutputType
  ) {
    guard type == .audio, sampleBuffer.isValid,
      let buffer = sampleBuffer.asPCMBuffer
    else { return }
    writer.append(buffer)
  }

  // MARK: - SCStreamDelegate

  func stream(_ stream: SCStream, didStopWithError error: Error) {
    onStop?(error)
  }
}

extension CMSampleBuffer {
  /// Copies this buffer's PCM payload into an `AVAudioPCMBuffer`.
  var asPCMBuffer: AVAudioPCMBuffer? {
    guard let formatDescription = CMSampleBufferGetFormatDescription(self),
      let streamDescription = CMAudioFormatDescriptionGetStreamBasicDescription(
        formatDescription),
      let format = AVAudioFormat(streamDescription: streamDescription)
    else { return nil }
    let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(self))
    guard frames > 0,
      let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)
    else { return nil }
    buffer.frameLength = frames
    let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
      self, at: 0, frameCount: Int32(frames), into: buffer.mutableAudioBufferList)
    return status == noErr ? buffer : nil
  }
}
