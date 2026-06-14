from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from meetingbot import config, exporters
from meetingbot.exporters import apple_notes, google_docs, mdconvert
from meetingbot.exporters.base import ExporterError, NeedsSetupError

META = {"title": "Roadmap sync", "started_at": "2026-06-12T10:00:00", "duration_s": 600}
SUMMARY = "## Summary\n- shipped beta\n\n## Action items\n- [ ] write docs — Me\n- [x] ship"
TRANSCRIPT = "**Me** [00:00]: hello"


class TestMarkdownToHtml:
    def test_headings_and_bullets(self) -> None:
        html = mdconvert.to_html("## Summary\n- one\n- two")
        assert "<h2>Summary</h2>" in html
        assert "<li>one</li>" in html

    def test_bold(self) -> None:
        assert "<strong>Me</strong>" in mdconvert.to_html("**Me** said hi")


class TestDocsRequests:
    def test_text_layout_and_title_first(self) -> None:
        build = mdconvert.to_docs_requests("## Summary\n- one", title="T")
        assert build.text == "T\n\nSummary\none\n"

    def test_exact_style_ranges(self) -> None:
        build = mdconvert.to_docs_requests("## Summary\n- one", title="T")
        # Title -> HEADING_1 at [1,3); Summary -> HEADING_2 at [4,12); bullet at [12,16)
        para = [r for r in build.requests if "updateParagraphStyle" in r]
        bullets = [r for r in build.requests if "createParagraphBullets" in r]
        assert para[0]["updateParagraphStyle"]["range"] == {"startIndex": 1, "endIndex": 3}
        assert para[0]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
        assert para[1]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "HEADING_2"
        assert para[1]["updateParagraphStyle"]["range"] == {"startIndex": 4, "endIndex": 12}
        assert bullets[0]["createParagraphBullets"]["range"] == {"startIndex": 12, "endIndex": 16}

    def test_checkbox_glyphs(self) -> None:
        build = mdconvert.to_docs_requests("- [ ] todo\n- [x] done", title="T")
        assert "☐ todo" in build.text
        assert "☑ done" in build.text

    def test_insert_index_matches_text(self) -> None:
        """The first char of body text lands at Docs index 1 (insert location)."""
        build = mdconvert.to_docs_requests("body line", title="Hi")
        assert build.text.startswith("Hi\n")


class TestRegistry:
    def test_configured_default_is_markdown_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "EXPORTERS", "markdown")
        assert exporters.configured_targets() == ["markdown"]

    def test_configured_dedupes_and_prepends_markdown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "EXPORTERS", "apple_notes,apple_notes,google_docs")
        assert exporters.configured_targets() == ["markdown", "apple_notes", "google_docs"]

    def test_unknown_target_raises(self) -> None:
        with pytest.raises(ExporterError, match="unknown export target"):
            exporters.get("dropbox")


class TestRunExports:
    def test_markdown_always_runs(self, isolated: Path) -> None:
        results = exporters.run_exports(["markdown"], META, SUMMARY, TRANSCRIPT)
        assert results[0].target == "markdown"
        assert Path(results[0].location).exists()

    def test_unconfigured_target_skipped_not_fatal(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(google_docs.GoogleDocsExporter, "available", lambda self: False)
        results = exporters.run_exports(["markdown", "google_docs"], META, SUMMARY, TRANSCRIPT)
        assert results[1].target == "google_docs"
        assert "not configured" in results[1].detail

    def test_target_failure_is_isolated(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(apple_notes.AppleNotesExporter, "available", lambda self: True)

        def boom(self: object, *a: object) -> None:
            raise ExporterError("notes app not running")

        monkeypatch.setattr(apple_notes.AppleNotesExporter, "export", boom)
        results = exporters.run_exports(["markdown", "apple_notes"], META, SUMMARY, TRANSCRIPT)
        assert Path(results[0].location).exists()  # markdown still written
        assert "failed: notes app not running" in results[1].detail


class TestAppleNotes:
    def test_applescript_escapes_quotes(self) -> None:
        script = apple_notes._applescript("Folder", 'body with "quotes" and \\ slash')
        assert '\\"quotes\\"' in script
        assert "make new note" in script

    def test_build_html_has_title_and_transcript(self) -> None:
        title, body = apple_notes._build_html(META, SUMMARY, TRANSCRIPT)
        assert title == "Roadmap sync"
        assert "<h1>Roadmap sync</h1>" in body
        assert "<h2>Transcript</h2>" in body

    def test_export_invokes_osascript(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(apple_notes, "_osascript", lambda s: calls.append(s) or "note-id-123")
        monkeypatch.setattr(apple_notes.AppleNotesExporter, "available", lambda self: True)
        res = apple_notes.AppleNotesExporter().export(META, SUMMARY, TRANSCRIPT)
        assert res.detail == "note-id-123"
        assert "Meeting Bot" in res.location


class TestGoogleDocs:
    def test_unavailable_without_token(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "GOOGLE_TOKEN", isolated / "nope.json")
        assert google_docs.GoogleDocsExporter().available() is False

    def test_export_without_auth_raises_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(google_docs, "_load_credentials", lambda: None)
        with pytest.raises(NeedsSetupError, match="auth-google"):
            google_docs.GoogleDocsExporter().export(META, SUMMARY, TRANSCRIPT)

    def test_export_builds_doc_with_mocked_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        class FakeExec:
            def __init__(self, result: dict[str, Any]):
                self._result = result

            def execute(self) -> dict[str, Any]:
                return self._result

        class FakeDocuments:
            def create(self, body: dict[str, Any]) -> FakeExec:
                captured["title"] = body["title"]
                return FakeExec({"documentId": "DOC123"})

            def batchUpdate(self, **kwargs: Any) -> FakeExec:  # noqa: N802 - Google API name
                captured["requests"] = kwargs["body"]["requests"]
                return FakeExec({})

        class FakeDocsService:
            def documents(self) -> FakeDocuments:
                return FakeDocuments()

        monkeypatch.setattr(google_docs, "_load_credentials", lambda: object())
        monkeypatch.setattr(google_docs, "_services", lambda creds: (FakeDocsService(), None))
        monkeypatch.setattr(config, "GOOGLE_DRIVE_FOLDER_ID", "")

        res = google_docs.GoogleDocsExporter().export(META, SUMMARY, TRANSCRIPT)
        assert res.location == "https://docs.google.com/document/d/DOC123/edit"
        assert captured["title"] == "Roadmap sync"
        # First request inserts all text at index 1.
        assert captured["requests"][0]["insertText"]["location"]["index"] == 1
        assert "Roadmap sync" in captured["requests"][0]["insertText"]["text"]
