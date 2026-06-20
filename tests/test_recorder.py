import json
import os
from pathlib import Path

import pytest

from meetingbot import config, notes, recorder


def fake_session(base: Path, name: str = "20260612-100000-sync") -> Path:
    session = config.SESSIONS_DIR / name
    session.mkdir(parents=True)
    recorder.write_meta(
        session,
        {
            "title": "Sync",
            "started_at": "2026-06-12T10:00:00",
            "ended_at": "2026-06-12T10:30:00",
            "duration_s": 1800,
            "session_dir": str(session),
        },
    )
    segments = [
        {"start": 0.0, "end": 2.0, "speaker": "mic", "text": "hello team", "chunk": "mic-0001.wav"},
        {"start": 3.0, "end": 5.0, "speaker": "sys", "text": "hi there", "chunk": "sys-0001.wav"},
    ]
    (session / "transcript.jsonl").write_text("".join(json.dumps(s) + "\n" for s in segments))
    return session


class TestFinalizeSession:
    def test_no_key_writes_placeholder_note(self, isolated: Path) -> None:
        session = fake_session(isolated)
        note_path, summarized = recorder.finalize_session(session)
        assert not summarized
        body = note_path.read_text()
        assert notes.PLACEHOLDER_SUMMARY in body
        assert "**Me** [00:00]: hello team" in body
        assert "**Them** [00:03]: hi there" in body
        meta = recorder.read_meta(session)
        assert meta["note_path"] == str(note_path)
        assert meta["summarized"] is False

    def test_with_key_summarizes(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from meetingbot import summarize

        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(
            summarize, "summarize_meeting", lambda *a, **k: "## Summary\n- great meeting"
        )
        session = fake_session(isolated)
        note_path, summarized = recorder.finalize_session(session)
        assert summarized
        assert "great meeting" in note_path.read_text()
        assert recorder.read_meta(session)["summarized"] is True

    def test_auto_titles_when_no_title(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from meetingbot import summarize

        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(summarize, "summarize_meeting", lambda *a, **k: "## Summary\n- launch")
        monkeypatch.setattr(summarize, "generate_title", lambda *a, **k: "Q3 Launch Planning")
        session = fake_session(isolated, name="20260612-090000-untitled")
        meta = recorder.read_meta(session)
        meta["title"] = None
        recorder.write_meta(session, meta)

        recorder.summarize_session(session)
        assert recorder.read_meta(session)["title"] == "Q3 Launch Planning"

    def test_keeps_explicit_title(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from meetingbot import summarize

        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(summarize, "summarize_meeting", lambda *a, **k: "## Summary\n- x")

        def fail(*a: object, **k: object) -> str:
            raise AssertionError("generate_title must not run when a title exists")

        monkeypatch.setattr(summarize, "generate_title", fail)
        session = fake_session(isolated)  # title "Sync"
        recorder.summarize_session(session)
        assert recorder.read_meta(session)["title"] == "Sync"

    def test_summarize_session_without_transcript_raises(self, isolated: Path) -> None:
        session = config.SESSIONS_DIR / "20260612-110000-empty"
        session.mkdir(parents=True)
        recorder.write_meta(session, {"title": None, "started_at": "2026-06-12T11:00:00"})
        with pytest.raises(RuntimeError, match="no transcript"):
            recorder.summarize_session(session)


class TestEnsureMeta:
    def test_synthesizes_meta_for_native_session(self, isolated: Path) -> None:
        session = config.SESSIONS_DIR / "20260613-100000-meeting"
        session.mkdir(parents=True)
        (session / "session.json").write_text(
            json.dumps({"started_at": "2026-06-13T10:00:00Z", "sample_rate": 16000})
        )
        (session / "manifest.jsonl").write_text(
            json.dumps({"stream": "mic", "file": "mic-0001.wav", "start": 0.0, "end": 42.0}) + "\n"
        )
        meta = recorder.ensure_meta(session)
        assert (session / "meta.json").exists()
        assert meta["duration_s"] == 42
        assert meta["source"] == "native-app"
        assert meta["started_at"].startswith("2026-06-13T")

    def test_applies_title_and_preserves_existing(self, isolated: Path) -> None:
        session = config.SESSIONS_DIR / "20260613-110000-meeting"
        session.mkdir(parents=True)
        (session / "session.json").write_text(json.dumps({"started_at": "2026-06-13T11:00:00"}))
        recorder.ensure_meta(session, title="Standup")
        assert recorder.read_meta(session)["title"] == "Standup"
        # Re-running with a new title updates it without losing the file.
        recorder.ensure_meta(session, title="Retro")
        assert recorder.read_meta(session)["title"] == "Retro"


class TestExportSession:
    def test_extract_summary_from_note(self, isolated: Path) -> None:
        session = fake_session(isolated)
        recorder.finalize_session(session)  # writes the markdown note (no key)
        note_path = Path(recorder.read_meta(session)["note_path"])
        summary = recorder._extract_summary(note_path)
        assert notes.PLACEHOLDER_SUMMARY in summary
        assert "## Transcript" not in summary

    def test_export_session_runs_named_target(self, isolated: Path) -> None:
        session = fake_session(isolated)
        recorder.finalize_session(session)
        results = recorder.export_session(session, ["markdown"])
        assert results[0].target == "markdown"
        assert Path(results[0].location).exists()

    def test_finalize_records_exports_in_meta(self, isolated: Path) -> None:
        session = fake_session(isolated)
        recorder.finalize_session(session)
        meta = recorder.read_meta(session)
        assert meta["exports"][0]["target"] == "markdown"


class TestRecovery:
    def test_finds_and_finishes_interrupted_session(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A native-app crash leaves session.json + manifest + transcript but no note.
        session = config.SESSIONS_DIR / "20260614-090000-meeting"
        session.mkdir(parents=True)
        (session / "session.json").write_text(json.dumps({"started_at": "2026-06-14T09:00:00"}))
        (session / "manifest.jsonl").write_text(
            json.dumps({"stream": "mic", "file": "mic-0001.wav", "start": 0.0, "end": 5.0}) + "\n"
        )
        (session / "transcript.jsonl").write_text(
            json.dumps(
                {
                    "start": 0.0,
                    "end": 2.0,
                    "speaker": "mic",
                    "text": "hello",
                    "chunk": "mic-0001.wav",
                }
            )
            + "\n"
        )
        # Don't run real Whisper during recovery.
        monkeypatch.setattr(recorder.transcribe, "transcribe_session", lambda *a, **k: None)

        assert recorder.unfinished_sessions() == [session]
        made = recorder.recover()
        assert len(made) == 1 and made[0].exists()
        # Once finalized it's no longer "unfinished".
        assert recorder.unfinished_sessions() == []

    def test_finalized_and_empty_sessions_are_not_recovered(self, isolated: Path) -> None:
        # Finalized session (has note_path) — skip.
        done = config.SESSIONS_DIR / "done"
        done.mkdir(parents=True)
        (done / "manifest.jsonl").write_text("")
        recorder.write_meta(done, {"started_at": "2026-06-14T09:00:00", "note_path": "/x.md"})
        # Session with no manifest (never captured) — skip.
        empty = config.SESSIONS_DIR / "empty"
        empty.mkdir(parents=True)
        assert recorder.unfinished_sessions() == []


class TestSessionListing:
    def test_lists_only_real_sessions_newest_first(self, isolated: Path) -> None:
        fake_session(isolated, "20260610-090000-old")
        fake_session(isolated, "20260612-100000-new")
        (config.SESSIONS_DIR / "not-a-session").mkdir()
        sessions = recorder.list_sessions()
        assert [s.name for s in sessions] == [
            "20260612-100000-new",
            "20260610-090000-old",
        ]
        assert recorder.latest_session() is not None
        assert recorder.latest_session().name == "20260612-100000-new"

    def test_empty(self, isolated: Path) -> None:
        assert recorder.list_sessions() == []
        assert recorder.latest_session() is None


class TestCurrentRecording:
    def test_none_when_no_file(self, isolated: Path) -> None:
        assert recorder.current_recording() is None

    def test_live_meetingbot_pid_reported(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(recorder, "_pid_is_meetingbot", lambda pid: True)
        config.DATA_DIR.mkdir(parents=True)
        config.CURRENT_FILE.write_text(
            json.dumps({"pid": os.getpid(), "session_dir": "x", "started_at": "y"})
        )
        info = recorder.current_recording()
        assert info is not None
        assert info["pid"] == os.getpid()

    def test_dead_pid_cleaned_up(self, isolated: Path) -> None:
        config.DATA_DIR.mkdir(parents=True)
        config.CURRENT_FILE.write_text(
            json.dumps({"pid": 2**22 + 12345, "session_dir": "x", "started_at": "y"})
        )
        assert recorder.current_recording() is None
        assert not config.CURRENT_FILE.exists()

    def test_recycled_live_pid_treated_as_stale(self, isolated: Path) -> None:
        # The pytest process is alive but is NOT a meeting-bot process, so the
        # lock must be treated as stale and cleared (recycled-PID guard).
        config.DATA_DIR.mkdir(parents=True)
        config.CURRENT_FILE.write_text(
            json.dumps({"pid": os.getpid(), "session_dir": "x", "started_at": "y"})
        )
        assert recorder.current_recording() is None
        assert not config.CURRENT_FILE.exists()

    def test_corrupt_file_cleaned_up(self, isolated: Path) -> None:
        config.DATA_DIR.mkdir(parents=True)
        config.CURRENT_FILE.write_text("not json")
        assert recorder.current_recording() is None
        assert not config.CURRENT_FILE.exists()
