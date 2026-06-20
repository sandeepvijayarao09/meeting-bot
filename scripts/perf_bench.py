"""End-to-end performance benchmark for Meeting Bot.

Measures the two costs that decide how fast a note appears after you hit Stop:

  1. Local transcription throughput (real-time factor) — synthesizes speech with
     macOS `say` and times the warm transcription pass.
  2. NIM summarization latency — times a real summary call on a synthetic
     transcript and reports wall time + token usage. Skipped without an API key.

Usage: uv run python scripts/perf_bench.py [--model ...] [--no-summary]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# A short, content-rich meeting used for the summary timing.
TRANSCRIPT_TURNS = [
    ("the Q3 roadmap", "ship the billing rewrite", "Maria", "July 15"),
    ("the enterprise SSO request", "scope SAML support", "Raj", "next Tuesday"),
    ("the pricing experiment", "launch the 3-tier test", "Growth", "Monday"),
    ("the on-call rotation", "rebalance the schedule", "Priya", "this week"),
]


def _build_transcript() -> str:
    turns: list[str] = []
    for topic, decision, owner, due in TRANSCRIPT_TURNS:
        turns += [
            f"Me: Let's talk about {topic}. Where are we?",
            f"Them: Progress but risks — testing coverage and a data-team "
            f"dependency. We can {decision} if we move now.",
            f"Me: I want to {decision}. Can {owner} own it by {due}?",
            f"Them: Yes, {owner} owns it, target {due}. Open question: design review first?",
            "Me: Heads-up to design, don't block. Budget is 40 thousand, down from 55.",
        ]
    return "\n".join(turns)


def _synth_wav(text: str, path: Path) -> float:
    aiff = path.with_suffix(".aiff")
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(path)],
        check=True,
    )
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _bench_transcription(model: str) -> None:
    from meetingbot import transcribe

    print("── transcription (local) ──────────────────────────────")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        sentence = "This is a benchmark of the local transcription pipeline speed. " * 6
        duration = _synth_wav(sentence, wav)
        audio = transcribe.load_wav(wav)

        t0 = time.time()
        transcribe._transcribe_array(audio, model)
        cold = time.time() - t0

        t0 = time.time()
        segs = transcribe._transcribe_array(audio, model)
        warm = time.time() - t0

    print(f"model:           {model}")
    print(f"audio duration:  {duration:.1f}s")
    print(f"cold (load+run): {cold:.1f}s")
    print(
        f"warm:            {warm:.2f}s  ->  RTF {warm / duration:.3f}x "
        f"({duration / warm:.0f}x faster than real time)  segs={len(segs)}"
    )


def _bench_summary() -> None:
    from meetingbot import config, summarize

    print("\n── summarization (NVIDIA NIM) ─────────────────────────")
    if not summarize.have_key():
        print("skipped: NVIDIA_API_KEY not set")
        return

    transcript = _build_transcript()
    print(f"model:        {config.NIM_MODEL}")
    print(f"reasoning:    {config.NIM_REASONING}")
    print(f"transcript:   {len(transcript)} chars (~{len(transcript.split())} words)")

    t0 = time.time()
    note = summarize.summarize_meeting(
        transcript, title="Leadership sync", date="2026-06-20", duration="20 min"
    )
    elapsed = time.time() - t0
    print(f"latency:      {elapsed:.1f}s")
    print(f"note length:  {len(note)} chars")
    print(f"sections:     {[ln[3:] for ln in note.splitlines() if ln.startswith('## ')]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Whisper model override")
    parser.add_argument("--no-summary", action="store_true", help="skip the NIM call")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from meetingbot import config

    _bench_transcription(args.model or config.WHISPER_MODEL)
    if not args.no_summary:
        _bench_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
