import json
from pathlib import Path

import numpy as np
import pytest

from meetingbot import transcribe
from tests.conftest import tone, write_wav


class TestWavIO:
    def test_load_wav_roundtrip(self, tmp_path: Path) -> None:
        original = tone(0.5)
        loaded = transcribe.load_wav(write_wav(tmp_path / "t.wav", original))
        assert loaded.dtype == np.float32
        assert len(loaded) == len(original)
        assert np.allclose(loaded, original, atol=1e-3)

    def test_load_wav_rejects_stereo_or_24bit(self, tmp_path: Path) -> None:
        import wave

        with wave.open(str(tmp_path / "bad.wav"), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * 64)
        with pytest.raises(ValueError, match="16-bit mono"):
            transcribe.load_wav(tmp_path / "bad.wav")

    def test_silence_detection(self) -> None:
        assert transcribe.is_silent(np.zeros(16000, dtype=np.float32))
        assert transcribe.is_silent(np.array([], dtype=np.float32))
        assert not transcribe.is_silent(tone(1.0))


class TestManifest:
    def test_read_manifest_missing(self, tmp_path: Path) -> None:
        assert transcribe.read_manifest(tmp_path) == []

    def test_read_manifest_skips_blank_lines(self, tmp_path: Path) -> None:
        entry = {"stream": "mic", "file": "mic-0001.wav", "start": 0.0, "end": 30.0}
        (tmp_path / "manifest.jsonl").write_text(json.dumps(entry) + "\n\n")
        assert transcribe.read_manifest(tmp_path) == [entry]

    def test_load_segments_missing(self, tmp_path: Path) -> None:
        assert transcribe.load_segments(tmp_path) == []


class TestMergeTurns:
    def test_interleaves_speakers_by_time(self) -> None:
        segments = [
            {"start": 10.0, "end": 12.0, "speaker": "sys", "text": "world"},
            {"start": 0.0, "end": 2.0, "speaker": "mic", "text": "hello"},
        ]
        turns = transcribe.merge_turns(segments)
        assert [t["speaker"] for t in turns] == ["Me", "Them"]
        assert [t["text"] for t in turns] == ["hello", "world"]

    def test_coalesces_consecutive_same_speaker(self) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "speaker": "mic", "text": "one"},
            {"start": 2.5, "end": 4.0, "speaker": "mic", "text": "two"},
        ]
        turns = transcribe.merge_turns(segments)
        assert len(turns) == 1
        assert turns[0]["text"] == "one two"
        assert turns[0]["end"] == 4.0

    def test_does_not_coalesce_across_long_gaps(self) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "speaker": "mic", "text": "one"},
            {"start": 30.0, "end": 31.0, "speaker": "mic", "text": "two"},
        ]
        assert len(transcribe.merge_turns(segments)) == 2

    def test_empty(self) -> None:
        assert transcribe.merge_turns([]) == []


class TestFormatting:
    def test_format_transcript(self) -> None:
        turns = [{"speaker": "Me", "start": 65.0, "end": 67.0, "text": "hi"}]
        assert transcribe.format_transcript(turns) == "**Me** [01:05]: hi"

    def test_timestamp_rolls_to_hours(self) -> None:
        turns = [{"speaker": "Me", "start": 3725.0, "end": 3726.0, "text": "x"}]
        assert "[1:02:05]" in transcribe.format_transcript(turns)


class TestTranscribeSession:
    def test_skips_silent_and_missing_chunks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_wav(tmp_path / "mic-0001.wav", np.zeros(16000, dtype=np.float32))
        manifest = [
            {"stream": "mic", "file": "mic-0001.wav", "start": 0.0, "end": 1.0},
            {"stream": "sys", "file": "sys-0001.wav", "start": 0.0, "end": 1.0},  # missing
        ]
        (tmp_path / "manifest.jsonl").write_text("".join(json.dumps(e) + "\n" for e in manifest))
        called = False

        def fake_model_call(*a: object, **k: object) -> list[dict[str, float | str]]:
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(transcribe, "_transcribe_array", fake_model_call)
        transcribe.transcribe_session(tmp_path, model="fake")
        assert not called  # silent + missing chunks never reach the model

    def test_resumes_without_duplicating_chunks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_wav(tmp_path / "mic-0001.wav", tone(1.0))
        entry = {"stream": "mic", "file": "mic-0001.wav", "start": 10.0, "end": 11.0}
        (tmp_path / "manifest.jsonl").write_text(json.dumps(entry) + "\n")
        monkeypatch.setattr(
            transcribe,
            "_transcribe_array",
            lambda *a, **k: [{"start": 0.5, "end": 0.9, "text": "hello"}],
        )
        transcribe.transcribe_session(tmp_path, model="fake")
        transcribe.transcribe_session(tmp_path, model="fake")  # second run: no-op
        segments = transcribe.load_segments(tmp_path)
        assert len(segments) == 1
        assert segments[0]["start"] == 10.5  # chunk offset + in-chunk time
        assert segments[0]["speaker"] == "mic"
