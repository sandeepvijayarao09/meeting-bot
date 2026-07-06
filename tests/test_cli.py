import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from meetingbot import config, notes
from meetingbot.cli import app
from tests.test_recorder import fake_session

runner = CliRunner()


class TestStatus:
    def test_idle(self, isolated: Path) -> None:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "idle" in result.output


class TestStop:
    def test_nothing_recording(self, isolated: Path) -> None:
        result = runner.invoke(app, ["stop"])
        assert result.exit_code == 1
        assert "nothing is recording" in result.output


class TestSetKey:
    def test_saves_upserts_and_clears(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = isolated / "config"
        monkeypatch.setattr(config, "CONFIG_DIR", cfg)  # never touch the real ~/.config key
        env_file = cfg / ".env"

        result = runner.invoke(app, ["set-key", "nvapi-abcdef123456"])
        assert result.exit_code == 0
        assert "NVIDIA_API_KEY=nvapi-abcdef123456" in env_file.read_text()
        assert "nvapi-abcdef123456" not in result.output  # masked, never echoed in full

        # Upsert: replace the key without duplicating, preserving unrelated lines.
        env_file.write_text("OTHER=1\nNVIDIA_API_KEY=old\n")
        runner.invoke(app, ["set-key", "nvapi-newkey987654"])
        text = env_file.read_text()
        assert "OTHER=1" in text and text.count("NVIDIA_API_KEY=") == 1
        assert "nvapi-newkey987654" in text

        # Clear with an empty value; other lines survive.
        result = runner.invoke(app, ["set-key", ""])
        assert result.exit_code == 0
        assert "NVIDIA_API_KEY=" not in env_file.read_text()
        assert "OTHER=1" in env_file.read_text()


class TestList:
    def test_empty(self, isolated: Path) -> None:
        result = runner.invoke(app, ["list"])
        assert "no notes yet" in result.output

    def test_lists_notes(self, isolated: Path) -> None:
        notes.write_note({"title": "Sync", "started_at": "2026-06-12T10:00:00"}, "s", "t")
        result = runner.invoke(app, ["list"])
        assert "2026-06-12-1000-sync.md" in result.output


class TestSearch:
    def test_no_match(self, isolated: Path) -> None:
        result = runner.invoke(app, ["search", "zebra"])
        assert "no matches" in result.output

    def test_match(self, isolated: Path) -> None:
        notes.write_note(
            {"title": "Sync", "started_at": "2026-06-12T10:00:00"},
            "we approved the budget",
            "t",
        )
        result = runner.invoke(app, ["search", "budget"])
        assert "Sync" in result.output


class TestSessions:
    def test_empty(self, isolated: Path) -> None:
        result = runner.invoke(app, ["sessions"])
        assert "no sessions" in result.output

    def test_states(self, isolated: Path) -> None:
        fake_session(isolated)  # has transcript, not summarized
        result = runner.invoke(app, ["sessions"])
        assert "transcribed" in result.output


class TestSummarize:
    def test_no_key_fails_cleanly(self, isolated: Path) -> None:
        fake_session(isolated)
        result = runner.invoke(app, ["summarize"])
        assert result.exit_code == 1
        assert "NVIDIA_API_KEY" in result.output

    def test_no_sessions(self, isolated: Path) -> None:
        result = runner.invoke(app, ["summarize"])
        assert result.exit_code == 1
        assert "no sessions yet" in result.output


class TestExport:
    def test_export_latest_to_markdown(self, isolated: Path) -> None:
        session = fake_session(isolated)
        from meetingbot import recorder

        recorder.finalize_session(session)
        result = runner.invoke(app, ["export", "--to", "markdown"])
        assert result.exit_code == 0
        assert "markdown:" in result.output

    def test_export_no_sessions(self, isolated: Path) -> None:
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 1
        assert "no sessions yet" in result.output


class TestRefineCmd:
    def test_local_refine_cleans(self, isolated: Path) -> None:
        fake_session(isolated)  # transcript: "hello team" / "hi there"
        result = runner.invoke(app, ["refine"])
        assert result.exit_code == 0
        assert "Hello team" in result.output  # sentence-start capitalized by refine

    def test_off_tier_is_verbatim(self, isolated: Path) -> None:
        fake_session(isolated)
        result = runner.invoke(app, ["refine", "--tier", "off"])
        assert result.exit_code == 0
        assert "hello team" in result.output  # raw, unrefined

    def test_no_sessions(self, isolated: Path) -> None:
        result = runner.invoke(app, ["refine"])
        assert result.exit_code == 1
        assert "no sessions yet" in result.output


class TestTransformCmd:
    def test_no_key_fails_cleanly(self, isolated: Path) -> None:
        fake_session(isolated)
        result = runner.invoke(app, ["transform", "key_points"])
        assert result.exit_code == 1
        assert "NVIDIA_API_KEY" in result.output

    def test_unknown_kind_fails(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        fake_session(isolated)
        result = runner.invoke(app, ["transform", "bogus"])
        assert result.exit_code == 1
        assert "unknown transform" in result.output

    def test_runs_with_mocked_nim(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from meetingbot import summarize

        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(summarize, "complete", lambda *a, **k: "- point one")
        fake_session(isolated)
        result = runner.invoke(app, ["transform", "key_points"])
        assert result.exit_code == 0
        assert "point one" in result.output


class TestAuthGoogle:
    def test_auth_google_reports_missing_secret(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRETS", isolated / "nope.json")
        result = runner.invoke(app, ["auth-google"])
        assert result.exit_code == 1
        assert "client secret" in result.output


class TestDoctor:
    def test_reports_missing_key(self, isolated: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "NVIDIA_API_KEY not set" in result.output

    def test_all_green_with_key_and_nim(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from meetingbot import summarize

        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(summarize, "ping", lambda: "ok")
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "NIM reachable" in result.output


class TestRecordGuard:
    def test_refuses_double_record(self, isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        from meetingbot import recorder

        # Simulate a genuine live recording process (the pytest PID is not itself
        # a Meeting Bot process, so the recycled-PID guard would otherwise clear it).
        monkeypatch.setattr(recorder, "_pid_is_meetingbot", lambda pid: True)
        config.DATA_DIR.mkdir(parents=True)
        config.CURRENT_FILE.write_text(
            json.dumps({"pid": os.getpid(), "session_dir": "x", "started_at": "y"})
        )
        result = runner.invoke(app, ["record"])
        assert result.exit_code != 0
        assert "already in progress" in result.output
