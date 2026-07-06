"""Eloquent-style text tools — discrete transformations over a meeting's transcript.

Mirrors Google AI Edge Eloquent's text transformations: take cleaned transcript text
and reshape it on demand into one of four forms:
    key_points — the substantive takeaways as a bullet list
    formal     — formal, professional prose
    short      — a few-sentence summary
    long       — detailed, structured minutes

Each is one NIM round trip (map-reduced for marathon transcripts), reusing the
plumbing in :mod:`summarize`. Generative rewrites, so these require the API key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from . import config, summarize

TRANSFORMS: Final[tuple[str, ...]] = ("key_points", "formal", "short", "long")

TRANSFORM_SYSTEM = (
    "You transform meeting text exactly as instructed. Use ONLY facts present in the "
    "source; never invent names, numbers, or details. Output Markdown only, with no "
    "preamble."
)


def _template_path(kind: str) -> Path:
    return config.PROMPTS_DIR / "transforms" / f"{kind}.md"


def transform(text: str, kind: str) -> str:
    """Run one text transformation over ``text``. Requires the NIM API key.

    Over-long input is map-reduced first (condense pieces, then transform the
    condensed text), mirroring :func:`summarize.summarize_meeting`.
    """
    if kind not in TRANSFORMS:
        raise ValueError(f"unknown transform {kind!r}; choose from {', '.join(TRANSFORMS)}")
    if not summarize.have_key():
        raise summarize.MissingAPIKeyError(
            "NVIDIA_API_KEY is not set. Get a free key at https://build.nvidia.com "
            "and put it in ~/.config/meetingbot/.env"
        )
    text = summarize.condense_if_long(text)
    prompt = summarize._fill(_template_path(kind).read_text(), TEXT=text)
    return summarize.complete(TRANSFORM_SYSTEM, prompt)
