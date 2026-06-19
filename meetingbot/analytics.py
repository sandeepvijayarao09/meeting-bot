"""Talk-time analytics for a meeting (Me/Them ratio, words, longest monologue).

Computed locally from the merged transcript turns — no extra model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import transcribe


@dataclass
class SpeakerStat:
    seconds: float = 0.0
    words: int = 0
    turns: int = 0


@dataclass
class Analytics:
    by_speaker: dict[str, SpeakerStat] = field(default_factory=dict)
    total_seconds: float = 0.0
    longest_monologue_s: float = 0.0
    longest_monologue_speaker: str = ""

    def talk_ratio(self) -> dict[str, float]:
        """Fraction of speaking time per speaker (0 to 1), empty if silent."""
        if self.total_seconds <= 0:
            return {}
        return {s: st.seconds / self.total_seconds for s, st in self.by_speaker.items()}


def compute(segments: list[dict[str, Any]]) -> Analytics:
    """Aggregate per-speaker talk time and words from raw transcript segments."""
    turns = transcribe.merge_turns(segments)
    result = Analytics()
    for turn in turns:
        speaker = turn["speaker"]
        duration = max(0.0, float(turn["end"]) - float(turn["start"]))
        stat = result.by_speaker.setdefault(speaker, SpeakerStat())
        stat.seconds += duration
        stat.words += len(turn["text"].split())
        stat.turns += 1
        result.total_seconds += duration
        if duration > result.longest_monologue_s:
            result.longest_monologue_s = duration
            result.longest_monologue_speaker = speaker
    return result


def _mmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}m {total % 60:02d}s"


def format_markdown(a: Analytics) -> str:
    """Render an "## Meeting stats" section, or "" if there was no speech."""
    if not a.by_speaker or a.total_seconds <= 0:
        return ""
    ratios = a.talk_ratio()
    lines = [
        "## Meeting stats",
        "",
        "| Speaker | Talk time | Share | Words | Turns |",
        "|---|---|---|---|---|",
    ]
    for speaker, stat in sorted(a.by_speaker.items(), key=lambda kv: -kv[1].seconds):
        lines.append(
            f"| {speaker} | {_mmss(stat.seconds)} | {round(ratios[speaker] * 100)}% "
            f"| {stat.words} | {stat.turns} |"
        )
    lines.append("")
    lines.append(
        f"Total spoken: {_mmss(a.total_seconds)} · longest monologue: "
        f"{_mmss(a.longest_monologue_s)} ({a.longest_monologue_speaker})"
    )
    return "\n".join(lines)


def section(segments: list[dict[str, Any]]) -> str:
    """Convenience: analytics Markdown section for a session's segments."""
    return format_markdown(compute(segments))
