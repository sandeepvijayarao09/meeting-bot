import json
from pathlib import Path
from typing import Any

import pytest

from meetingbot import config, refine, summarize, transcribe


class TestStripFillers:
    def test_removes_vocalized_fillers(self) -> None:
        assert refine.strip_fillers("um I uh think hmm so") == "I think so"

    def test_removes_leading_discourse_marker(self) -> None:
        assert refine.strip_fillers("so, we should ship") == "we should ship"

    def test_removes_embedded_discourse_marker(self) -> None:
        assert refine.strip_fillers("it works, you know, well") == "it works, well"

    def test_keeps_like_as_a_verb(self) -> None:
        # "like" is only a filler when comma-delimited; the verb must survive.
        assert refine.strip_fillers("I like it") == "I like it"

    def test_does_not_bite_real_words(self) -> None:
        phrase = "get ahead and err on caution"
        assert refine.strip_fillers(phrase) == phrase


class TestCollapseRepetitions:
    def test_collapses_single_word_stutter(self) -> None:
        assert refine.collapse_repetitions("the the the report") == "the report"

    def test_collapses_phrase_stutter(self) -> None:
        assert refine.collapse_repetitions("I think I think we ship") == "I think we ship"

    def test_is_case_insensitive(self) -> None:
        assert refine.collapse_repetitions("The the plan") == "The plan"

    def test_leaves_non_adjacent_repeats(self) -> None:
        assert refine.collapse_repetitions("the cat sat on the mat") == "the cat sat on the mat"


class TestCollapseFalseStarts:
    def test_drops_fragment_before_dash_restart(self) -> None:
        assert refine.collapse_false_starts("I think— I believe we ship") == "I believe we ship"

    def test_handles_ellipsis(self) -> None:
        assert refine.collapse_false_starts("we could... we should decide") == "we should decide"

    def test_leaves_clean_text(self) -> None:
        assert refine.collapse_false_starts("we should decide now") == "we should decide now"

    def test_does_not_swallow_long_lead_in_before_ellipsis(self) -> None:
        # A long run before a "..." pause is real content, not a short false start.
        text = "the plan looks good... good"
        assert refine.collapse_false_starts(text) == text


class TestSpacingAndCapitalization:
    def test_fix_spacing_punctuation(self) -> None:
        assert refine.fix_spacing_punctuation("hello ,world  .") == "hello, world."

    def test_keeps_thousands_separator(self) -> None:
        assert refine.fix_spacing_punctuation("we saw 1,000 users") == "we saw 1,000 users"

    def test_polish_capitalization(self) -> None:
        assert refine.polish_capitalization("i went. they came") == "I went. They came"


class TestCleanText:
    def test_full_pipeline_on_disfluent_sentence(self) -> None:
        raw = "um so, I I think— I believe we we should ship it"
        assert refine.clean_text(raw) == "I believe we should ship it"

    def test_empty_stays_empty(self) -> None:
        assert refine.clean_text("um uh hmm") == ""


class TestCleanTurns:
    def test_preserves_speaker_and_timestamps(self) -> None:
        turns = [{"speaker": "Me", "start": 1.0, "end": 4.0, "text": "uh the the plan"}]
        cleaned = refine.clean_turns(turns)
        assert cleaned == [{"speaker": "Me", "start": 1.0, "end": 4.0, "text": "The plan"}]

    def test_drops_turns_that_clean_to_empty(self) -> None:
        turns = [
            {"speaker": "Me", "start": 0.0, "end": 1.0, "text": "um uh"},
            {"speaker": "Them", "start": 2.0, "end": 3.0, "text": "real content"},
        ]
        cleaned = refine.clean_turns(turns)
        assert [t["text"] for t in cleaned] == ["Real content"]

    def test_empty_input(self) -> None:
        assert refine.clean_turns([]) == []


def _write_transcript(session_dir: Path, segments: list[dict[str, Any]]) -> None:
    (session_dir / "transcript.jsonl").write_text("".join(json.dumps(s) + "\n" for s in segments))


_SEGMENTS = [
    {"start": 0.0, "end": 3.0, "speaker": "mic", "text": "um so, I I think we should ship"},
    {"start": 4.0, "end": 6.0, "speaker": "sys", "text": "uh the the plan looks good"},
]


class TestRefineTranscript:
    def test_off_matches_raw_transcript(self, tmp_path: Path) -> None:
        _write_transcript(tmp_path, _SEGMENTS)
        raw = transcribe.format_transcript(
            transcribe.merge_turns(transcribe.load_segments(tmp_path))
        )
        assert refine.refine_transcript(tmp_path, "off") == raw
        assert "um so," in raw  # the raw path is genuinely unrefined

    def test_local_cleans_without_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_transcript(tmp_path, _SEGMENTS)

        def boom(*a: object, **k: object) -> str:
            raise AssertionError("local tier must not call the cloud")

        monkeypatch.setattr(summarize, "complete", boom)
        out = refine.refine_transcript(tmp_path, "local")
        assert "um" not in out and "the the" not in out
        assert "I think we should ship" in out
        assert "**Me** [00:00]:" in out  # speaker/timestamp structure preserved

    def test_cloud_polishes_when_key_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_transcript(tmp_path, _SEGMENTS)
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        seen: list[str] = []

        def fake_complete(system: str, user: str, **k: object) -> str:
            seen.append(user)
            return "POLISHED TRANSCRIPT"

        monkeypatch.setattr(summarize, "complete", fake_complete)
        assert refine.refine_transcript(tmp_path, "cloud") == "POLISHED TRANSCRIPT"
        # the cloud tier polishes the locally-cleaned text, not the raw transcript
        assert "the the" not in seen[0]

    def test_cloud_without_key_falls_back_to_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_transcript(tmp_path, _SEGMENTS)
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "")

        def boom(*a: object, **k: object) -> str:
            raise AssertionError("must not call the cloud without a key")

        monkeypatch.setattr(summarize, "complete", boom)
        assert refine.refine_transcript(tmp_path, "cloud") == refine.refine_transcript(
            tmp_path, "local"
        )

    def test_cloud_failure_falls_back_to_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_transcript(tmp_path, _SEGMENTS)
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")

        def boom(*a: object, **k: object) -> str:
            raise RuntimeError("network down")

        monkeypatch.setattr(summarize, "complete", boom)
        # never raises; degrades to the local-cleaned transcript
        assert refine.refine_transcript(tmp_path, "cloud") == refine.refine_transcript(
            tmp_path, "local"
        )

    def test_empty_session(self, tmp_path: Path) -> None:
        assert refine.refine_transcript(tmp_path, "local") == ""


class TestPolishCloudMapReduce:
    def test_long_transcript_map_reduces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(summarize, "MAX_DIRECT_CHARS", 100)
        monkeypatch.setattr(summarize, "PIECE_CHARS", 60)
        calls: list[str] = []

        def fake_complete(system: str, user: str, **k: object) -> str:
            calls.append(user)
            return "ok"

        monkeypatch.setattr(summarize, "complete", fake_complete)
        long_md = "\n".join(f"**Me** [00:0{i % 10}]: line {i}" for i in range(40))
        refine.polish_cloud(long_md)
        assert len(calls) > 1  # split into multiple polish requests
