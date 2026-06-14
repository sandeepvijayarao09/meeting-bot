import json
from pathlib import Path

from meetingbot import diarize
from meetingbot.diarize import SpeakerTurn


class TestLetterLabels:
    def test_sequence(self) -> None:
        assert [diarize._letter(i) for i in range(3)] == ["A", "B", "C"]
        assert diarize._letter(25) == "Z"
        assert diarize._letter(26) == "AA"


class TestAssignSpeakers:
    def test_labels_sys_segments_by_overlap(self) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "speaker": "sys", "text": "hi"},
            {"start": 5.0, "end": 7.0, "speaker": "sys", "text": "yes"},
        ]
        turns = [
            SpeakerTurn(0.0, 3.0, "Speaker A"),
            SpeakerTurn(4.0, 8.0, "Speaker B"),
        ]
        out = diarize.assign_speakers(segments, turns)
        assert out[0]["sub_speaker"] == "Speaker A"
        assert out[1]["sub_speaker"] == "Speaker B"

    def test_mic_segments_untouched(self) -> None:
        segments = [{"start": 0.0, "end": 2.0, "speaker": "mic", "text": "me"}]
        turns = [SpeakerTurn(0.0, 3.0, "Speaker A")]
        out = diarize.assign_speakers(segments, turns)
        assert "sub_speaker" not in out[0]

    def test_no_overlap_leaves_segment_unlabeled(self) -> None:
        segments = [{"start": 10.0, "end": 12.0, "speaker": "sys", "text": "x"}]
        turns = [SpeakerTurn(0.0, 3.0, "Speaker A")]
        out = diarize.assign_speakers(segments, turns)
        assert "sub_speaker" not in out[0]

    def test_empty_turns_passes_through(self) -> None:
        segments = [{"start": 0.0, "end": 2.0, "speaker": "sys", "text": "x"}]
        assert diarize.assign_speakers(segments, []) == segments


class TestDiarizeSession:
    def test_rewrites_transcript_with_injected_diarizer(self, tmp_path: Path) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "speaker": "sys", "text": "a", "chunk": "sys-0001.wav"},
            {"start": 5.0, "end": 7.0, "speaker": "sys", "text": "b", "chunk": "sys-0001.wav"},
        ]
        (tmp_path / "transcript.jsonl").write_text("".join(json.dumps(s) + "\n" for s in segments))
        (tmp_path / "sys-0001.wav").write_bytes(b"RIFF")  # presence only; diarizer is mocked

        def fake_diarizer(paths: list[Path]) -> list[SpeakerTurn]:
            return [SpeakerTurn(0.0, 3.0, "Speaker A"), SpeakerTurn(4.0, 8.0, "Speaker B")]

        count = diarize.diarize_session(tmp_path, diarizer=fake_diarizer)
        assert count == 2
        rewritten = [
            json.loads(line) for line in (tmp_path / "transcript.jsonl").read_text().splitlines()
        ]
        assert rewritten[0]["sub_speaker"] == "Speaker A"
        assert rewritten[1]["sub_speaker"] == "Speaker B"

    def test_no_sys_chunks_returns_zero(self, tmp_path: Path) -> None:
        (tmp_path / "transcript.jsonl").write_text(
            json.dumps({"start": 0.0, "end": 1.0, "speaker": "mic", "text": "x"}) + "\n"
        )
        assert diarize.diarize_session(tmp_path, diarizer=lambda p: []) == 0
