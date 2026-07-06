"""Eloquent-style transcript refinement — turn messy speech-to-text into clean prose.

Mirrors Google AI Edge Eloquent's pipeline: an always-on, deterministic on-device
cleanup (strip fillers, collapse false starts and stutters, fix punctuation and
capitalization), with an optional cloud polish pass for richer prose.

Two tiers, selected by ``config.REFINE`` (overridable per call):
    off   — raw merged transcript, no cleanup (legacy behavior).
    local — deterministic, offline, $0 cleanup (the default). Pure functions.
    cloud — local cleanup THEN an NIM polish pass; falls back to local on any
            failure (missing key, network error) so it never blocks note creation.

The raw ``transcript.jsonl`` is always preserved verbatim — refinement is derived
and recomputable, and operates only on the merged turns' text (speaker and
timestamps are carried through untouched).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from . import config, summarize, transcribe

log = logging.getLogger(__name__)

# --- Tier 1: offline rule-based cleaner (pure functions) ---------------------

# Standalone vocalized fillers ("um", "uhh", "erm", "hmm", "mm", "mhm", "ah").
# Anchored on word boundaries so they never bite into real words ("ahead", "err").
_FILLER_RE = re.compile(r"\b(?:u+m+|u+h+|erm?|ehm?|mm+|m*hm+|ah+)\b", re.IGNORECASE)

# Discourse-marker fillers, only stripped when comma-delimited, so content words
# are never touched (e.g. the verb "like" in "I like it" has no trailing comma).
_LEADING_DISCOURSE_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:so|well|you know|i mean|like|okay|ok)\s*,\s*",
    re.IGNORECASE,
)
_EMBEDDED_DISCOURSE_RE = re.compile(r"\s*,\s*(?:you know|i mean)\s*,\s*", re.IGNORECASE)

# Immediate word- and short-phrase repetitions ("the the", "I think I think").
_WORD_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)
_PHRASE_REPEAT_RE = re.compile(r"\b(\w+(?:\s+\w+){1,2})\s+\1\b", re.IGNORECASE)

# Self-interruptions: a SHORT abandoned fragment (≤3 words) ending in a dash/ellipsis
# that is immediately restarted ("I think— I believe we ship" -> "I believe we ship").
# Kept short on purpose: a long lead-in before a "..." pause is real content, not a
# false start, so we must not swallow it ("the plan looks good ... good" is preserved).
_FALSE_START_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:\w+\s+){0,2}\w+(?:—|--|…|\.\.\.)\s+",
)

# Whitespace / punctuation tidy patterns, precompiled like the ones above — these
# run on every cleanup step, up to _MAX_PASSES times per turn.
_WS_RE = re.compile(r"\s+")
_COMMA_RUN_RE = re.compile(r"\s*,(?:\s*,)+")
_LEADING_JUNK_RE = re.compile(r"^[\s,]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")
_COMMA_SPACE_RE = re.compile(r",(?=[^\s\d])")
_MULTISPACE_RE = re.compile(r"\s{2,}")
_STANDALONE_I_RE = re.compile(r"\bi\b")
_SENTENCE_START_RE = re.compile(r"(^\s*|[.!?]\s+)([a-z])")


def strip_fillers(text: str) -> str:
    """Remove vocalized fillers and comma-delimited discourse markers."""
    text = _FILLER_RE.sub(" ", text)
    # Normalize whitespace first so the leading-discourse "^" anchor sees the real
    # clause start (filler removal can leave stray leading spaces).
    text = _WS_RE.sub(" ", text).strip()
    # Iterate to a fixpoint. Tidying the clause start (stray leading commas/spaces)
    # and collapsing comma runs happen INSIDE the loop, before discourse removal, so
    # a marker exposed by tidying (", okay," -> "okay," -> "") or chained markers
    # ("so, well, ...") are fully removed in one call — which keeps clean_text idempotent.
    prev = ""
    while prev != text:
        prev = text
        text = _COMMA_RUN_RE.sub(",", text)  # collapse comma runs
        text = _LEADING_JUNK_RE.sub("", text)  # strip leading commas/spaces
        text = _EMBEDDED_DISCOURSE_RE.sub(", ", text)
        text = _LEADING_DISCOURSE_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip()


def collapse_repetitions(text: str) -> str:
    """Collapse immediate stutters: "the the" -> "the", "I think I think" -> "I think"."""
    text = _WORD_REPEAT_RE.sub(r"\1", text)
    prev = ""
    while prev != text:  # iterate to a fixpoint for chained phrase repeats
        prev = text
        text = _PHRASE_REPEAT_RE.sub(r"\1", text)
    return text


def collapse_false_starts(text: str) -> str:
    """Drop a short abandoned fragment before a dash/ellipsis self-correction."""
    return _FALSE_START_RE.sub("", text)


def fix_spacing_punctuation(text: str) -> str:
    """Remove spaces before punctuation, ensure one after a comma, collapse runs."""
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _COMMA_SPACE_RE.sub(", ", text)  # space after comma, but keep "1,000"
    text = _MULTISPACE_RE.sub(" ", text)
    return text.strip()


def polish_capitalization(text: str) -> str:
    """Uppercase the standalone pronoun "i" and the first letter of each sentence."""
    text = _STANDALONE_I_RE.sub("I", text)
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


# Order matters and is locked by tests: fillers/stutters first, then normalize
# punctuation spacing, THEN false-start detection (so it sees canonical "word..."
# forms — running it before spacing would miss them and break idempotence),
# capitalization last.
_STEPS = (
    strip_fillers,
    collapse_repetitions,
    fix_spacing_punctuation,
    collapse_false_starts,
    polish_capitalization,
)


# Safety cap on the fixpoint iteration. The transforms only remove or normalize, so
# they converge in 1-2 passes; this just bounds pathological inputs. The fixpoint is
# what makes clean_text idempotent (verified by a property test over 1000 inputs).
_MAX_PASSES = 6


def clean_text(text: str) -> str:
    """Run the offline transforms to a fixpoint, in a fixed, tested order.

    Pure and idempotent: ``clean_text(clean_text(x)) == clean_text(x)``.
    """
    for _ in range(_MAX_PASSES):
        cleaned = text
        for step in _STEPS:
            cleaned = step(cleaned)
        cleaned = cleaned.strip()
        if cleaned == text:
            break
        text = cleaned
    return text


def clean_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean each turn's text; preserve speaker/start/end; drop now-empty turns."""
    cleaned: list[dict[str, Any]] = []
    for turn in turns:
        text = clean_text(str(turn.get("text") or ""))
        if text:
            cleaned.append({**turn, "text": text})
    return cleaned


# --- Tier 2: optional cloud polish (reuses the NIM plumbing in summarize) -----

REFINE_SYSTEM = (
    "You clean up a speech-to-text meeting transcript. Remove filler words, false "
    "starts, and stutters, and fix punctuation and capitalization. Keep EVERY fact, "
    "name, number, and the speaker's exact meaning — never add, summarize, reorder, "
    "or invent content. Preserve the '**Speaker** [mm:ss]: text' line structure "
    "exactly. Output only the cleaned transcript."
)


def polish_cloud(transcript_md: str) -> str:
    """NIM polish over an already-locally-cleaned Markdown transcript.

    Map-reduces over-long transcripts on line boundaries (mirrors summarize), so
    the per-turn ``**Speaker** [mm:ss]:`` structure is preserved across pieces.
    """
    if len(transcript_md) > summarize.MAX_DIRECT_CHARS:
        pieces = summarize._split_on_lines(transcript_md, summarize.PIECE_CHARS)
    else:
        pieces = [transcript_md]
    polished = [
        summarize.complete(REFINE_SYSTEM, piece, max_tokens=4096, temperature=0.1)
        for piece in pieces
    ]
    return "\n\n".join(part.strip() for part in polished).strip()


def noncloud_tier() -> str:
    """The configured tier, but never "cloud" — for secondary operations (note
    re-export, prepping transform input) that must not trigger a billable cloud
    refine. Returns "off" or "local"."""
    return "local" if config.REFINE == "cloud" else config.REFINE


def refine_transcript(session_dir: Path, tier: str | None = None) -> str:
    """Derive the refined Markdown transcript for a finished session.

    ``tier`` defaults to ``config.REFINE``. "cloud" degrades gracefully to the
    locally-cleaned text when there is no API key or the request fails, so a
    refinement problem can never block note creation.
    """
    tier = (tier or config.REFINE).lower()
    turns = transcribe.merge_turns(transcribe.load_segments(session_dir))
    if tier == "off":
        return transcribe.format_transcript(turns)
    local_md = transcribe.format_transcript(clean_turns(turns))
    if tier == "cloud" and local_md and summarize.have_key():
        try:
            return polish_cloud(local_md)
        except Exception as e:  # network/API/key failure -> local-cleaned fallback
            log.warning("cloud refine failed (%s); using local-cleaned transcript", e)
    return local_md
