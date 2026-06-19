from meetingbot import analytics


def _seg(start: float, end: float, speaker: str, text: str) -> dict:
    return {"start": start, "end": end, "speaker": speaker, "text": text}


class TestCompute:
    def test_talk_time_and_words(self) -> None:
        segs = [
            _seg(0, 4, "mic", "hello there team"),  # Me: 4s, 3 words
            _seg(10, 16, "sys", "yes absolutely agreed totally"),  # Them: 6s, 4 words
        ]
        a = analytics.compute(segs)
        assert round(a.by_speaker["Me"].seconds) == 4
        assert round(a.by_speaker["Them"].seconds) == 6
        assert a.by_speaker["Me"].words == 3
        assert a.by_speaker["Them"].words == 4
        assert round(a.total_seconds) == 10
        ratios = a.talk_ratio()
        assert abs(ratios["Me"] - 0.4) < 1e-6
        assert abs(ratios["Them"] - 0.6) < 1e-6

    def test_longest_monologue(self) -> None:
        segs = [_seg(0, 2, "mic", "a"), _seg(30, 45, "sys", "long one")]
        a = analytics.compute(segs)
        assert a.longest_monologue_speaker == "Them"
        assert round(a.longest_monologue_s) == 15

    def test_empty(self) -> None:
        a = analytics.compute([])
        assert a.total_seconds == 0
        assert a.talk_ratio() == {}


class TestFormat:
    def test_section_has_table_and_totals(self) -> None:
        segs = [_seg(0, 4, "mic", "hi"), _seg(5, 9, "sys", "yo")]
        md = analytics.section(segs)
        assert md.startswith("## Meeting stats")
        assert "| Speaker | Talk time | Share | Words | Turns |" in md
        assert "Total spoken:" in md

    def test_empty_section_is_blank(self) -> None:
        assert analytics.section([]) == ""
