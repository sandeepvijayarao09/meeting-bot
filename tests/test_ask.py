from pathlib import Path

import pytest

from meetingbot import ask, config, notes, summarize


def _note(title: str, date: str, summary: str, transcript: str) -> None:
    notes.write_note({"title": title, "started_at": date}, summary, transcript)


class TestAsk:
    def test_no_key_raises(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(summarize, "have_key", lambda: False)
        with pytest.raises(summarize.MissingAPIKeyError, match="NVIDIA"):
            ask.ask("anything")

    def test_no_matches_returns_gracefully(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(summarize, "have_key", lambda: True)
        result = ask.ask("nonexistent topic")
        assert result.sources == []
        assert "No meetings matched" in result.answer

    def test_retrieves_relevant_note_and_answers(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _note("Pricing sync", "2026-06-10T10:00:00", "We set the price at $49/mo", "discussion")
        _note("Hiring", "2026-06-11T10:00:00", "Open two roles", "discussion")

        captured = {}

        def fake_complete(system: str, user: str, **kw: object) -> str:
            captured["system"] = system
            captured["user"] = user
            return "The price was set to $49/mo."

        monkeypatch.setattr(summarize, "have_key", lambda: True)
        monkeypatch.setattr(summarize, "complete", fake_complete)

        result = ask.ask("what price did we set?")
        assert result.answer == "The price was set to $49/mo."
        # The pricing note must be retrieved and put into the context.
        assert "Pricing sync" in captured["user"]
        assert "$49/mo" in captured["user"]
        assert any(s["title"] == "Pricing sync" for s in result.sources)

    def test_context_is_bounded(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ask, "PER_NOTE_CHARS", 50)
        _note("Long", "2026-06-10T10:00:00", "x" * 5000, "y" * 5000)
        hits = notes.search("Long")
        context = ask.build_context(hits)
        assert len(context) < 500  # truncated per-note
