"""Measure transcription accuracy (Word Error Rate) on known-text speech.

Synthesizes reference sentences with macOS `say`, runs them through the real
transcription pipeline (chunked, with cross-chunk context + hallucination
filtering), and reports WER. Lower is better; <10% is strong for real speech.

Usage: uv run python scripts/accuracy_bench.py [--model mlx-community/whisper-large-v3-turbo]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REFERENCE = [
    "The quarterly revenue grew eleven percent to four point two million dollars.",
    "Let's schedule the architecture review for Tuesday afternoon with the platform team.",
    "We decided to postpone the database migration until after the security audit.",
    "Maya will send the press release draft to marketing by Friday at the latest.",
    "Our biggest risk is the payment provider integration slipping into next quarter.",
]


_WORD2NUM = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}


def _normalize(text: str) -> list[str]:
    """Content-level tokens: drop $/% symbols and punctuation, map small number
    words to digits, so '11%' ~ 'eleven percent' isn't scored as a transcription
    error (Whisper's numeral formatting differs from the spoken words)."""
    text = text.lower().replace("%", "").replace("$", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return [_WORD2NUM.get(w, w) for w in text.split() if w != "point"]


def _wer(reference: str, hypothesis: str) -> float:
    ref, hyp = _normalize(reference), _normalize(hypothesis)
    # Levenshtein distance over words.
    dp = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, dp[0] = dp[0], i
        for j, h in enumerate(hyp, 1):
            cur = dp[j]
            dp[j] = prev if r == h else 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[len(hyp)] / max(1, len(ref))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from meetingbot import transcribe

    reference = " ".join(REFERENCE)
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "ref.aiff"
        wav = Path(tmp) / "ref.wav"
        subprocess.run(["say", "-o", str(aiff), reference], check=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
            check=True,
        )
        with wave.open(str(wav), "rb") as w:
            duration = w.getnframes() / w.getframerate()

        audio = transcribe.load_wav(wav)
        segments = transcribe._transcribe_array(
            audio, args.model or transcribe.config.WHISPER_MODEL
        )
        hypothesis = " ".join(s["text"] for s in segments)

    wer = _wer(reference, hypothesis)
    print(f"audio: {duration:.1f}s   model: {args.model or transcribe.config.WHISPER_MODEL}")
    print(f"reference:  {reference}")
    print(f"hypothesis: {hypothesis.strip()}")
    print(f"\nWord Error Rate: {wer * 100:.1f}%  ({'PASS' if wer < 0.10 else 'review'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
