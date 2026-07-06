import AVFoundation

/// Captures the default microphone via AVAudioEngine ("me" in the transcript).
///
/// On iOS the engine is stopped by the system during interruptions (phone calls,
/// Siri) and can be torn down by route changes (unplugging headphones). Left
/// unhandled, the tail of a meeting is silently lost — so we observe those events
/// and restart capture, reporting a hard failure via `onError`.
final class MicCapture {
  private let engine = AVAudioEngine()
  private let writer: StreamWriter

  /// Reports a capture failure we could not recover from (e.g. the engine refused
  /// to restart after an interruption). macOS leaves this unused.
  var onError: ((Error) -> Void)?

  #if os(iOS)
    private var observers: [NSObjectProtocol] = []
  #endif

  init(writer: StreamWriter) {
    self.writer = writer
  }

  func start() throws {
    installTap()
    try engine.start()
    #if os(iOS)
      observeInterruptions()
    #endif
  }

  func stop() {
    #if os(iOS)
      observers.forEach(NotificationCenter.default.removeObserver)
      observers.removeAll()
    #endif
    engine.inputNode.removeTap(onBus: 0)
    engine.stop()
  }

  private func installTap() {
    let input = engine.inputNode
    let format = input.outputFormat(forBus: 0)
    input.installTap(onBus: 0, bufferSize: 4800, format: format) { [writer] buffer, _ in
      writer.append(buffer)
    }
  }

  #if os(iOS)
    private func observeInterruptions() {
      let center = NotificationCenter.default
      // Phone call / Siri: the system stops our engine; resume when it says we may.
      observers.append(
        center.addObserver(
          forName: AVAudioSession.interruptionNotification, object: nil, queue: .main
        ) { [weak self] note in
          guard
            let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
            AVAudioSession.InterruptionType(rawValue: raw) == .ended
          else { return }
          let opts = AVAudioSession.InterruptionOptions(
            rawValue: note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0)
          if opts.contains(.shouldResume) { self?.restart() }
        })
      // Route change (e.g. headphones unplugged) can stop the engine too.
      observers.append(
        center.addObserver(
          forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
        ) { [weak self] _ in self?.restart() })
    }

    /// Reactivate the session and restart the engine after an interruption or route
    /// change. Reinstall the tap so it binds to the current input format — a route
    /// change (e.g. AirPods connect) can change the mic's sample rate, and restarting
    /// with a tap bound to the old format crashes AVAudioEngine on start().
    private func restart() {
      guard !engine.isRunning else { return }
      do {
        engine.inputNode.removeTap(onBus: 0)
        installTap()
        try AVAudioSession.sharedInstance().setActive(true)
        try engine.start()
      } catch {
        onError?(error)
      }
    }
  #endif
}
