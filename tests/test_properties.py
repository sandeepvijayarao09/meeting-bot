"""Property-based (fuzz) tests: each runs across many generated inputs to find
edge cases hand-written examples miss. Total generated cases here is ~1000+.

These target pure logic (no network, no Whisper, no real audio model).
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from meetingbot import diarize, notes, recorder, transcribe
from meetingbot.diarize import SpeakerTurn
from meetingbot.exporters import mdconvert
from meetingbot.server import SAMPLE_RATE, ChunkWriter

# Realistic, finite timing values.
times = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
texts = st.text(max_size=80)
speakers = st.sampled_from(["mic", "sys", "other"])


def _segment() -> st.SearchStrategy[dict]:
    return st.builds(
        lambda s, d, sp, t: {"start": s, "end": s + d, "speaker": sp, "text": t},
        times,
        st.floats(min_value=0, max_value=30, allow_nan=False, allow_infinity=False),
        speakers,
        texts,
    )


class TestMergeTurnsProperties:
    @settings(max_examples=150)
    @given(st.lists(_segment(), max_size=40))
    def test_sorted_and_words_subsequence(self, segments: list[dict]) -> None:
        turns = transcribe.merge_turns(segments)
        # Output is time-ordered.
        starts = [t["start"] for t in turns]
        assert starts == sorted(starts)
        # Boundary-echo de-duplication may drop repeated segments, but words are
        # never invented or reordered: output is a subsequence of the input words.
        ordered = sorted(segments, key=lambda s: s["start"])
        expected = " ".join(s["text"] for s in ordered).split()
        got = " ".join(t["text"] for t in turns).split()
        it = iter(expected)
        assert all(word in it for word in got)
        # Turns never exceed segments; each turn is well-formed.
        assert len(turns) <= len(segments)
        for t in turns:
            assert t["start"] <= t["end"]


class TestDiarizeProperties:
    @settings(max_examples=150)
    @given(
        st.lists(_segment(), max_size=30),
        st.lists(
            st.builds(
                lambda a, d, n: SpeakerTurn(a, a + d, f"Speaker {n}"),
                times,
                st.floats(min_value=0, max_value=30, allow_nan=False, allow_infinity=False),
                st.integers(min_value=0, max_value=5),
            ),
            max_size=10,
        ),
    )
    def test_assignment_invariants(self, segments: list[dict], turns: list[SpeakerTurn]) -> None:
        out = diarize.assign_speakers(segments, turns)
        assert len(out) == len(segments)
        for original, result in zip(segments, out, strict=True):
            if original["speaker"] != "sys" or not turns:
                assert "sub_speaker" not in result
            elif "sub_speaker" in result:
                # A label was assigned only when a turn actually overlaps.
                assert result["sub_speaker"] in {t.speaker for t in turns}


class TestFtsQueryFuzz:
    @settings(max_examples=250)
    @given(st.text())
    def test_arbitrary_text_never_breaks_fts(self, query: str) -> None:
        # The sanitizer must make ANY user text safe for an FTS5 MATCH — this is
        # the property that the `?`/`:`/`*` crash class can never come back.
        match = notes._fts_query(query)
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE VIRTUAL TABLE notes USING fts5(title, date, path, body)")
            con.execute("INSERT INTO notes VALUES (?,?,?,?)", ("t", "d", "p", "hello world"))
            if match:  # empty query → search() returns [] without touching SQLite
                con.execute("SELECT * FROM notes WHERE notes MATCH ?", (match,)).fetchall()
        finally:
            con.close()


class TestDocsRequestsProperties:
    @settings(max_examples=150)
    @given(st.text(max_size=500), st.text(max_size=60))
    def test_indices_within_bounds(self, body: str, title: str) -> None:
        build = mdconvert.to_docs_requests(body, title=title)
        assert build.text.endswith("\n")
        limit = len(build.text) + 1
        for req in build.requests:
            rng = next(iter(req.values()))["range"]
            assert 1 <= rng["startIndex"] < rng["endIndex"] <= limit


class TestSlugifyProperties:
    @settings(max_examples=150)
    @given(st.text(), st.integers(min_value=1, max_value=60))
    def test_slug_shape(self, text: str, max_len: int) -> None:
        slug = notes.slugify(text, max_len=max_len)
        assert slug  # never empty
        assert len(slug) <= max_len
        assert re.fullmatch(r"[a-z0-9-]+", slug)
        assert not slug.startswith("-") and not slug.endswith("-")


class TestFormattingProperties:
    @settings(max_examples=80)
    @given(st.one_of(st.none(), st.floats(min_value=0, max_value=1e9, allow_nan=False)))
    def test_format_duration_never_crashes(self, seconds: float | None) -> None:
        assert isinstance(notes.format_duration(seconds), str)

    @settings(max_examples=80)
    @given(st.floats(min_value=0, max_value=1e7, allow_nan=False, allow_infinity=False))
    def test_timestamp_shape(self, seconds: float) -> None:
        assert re.fullmatch(r"\d+:\d{2}(:\d{2})?", transcribe._timestamp(seconds))


class TestChunkWriterProperties:
    @settings(max_examples=120)
    @given(st.lists(st.integers(min_value=0, max_value=4000), max_size=25), st.integers(1, 4))
    def test_frame_accounting_and_contiguity(
        self, frame_counts: list[int], chunk_seconds: int
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            writer = ChunkWriter("mic", Path(tmp), chunk_seconds=chunk_seconds)
            total = 0
            for n in frame_counts:
                writer.append(b"\x00\x00" * n)  # n int16 frames
                total += n
            writer.close_chunk()
            entries = transcribe.read_manifest(Path(tmp))
            # Manifest spans are contiguous and sum to everything written.
            # (Manifest times are rounded to 3 decimals, so compare within 1e-3.)
            prev_end = 0.0
            for e in entries:
                assert abs(e["start"] - prev_end) < 1e-3
                prev_end = e["end"]
            assert abs(prev_end - total / SAMPLE_RATE) < 1e-3


class TestEnsureMetaProperties:
    @settings(max_examples=80)
    @given(st.text(max_size=200), st.lists(times, max_size=10))
    def test_always_produces_valid_meta(self, session_json: str, ends: list[float]) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "session.json").write_text(session_json)  # often invalid JSON on purpose
            manifest = "".join(
                f'{{"stream":"sys","file":"s.wav","start":0,"end":{e}}}\n' for e in ends
            )
            (d / "manifest.jsonl").write_text(manifest)
            meta = recorder.ensure_meta(d)
            for key in ("title", "started_at", "duration_s", "session_dir"):
                assert key in meta
            assert meta["duration_s"] >= 0
