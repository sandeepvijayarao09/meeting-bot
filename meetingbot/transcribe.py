"""Local transcription with mlx-whisper, merging mic/system streams into one transcript.

The session dir contains chunked WAVs plus manifest.jsonl written by audiocap.
Each transcribed segment lands in transcript.jsonl as:
    {"start": <s>, "end": <s>, "speaker": "mic"|"sys", "text": "..."}
with start/end in seconds since session start (chunk offset + in-chunk time).
"""

import json
import re
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from . import config

SAMPLE_RATE = 16000  # capture + WAV rate; what Whisper and diarization expect

# Cross-chunk continuity: feed the tail of the prior transcript (per speaker) as
# Whisper's initial_prompt so words and proper nouns survive 30 s chunk boundaries.
CONTEXT_CHARS = 200

# Whisper hallucination signals (mirror openai-whisper's own thresholds): very
# low confidence or highly repetitive output, plus the canonical filler phrases
# Whisper emits over silence/music. These get dropped before they reach the note.
_MIN_AVG_LOGPROB = -1.0
_MAX_COMPRESSION_RATIO = 2.4
_HALLUCINATION_PHRASES = {
    "thank you",
    "thank you very much",
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subscribe to my channel",
    "see you next time",
    "see you in the next video",
    "bye",
    "you",
}
SILENCE_RMS = 0.0030  # 16-bit speech is well above this; skips dead air cheaply


def load_wav(path: Path) -> np.ndarray[Any, np.dtype[np.float32]]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f"{path}: expected 16-bit mono WAV")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def is_silent(audio: np.ndarray[Any, np.dtype[np.float32]]) -> bool:
    if audio.size == 0:
        return True
    return float(np.sqrt(np.mean(audio**2))) < SILENCE_RMS


def read_manifest(session_dir: Path) -> list[dict[str, Any]]:
    manifest = session_dir / "manifest.jsonl"
    if not manifest.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def load_segments(session_dir: Path) -> list[dict[str, Any]]:
    transcript = session_dir / "transcript.jsonl"
    if not transcript.exists():
        return []
    segments: list[dict[str, Any]] = []
    for line in transcript.read_text().splitlines():
        line = line.strip()
        if line:
            segments.append(json.loads(line))
    return segments


def _processed_chunks(session_dir: Path) -> set[str]:
    return {s["chunk"] for s in load_segments(session_dir) if "chunk" in s}


def _clean_segments(raw_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop empty, low-confidence, repetitive, and hallucinated segments.

    Pure function (testable). Missing confidence fields default to "keep" so this
    only ever removes output Whisper itself flags as unreliable.
    """
    cleaned: list[dict[str, Any]] = []
    for seg in raw_segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        no_speech = seg.get("no_speech_prob", 0.0)
        if no_speech > 0.6:
            continue
        if seg.get("avg_logprob", 0.0) < _MIN_AVG_LOGPROB:
            continue
        if seg.get("compression_ratio", 0.0) > _MAX_COMPRESSION_RATIO:
            continue
        normalized = re.sub(r"[^a-z ]", "", text.lower()).strip()
        if normalized in _HALLUCINATION_PHRASES and no_speech > 0.2:
            continue
        cleaned.append({"start": seg["start"], "end": seg["end"], "text": text})
    return cleaned


def _transcribe_array(
    audio: np.ndarray[Any, np.dtype[np.float32]], model: str, initial_prompt: str = ""
) -> list[dict[str, Any]]:
    import mlx_whisper  # heavy import; keep it lazy

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt or None,
        verbose=None,
    )
    return _clean_segments(result.get("segments", []))


def transcribe_entry(
    session_dir: Path, entry: dict[str, Any], model: str, initial_prompt: str = ""
) -> list[dict[str, Any]]:
    """Transcribe one manifest chunk; returns absolute-time segments."""
    path = session_dir / entry["file"]
    if not path.exists():
        return []
    audio = load_wav(path)
    if is_silent(audio):
        return []
    offset = float(entry["start"])
    return [
        {
            "start": round(offset + s["start"], 2),
            "end": round(offset + s["end"], 2),
            "speaker": entry["stream"],
            "text": s["text"],
            "chunk": entry["file"],
        }
        for s in _transcribe_array(audio, model, initial_prompt=initial_prompt)
    ]


def _seed_context(session_dir: Path) -> dict[str, str]:
    """Build per-speaker context tails from already-transcribed segments."""
    context: dict[str, str] = {}
    for seg in load_segments(session_dir):
        speaker = seg.get("speaker", "")
        tail = context.get(speaker, "") + " " + seg.get("text", "")
        context[speaker] = tail[-CONTEXT_CHARS:].strip()
    return context


def transcribe_session(
    session_dir: Path,
    model: str | None = None,
    follow: bool = False,
    stop_event: threading.Event | None = None,
    on_segment: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Transcribe all unprocessed manifest chunks; append to transcript.jsonl.

    With follow=True, keeps polling the manifest until stop_event is set AND
    everything written so far has been processed (call after audiocap exits).
    """
    session_dir = Path(session_dir)
    model = model or config.WHISPER_MODEL
    transcript_path = session_dir / "transcript.jsonl"
    done = _processed_chunks(session_dir)
    # Per-speaker running context fed as Whisper's initial_prompt (continuity
    # across chunk boundaries). Seed from any already-processed segments so a
    # resumed transcription keeps its context too.
    context = _seed_context(session_dir)

    while True:
        pending = [e for e in read_manifest(session_dir) if e["file"] not in done]
        for entry in pending:
            stream = entry["stream"]
            segments = transcribe_entry(
                session_dir, entry, model, initial_prompt=context.get(stream, "")
            )
            with transcript_path.open("a") as f:
                for seg in segments:
                    f.write(json.dumps(seg) + "\n")
                    if on_segment:
                        on_segment(seg)
            if segments:
                tail = context.get(stream, "") + " " + " ".join(s["text"] for s in segments)
                context[stream] = tail[-CONTEXT_CHARS:].strip()
            done.add(entry["file"])
        if not follow:
            break
        if stop_event is not None and stop_event.is_set() and not pending:
            break
        time.sleep(0.5)


class LiveTranscriber:
    """Transcribes chunks in a background thread while the meeting records."""

    def __init__(
        self,
        session_dir: Path,
        model: str | None = None,
        on_segment: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.model = model or config.WHISPER_MODEL
        self.on_segment = on_segment
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        transcribe_session(
            self.session_dir,
            model=self.model,
            follow=True,
            stop_event=self._stop,
            on_segment=self.on_segment,
        )

    def finish(self) -> None:
        """Call after audiocap has exited; waits for remaining chunks."""
        self._stop.set()
        self._thread.join()


def _speaker_label(seg: dict[str, Any]) -> str:
    """Display label for a segment, including a diarized sub-speaker if present."""
    base = config.SPEAKER_LABELS.get(seg["speaker"], seg["speaker"])
    sub = seg.get("sub_speaker")
    return f"{base} · {sub}" if sub else base


def _dedupe(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop consecutive same-speaker segments with identical text — these are
    chunk-boundary echoes caused by feeding prior text as Whisper's context."""
    out: list[dict[str, Any]] = []
    last: dict[str, str] = {}
    for seg in ordered:
        norm = " ".join(seg.get("text", "").lower().split())
        if norm and last.get(seg.get("speaker", "")) == norm:
            continue
        last[seg.get("speaker", "")] = norm
        out.append(seg)
    return out


def merge_turns(segments: list[dict[str, Any]], max_gap: float = 2.0) -> list[dict[str, Any]]:
    """Sort segments from both streams by time and coalesce into speaker turns."""
    ordered = _dedupe(sorted(segments, key=lambda s: s["start"]))
    turns: list[dict[str, Any]] = []
    for seg in ordered:
        speaker = _speaker_label(seg)
        if turns and turns[-1]["speaker"] == speaker and seg["start"] - turns[-1]["end"] <= max_gap:
            turns[-1]["text"] += " " + seg["text"]
            turns[-1]["end"] = seg["end"]
        else:
            turns.append(
                {
                    "speaker": speaker,
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"],
                }
            )
    return turns


def _timestamp(seconds: float) -> str:
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def format_transcript(turns: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"**{t['speaker']}** [{_timestamp(t['start'])}]: {t['text']}" for t in turns)
