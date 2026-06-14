from pathlib import Path

from meetingbot import notes


class TestSlugify:
    def test_basic(self) -> None:
        assert notes.slugify("Design Review: Q3 Plan!") == "design-review-q3-plan"

    def test_truncates(self) -> None:
        assert len(notes.slugify("x" * 100)) <= 40

    def test_empty_falls_back(self) -> None:
        assert notes.slugify("") == "meeting"
        assert notes.slugify("!!!") == "meeting"


class TestFormatDuration:
    def test_none_and_zero(self) -> None:
        assert notes.format_duration(None) == "?"
        assert notes.format_duration(0) == "?"

    def test_minutes(self) -> None:
        assert notes.format_duration(125) == "2m"

    def test_hours(self) -> None:
        assert notes.format_duration(3725) == "1h 02m"


META = {
    "title": "Roadmap sync",
    "started_at": "2026-06-12T10:00:00",
    "duration_s": 1800,
    "session_dir": "/tmp/somewhere",
}


class TestWriteAndSearch:
    def test_write_note_content(self, isolated: Path) -> None:
        path = notes.write_note(META, "## Summary\n- shipped it", "**Me** [00:00]: hi")
        body = path.read_text()
        assert path.name == "2026-06-12-1000-roadmap-sync.md"
        assert "title: Roadmap sync" in body
        assert "## Summary" in body
        assert "## Transcript" in body
        assert "**Me** [00:00]: hi" in body

    def test_rewrite_same_session_does_not_duplicate_index(self, isolated: Path) -> None:
        notes.write_note(META, "placeholder", "**Me** [00:00]: budget talk")
        notes.write_note(META, "real summary", "**Me** [00:00]: budget talk")
        hits = notes.search("budget")
        assert len(hits) == 1
        assert hits[0]["title"] == "Roadmap sync"

    def test_search_no_match(self, isolated: Path) -> None:
        notes.write_note(META, "summary", "transcript")
        assert notes.search("zebra") == []

    def test_search_tolerates_punctuation(self, isolated: Path) -> None:
        # FTS5 treats ? : * etc. as syntax; natural-language queries must not crash.
        notes.write_note(META, "we approved the migration plan", "t")
        hits = notes.search("what about the migration?")
        assert any("Roadmap" in h["title"] for h in hits)

    def test_search_empty_query(self, isolated: Path) -> None:
        notes.write_note(META, "summary", "transcript")
        assert notes.search("???") == []
        assert notes.search("") == []

    def test_search_snippet_highlights(self, isolated: Path) -> None:
        notes.write_note(META, "we agreed on the migration plan", "transcript")
        hits = notes.search("migration")
        assert "**migration**" in hits[0]["snippet"]

    def test_list_notes_newest_first(self, isolated: Path) -> None:
        old = dict(META, started_at="2026-06-10T09:00:00", title="Old")
        notes.write_note(old, "s", "t")
        notes.write_note(META, "s", "t")
        listing = notes.list_notes()
        assert listing[0].name == "2026-06-12-1000-roadmap-sync.md"

    def test_list_notes_empty(self, isolated: Path) -> None:
        assert notes.list_notes() == []
