"""Benchmark every supported Whisper model on synthesized speech.

Measures transcription speed and keyword accuracy so you can pick the right
MBOT_WHISPER_MODEL for your machine. Run: uv run python scripts/model_matrix.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODELS = [
    "mlx-community/whisper-tiny",
    "mlx-community/whisper-base-mlx",
    "mlx-community/whisper-small-mlx",
    "mlx-community/whisper-medium-mlx",
    "mlx-community/whisper-large-v3-turbo",
]

SENTENCES = [
    "The quarterly revenue grew eleven percent to four point two million dollars.",
    "Schedule the architecture review for Tuesday afternoon with the platform team.",
    "We decided to postpone the database migration until after the security audit.",
]

# Each entry is a set of acceptable spellings ("eleven" is correctly written "11%").
KEYWORDS: list[tuple[str, ...]] = [
    ("quarterly",),
    ("revenue",),
    ("eleven", "11"),
    ("million",),
    ("architecture",),
    ("review",),
    ("tuesday",),
    ("platform",),
    ("postpone",),
    ("database",),
    ("migration",),
    ("security",),
    ("audit",),
]


def make_fixture(directory: Path) -> Path:
    aiff = directory / "fixture.aiff"
    wav = directory / "fixture.wav"
    subprocess.run(["say", "-o", str(aiff), " ".join(SENTENCES)], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
        check=True,
    )
    return wav


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import mlx_whisper

    from meetingbot.transcribe import load_wav

    with tempfile.TemporaryDirectory() as tmp:
        wav = make_fixture(Path(tmp))
        audio = load_wav(wav)
        duration = len(audio) / 16000
        results = []
        for model in MODELS:
            try:
                # Cold run includes model download (if uncached) + weight loading;
                # warm run is the steady-state speed that matters for live use.
                t0 = time.perf_counter()
                mlx_whisper.transcribe(
                    audio, path_or_hf_repo=model, condition_on_previous_text=False, verbose=None
                )
                cold = time.perf_counter() - t0
                t0 = time.perf_counter()
                out = mlx_whisper.transcribe(
                    audio, path_or_hf_repo=model, condition_on_previous_text=False, verbose=None
                )
                warm = time.perf_counter() - t0
            except Exception as e:
                results.append({"model": model, "error": str(e)})
                continue
            text = out["text"].lower()
            hits = [k for k in KEYWORDS if any(alt in text for alt in k)]
            results.append(
                {
                    "model": model,
                    "cold_seconds": round(cold, 2),
                    "warm_seconds": round(warm, 2),
                    "warm_x_realtime": round(duration / warm, 1),
                    "keyword_accuracy": f"{len(hits)}/{len(KEYWORDS)}",
                    "missed": [k[0] for k in KEYWORDS if k not in hits],
                    "text": out["text"].strip(),
                }
            )
            print(json.dumps(results[-1], indent=2))

    print(f"\n=== SUMMARY (audio length: {duration:.1f}s) ===")
    for r in results:
        if "error" in r:
            print(f"{r['model']:<45} ERROR: {r['error']}")
        else:
            print(
                f"{r['model']:<45} cold {r['cold_seconds']:>6.2f}s  "
                f"warm {r['warm_seconds']:>6.2f}s ({r['warm_x_realtime']}x realtime)  "
                f"keywords {r['keyword_accuracy']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
