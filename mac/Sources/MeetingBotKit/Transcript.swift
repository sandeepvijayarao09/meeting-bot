import Foundation

/// One transcribed ASR segment, before merging. `speaker` is the raw stream
/// ("mic" / "sys"), matching the on-disk transcript and the Python pipeline.
public struct Segment: Equatable, Sendable {
  public var start: Double
  public var end: Double
  public var speaker: String
  public var text: String

  public init(start: Double, end: Double, speaker: String, text: String) {
    self.start = start
    self.end = end
    self.speaker = speaker
    self.text = text
  }
}

/// A coalesced speaker turn with a display label ("Me" / "Them").
public struct Turn: Equatable, Sendable {
  public var speaker: String
  public var start: Double
  public var end: Double
  public var text: String

  public init(speaker: String, start: Double, end: Double, text: String) {
    self.speaker = speaker
    self.start = start
    self.end = end
    self.text = text
  }
}

/// Pure transcript shaping — a Swift port of the merge/format logic in
/// `meetingbot/transcribe.py` (`merge_turns`, `format_transcript`).
public enum Transcript {
  /// "mic" -> "Me", "sys" -> "Them"; any other stream label passes through.
  static let labels = ["mic": "Me", "sys": "Them"]

  /// Sort segments from all streams by time and coalesce them into speaker turns,
  /// merging same-speaker segments separated by <= `maxGap` seconds.
  public static func mergeTurns(_ segments: [Segment], maxGap: Double = 2.0) -> [Turn] {
    let ordered = dedupe(segments.sorted { $0.start < $1.start })
    var turns: [Turn] = []
    for seg in ordered {
      let speaker = labels[seg.speaker] ?? seg.speaker
      if var last = turns.last, last.speaker == speaker, seg.start - last.end <= maxGap {
        last.text += " " + seg.text
        last.end = seg.end
        turns[turns.count - 1] = last
      } else {
        turns.append(Turn(speaker: speaker, start: seg.start, end: seg.end, text: seg.text))
      }
    }
    return turns
  }

  public static func formatTranscript(_ turns: [Turn]) -> String {
    turns
      .map { "**\($0.speaker)** [\(timestamp($0.start))]: \($0.text)" }
      .joined(separator: "\n\n")
  }

  // MARK: - Private

  /// Drop consecutive same-speaker segments with identical text — chunk-boundary
  /// echoes from feeding prior text as the ASR's context prompt.
  private static func dedupe(_ ordered: [Segment]) -> [Segment] {
    var out: [Segment] = []
    var last: [String: String] = [:]
    for seg in ordered {
      let norm = seg.text.lowercased().split(separator: " ").joined(separator: " ")
      if !norm.isEmpty, last[seg.speaker] == norm { continue }
      last[seg.speaker] = norm
      out.append(seg)
    }
    return out
  }

  private static func timestamp(_ seconds: Double) -> String {
    let s = Int(seconds)
    if s >= 3600 {
      return String(format: "%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60)
    }
    return String(format: "%02d:%02d", s / 60, s % 60)
  }
}
