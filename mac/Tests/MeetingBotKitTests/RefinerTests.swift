import XCTest

@testable import MeetingBotKit

/// Parity tests with the Python `tests/test_refine.py` — the Swift Refiner must
/// produce the same cleanup so iOS and macOS/CLI notes match.
final class RefinerTests: XCTestCase {
  func testStripFillers() {
    XCTAssertEqual(Refiner.stripFillers("um I uh think hmm so"), "I think so")
    XCTAssertEqual(Refiner.stripFillers("so, we should ship"), "we should ship")
    XCTAssertEqual(Refiner.stripFillers("it works, you know, well"), "it works, well")
    XCTAssertEqual(Refiner.stripFillers("I like it"), "I like it")  // verb, not filler
    XCTAssertEqual(
      Refiner.stripFillers("get ahead and err on caution"), "get ahead and err on caution")
  }

  func testCollapseRepetitions() {
    XCTAssertEqual(Refiner.collapseRepetitions("the the the report"), "the report")
    XCTAssertEqual(Refiner.collapseRepetitions("I think I think we ship"), "I think we ship")
    XCTAssertEqual(Refiner.collapseRepetitions("The the plan"), "The plan")
    XCTAssertEqual(
      Refiner.collapseRepetitions("the cat sat on the mat"), "the cat sat on the mat")
  }

  func testCollapseFalseStarts() {
    XCTAssertEqual(Refiner.collapseFalseStarts("I think— I believe we ship"), "I believe we ship")
    XCTAssertEqual(Refiner.collapseFalseStarts("we could... we should decide"), "we should decide")
    XCTAssertEqual(Refiner.collapseFalseStarts("we should decide now"), "we should decide now")
    // A long lead-in before a "..." pause is real content, not a false start.
    XCTAssertEqual(
      Refiner.collapseFalseStarts("the plan looks good... good"), "the plan looks good... good")
  }

  func testSpacingAndCapitalization() {
    XCTAssertEqual(Refiner.fixSpacingPunctuation("hello ,world  ."), "hello, world.")
    XCTAssertEqual(Refiner.fixSpacingPunctuation("we saw 1,000 users"), "we saw 1,000 users")
    XCTAssertEqual(Refiner.polishCapitalization("i went. they came"), "I went. They came")
  }

  func testCleanText() {
    XCTAssertEqual(
      Refiner.cleanText("um so, I I think— I believe we we should ship it"),
      "I believe we should ship it")
    XCTAssertEqual(Refiner.cleanText("um uh hmm"), "")
  }

  /// Differential parity: each expected value is the output of the Python
  /// `refine.clean_text` for the same input. The Swift port must match exactly.
  func testCleanTextParityWithPython() {
    let cases: [(String, String)] = [
      ("I I I think we we ship", "I think we ship"),
      ("Well, so, um, the the plan looks good", "The plan looks good"),
      ("we saw 1,000,000 users and 3.5 percent", "We saw 1,000,000 users and 3.5 percent"),
      ("uh... I mean, like, the report", "... The report"),
      ("okay, okay, yeah the the the report", "Yeah the report"),
      ("so, you know, we should, you know, decide", "We should, decide"),
      ("he said hi ,then left .", "He said hi, then left."),
      ("i think i am right and i.e. so", "I think I am right and I.e. So"),
    ]
    for (input, expected) in cases {
      XCTAssertEqual(Refiner.cleanText(input), expected, "parity drift for: \(input)")
    }
  }

  func testCleanTextIsIdempotent() {
    for raw in [
      "um so, I I think— I believe we we should ship it",
      "okay, the plan looks looks good ... good",
      "i went. they came. um so, yeah",
    ] {
      let once = Refiner.cleanText(raw)
      XCTAssertEqual(Refiner.cleanText(once), once, "not idempotent for: \(raw)")
    }
  }

  func testCleanTurns() {
    let turns = [Turn(speaker: "Me", start: 1, end: 4, text: "uh the the plan")]
    XCTAssertEqual(
      Refiner.cleanTurns(turns), [Turn(speaker: "Me", start: 1, end: 4, text: "The plan")])

    let withEmpty = [
      Turn(speaker: "Me", start: 0, end: 1, text: "um uh"),
      Turn(speaker: "Them", start: 2, end: 3, text: "real content"),
    ]
    XCTAssertEqual(Refiner.cleanTurns(withEmpty).map(\.text), ["Real content"])
    XCTAssertEqual(Refiner.cleanTurns([]), [])
  }
}
