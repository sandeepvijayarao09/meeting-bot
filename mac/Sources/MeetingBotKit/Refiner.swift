import Foundation

/// Eloquent-style on-device transcript cleanup — a faithful Swift port of the
/// Tier-1 rules in the Python `meetingbot/refine.py`.
///
/// Pure and deterministic: strips vocalized fillers and comma-delimited discourse
/// markers, collapses stutters and short false starts, fixes spacing/punctuation,
/// and capitalizes sentence starts. `cleanText` runs the steps to a fixpoint so it
/// is idempotent (`cleanText(cleanText(x)) == cleanText(x)`).
public enum Refiner {
  /// Safety cap on the fixpoint iteration; the steps only remove/normalize, so they
  /// converge in 1-2 passes. Mirrors `_MAX_PASSES` in refine.py.
  static let maxPasses = 6

  // Patterns are static, tested constants — a bad pattern is a programmer error, so
  // we fail loudly (matching CaptureKit's `preconditionFailure` convention) rather
  // than forcing a try.
  private static func compiled(
    _ pattern: String, _ options: NSRegularExpression.Options = []
  ) -> NSRegularExpression {
    guard let re = try? NSRegularExpression(pattern: pattern, options: options) else {
      preconditionFailure("invalid regex: \(pattern)")
    }
    return re
  }

  private static let fillerRE = compiled(
    #"\b(?:u+m+|u+h+|erm?|ehm?|mm+|m*hm+|ah+)\b"#, [.caseInsensitive])
  private static let leadingDiscourseRE = compiled(
    #"(?:^|(?<=[.!?]\s))(?:so|well|you know|i mean|like|okay|ok)\s*,\s*"#, [.caseInsensitive])
  private static let embeddedDiscourseRE = compiled(
    #"\s*,\s*(?:you know|i mean)\s*,\s*"#, [.caseInsensitive])
  private static let wordRepeatRE = compiled(#"\b(\w+)(?:\s+\1\b)+"#, [.caseInsensitive])
  private static let phraseRepeatRE = compiled(
    #"\b(\w+(?:\s+\w+){1,2})\s+\1\b"#, [.caseInsensitive])
  private static let falseStartRE = compiled(
    #"(?:^|(?<=[.!?]\s))(?:\w+\s+){0,2}\w+(?:—|--|…|\.\.\.)\s+"#)
  private static let wsRE = compiled(#"\s+"#)
  private static let commaRunRE = compiled(#"\s*,(?:\s*,)+"#)
  private static let leadingJunkRE = compiled(#"^[\s,]+"#)
  private static let spaceBeforePunctRE = compiled(#"\s+([,.!?;:])"#)
  private static let commaSpaceRE = compiled(#",(?=[^\s\d])"#)
  private static let multiSpaceRE = compiled(#"\s{2,}"#)
  private static let standaloneIRE = compiled(#"\bi\b"#)
  private static let sentenceStartRE = compiled(#"(^\s*|[.!?]\s+)([a-z])"#)

  // MARK: - Steps

  public static func stripFillers(_ text: String) -> String {
    var t = sub(fillerRE, " ", text)
    // Normalize whitespace first so the leading-discourse "^" anchor sees the real
    // clause start (filler removal can leave stray leading spaces).
    t = trim(sub(wsRE, " ", t))
    // Iterate to a fixpoint; tidy the clause start before discourse removal so an
    // exposed marker (", okay," -> "okay," -> "") or chained markers are fully removed.
    var prev = ""
    while prev != t {
      prev = t
      t = sub(commaRunRE, ",", t)
      t = sub(leadingJunkRE, "", t)
      t = sub(embeddedDiscourseRE, ", ", t)
      t = sub(leadingDiscourseRE, "", t)
    }
    return trim(sub(wsRE, " ", t))
  }

  public static func collapseRepetitions(_ text: String) -> String {
    var t = sub(wordRepeatRE, "$1", text)
    var prev = ""
    while prev != t {
      prev = t
      t = sub(phraseRepeatRE, "$1", t)
    }
    return t
  }

  public static func collapseFalseStarts(_ text: String) -> String {
    sub(falseStartRE, "", text)
  }

  public static func fixSpacingPunctuation(_ text: String) -> String {
    var t = sub(spaceBeforePunctRE, "$1", text)
    t = sub(commaSpaceRE, ", ", t)  // space after comma, but keep "1,000"
    t = sub(multiSpaceRE, " ", t)
    return trim(t)
  }

  public static func polishCapitalization(_ text: String) -> String {
    let withI = sub(standaloneIRE, "I", text)
    let ns = withI as NSString
    let full = NSRange(location: 0, length: ns.length)
    var result = ""
    var cursor = 0
    for match in sentenceStartRE.matches(in: withI, range: full) {
      let letter = match.range(at: 2)
      result += ns.substring(with: NSRange(location: cursor, length: letter.location - cursor))
      result += ns.substring(with: letter).uppercased()
      cursor = letter.location + letter.length
    }
    result += ns.substring(from: cursor)
    return result
  }

  // MARK: - Composition

  /// Run the steps to a fixpoint, in the same fixed order as refine.py. Idempotent.
  public static func cleanText(_ input: String) -> String {
    var text = input
    for _ in 0..<maxPasses {
      var cleaned = stripFillers(text)
      cleaned = collapseRepetitions(cleaned)
      cleaned = fixSpacingPunctuation(cleaned)
      cleaned = collapseFalseStarts(cleaned)
      cleaned = polishCapitalization(cleaned)
      cleaned = trim(cleaned)
      if cleaned == text { break }
      text = cleaned
    }
    return text
  }

  /// Clean each turn's text; preserve speaker/start/end; drop now-empty turns.
  public static func cleanTurns(_ turns: [Turn]) -> [Turn] {
    turns.compactMap { turn in
      let text = cleanText(turn.text)
      return text.isEmpty
        ? nil : Turn(speaker: turn.speaker, start: turn.start, end: turn.end, text: text)
    }
  }

  // MARK: - Helpers

  private static func sub(_ re: NSRegularExpression, _ template: String, _ text: String) -> String {
    let range = NSRange(text.startIndex..., in: text)
    return re.stringByReplacingMatches(in: text, range: range, withTemplate: template)
  }

  private static func trim(_ text: String) -> String {
    text.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
