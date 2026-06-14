"""Optional speaker diarization for the system-audio ("Them") stream.

The base pipeline labels everyone-else as a single "Them". With diarization on
(MBOT_DIARIZE=1), we run pyannote on the combined system-audio WAVs to find who-
spoke-when, then tag each "Them" transcript segment with the speaker whose turn
overlaps it most → "Them · Speaker A", "Them · Speaker B", …

pyannote weights are gated: set HF_TOKEN (a free Hugging Face token, after
accepting the model terms) for the first download. Diarization is local thereafter.
Disabled by default — it adds a heavy model and noticeable processing time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import transcribe


def enabled() -> bool:
    return os.environ.get("MBOT_DIARIZE", "").strip() in ("1", "true", "yes")


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str  # e.g. "Speaker A"


class Diarizer(Protocol):
    def __call__(self, wav_paths: list[Path]) -> list[SpeakerTurn]: ...


def _letter(index: int) -> str:
    # 0 -> A, 1 -> B, … 25 -> Z, 26 -> AA
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def assign_speakers(
    segments: list[dict[str, Any]], turns: list[SpeakerTurn], stream: str = "sys"
) -> list[dict[str, Any]]:
    """Attach a `sub_speaker` to each `stream` segment by max temporal overlap.

    Pure function (no model) so it is fully unit-testable. Segments of other
    streams (the mic) pass through unchanged.
    """
    out: list[dict[str, Any]] = []
    for seg in segments:
        if seg.get("speaker") != stream or not turns:
            out.append(seg)
            continue
        best = max(
            turns,
            key=lambda t: max(0.0, min(seg["end"], t.end) - max(seg["start"], t.start)),
        )
        overlap = max(0.0, min(seg["end"], best.end) - max(seg["start"], best.start))
        out.append({**seg, "sub_speaker": best.speaker} if overlap > 0 else seg)
    return out


def _pyannote_diarizer(wav_paths: list[Path]) -> list[SpeakerTurn]:  # pragma: no cover
    """Real diarizer: concatenate the system WAVs and run pyannote. Heavy import."""
    import numpy as np
    import torch
    from pyannote.audio import Pipeline

    token = os.environ.get("HF_TOKEN")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    audio = np.concatenate([transcribe.load_wav(p) for p in wav_paths])
    waveform = torch.from_numpy(audio).unsqueeze(0)
    annotation = pipeline({"waveform": waveform, "sample_rate": transcribe.SAMPLE_RATE})

    labels: dict[str, str] = {}
    turns: list[SpeakerTurn] = []
    for segment, _, label in annotation.itertracks(yield_label=True):
        if label not in labels:
            labels[label] = f"Speaker {_letter(len(labels))}"
        turns.append(SpeakerTurn(segment.start, segment.end, labels[label]))
    return turns


def diarize_session(session_dir: Path, diarizer: Diarizer | None = None) -> int:
    """Rewrite transcript.jsonl with per-speaker labels on the system stream.

    Returns the number of distinct speakers found. `diarizer` is injectable for
    testing; defaults to the real pyannote pipeline.
    """
    session_dir = Path(session_dir)
    segments = transcribe.load_segments(session_dir)
    sys_chunks = sorted(
        {s["chunk"] for s in segments if s.get("speaker") == "sys" and "chunk" in s}
    )
    wav_paths = [session_dir / name for name in sys_chunks if (session_dir / name).exists()]
    if not wav_paths:
        return 0

    run = diarizer or _pyannote_diarizer
    turns = run(wav_paths)
    labeled = assign_speakers(segments, turns)

    import json

    transcript_path = session_dir / "transcript.jsonl"
    transcript_path.write_text("".join(json.dumps(s) + "\n" for s in labeled))
    return len({t.speaker for t in turns})
