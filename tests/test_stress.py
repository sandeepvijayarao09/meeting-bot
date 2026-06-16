"""Stress harness: run the real session pipeline across 1000 randomized cases.

Each case builds a synthetic session (random chunk layout, speakers, silence,
diarization on/off) and runs transcribe → merge → finalize end-to-end with the
Whisper model mocked, asserting invariants and that a note is always produced.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from meetingbot import config, diarize, recorder, transcribe
from meetingbot.diarize import SpeakerTurn

CASES = 1000


def _random_session(rng: random.Random, root: Path, idx: int) -> Path:
    session = root / f"s{idx:04d}"
    session.mkdir(parents=True, exist_ok=True)
    n_chunks = rng.randint(0, 6)
    manifest, segments, t = [], [], 0.0
    for c in range(n_chunks):
        stream = rng.choice(["mic", "sys", "sys"])
        dur = rng.uniform(0.5, 30.0)
        fname = f"{stream}-{c:04d}.wav"
        (session / fname).write_bytes(b"")  # presence only; diarizer is mocked
        manifest.append(
            {"stream": stream, "file": fname, "start": round(t, 2), "end": round(t + dur, 2)}
        )
        # Some chunks are silent (no segments); others yield 1-3 lines.
        if rng.random() > 0.25:
            for _ in range(rng.randint(1, 3)):
                segments.append(
                    {
                        "start": round(t + rng.uniform(0, dur), 2),
                        "end": round(t + dur, 2),
                        "speaker": stream,
                        "text": rng.choice(["hello", "okay let's ship", "agreed", "next item", ""]),
                        "chunk": fname,
                    }
                )
        t += dur
    (session / "manifest.jsonl").write_text("".join(json.dumps(m) + "\n" for m in manifest))
    (session / "transcript.jsonl").write_text("".join(json.dumps(s) + "\n" for s in segments))
    (session / "session.json").write_text(json.dumps({"started_at": "2026-06-14T10:00:00"}))
    return session


@pytest.mark.stress
def test_pipeline_survives_1000_random_sessions(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng = random.Random(20260614)
    # Mock the diarizer so "diarize on" cases exercise the merge path without pyannote.
    monkeypatch.setattr(
        diarize, "_pyannote_diarizer", lambda paths: [SpeakerTurn(0.0, 1e6, "Speaker A")]
    )

    notes_made = 0
    for idx in range(CASES):
        session = _random_session(rng, config.SESSIONS_DIR, idx)
        recorder.ensure_meta(session)
        if rng.random() < 0.5:
            monkeypatch.setenv("MBOT_DIARIZE", "1")
        else:
            monkeypatch.delenv("MBOT_DIARIZE", raising=False)

        # No API key in the isolated fixture → placeholder summary, note still written.
        note_path, summarized = recorder.finalize_session(session, want_summary=True)
        assert note_path.exists()
        assert not summarized

        # Invariant: the merged transcript is time-ordered.
        turns = transcribe.merge_turns(transcribe.load_segments(session))
        starts = [t["start"] for t in turns]
        assert starts == sorted(starts)
        notes_made += 1

    assert notes_made == CASES
