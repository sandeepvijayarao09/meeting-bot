"""Meeting summarization.

Generation itself lives in :mod:`meetingbot.llm` (on-device Gemma 4 by default);
this module owns the prompting, the map-reduce for long transcripts, and title
generation. Normal meetings take a single completion.
"""

import datetime as dt
import json
from typing import Any

from . import config, llm

# Gemma 4 E4B carries a 128k context; stay far below it so the transcript, the
# prompt and the model's own output all fit comfortably.
MAX_DIRECT_CHARS = 240_000
PIECE_CHARS = 80_000

SYSTEM_PROMPT = (
    "You are an expert meeting notetaker. You write crisp, factual, well-structured "
    "Markdown notes and never invent details that are not in the source material."
)

CONDENSE_PROMPT = (
    "Condense this portion of a meeting transcript into detailed minutes. Preserve every "
    "fact, number, name, decision, action item, and owner. Keep speaker attribution "
    "(Me/Them). Output plain text minutes only.\n\nTranscript portion:\n\n"
)


# Kept as an alias so callers that still catch this keep working; the backend may
# now be unavailable for reasons other than a missing key (no local model).
MissingAPIKeyError = llm.LLMUnavailableError


def have_key() -> bool:
    """Whether a summary can be produced. Named for history; asks the backend."""
    return llm.is_available()


def _log_usage(model: str, usage: Any) -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with config.USAGE_LOG.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "at": dt.datetime.now().isoformat(timespec="seconds"),
                        "model": model,
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                    }
                )
                + "\n"
            )
    except OSError:
        pass


def complete(
    system_prompt: str, user_prompt: str, max_tokens: int = 4096, temperature: float = 0.2
) -> str:
    """One completion. Shared by summary, Ask, refine and transform."""
    text = llm.complete(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature)
    _log_usage(llm.describe(), None)
    return text


def _chat(user_content: str, max_tokens: int = 4096) -> str:
    return complete(SYSTEM_PROMPT, user_content, max_tokens=max_tokens)


TITLE_SYSTEM = (
    "You write short, specific meeting titles, like a smart calendar entry. "
    "Capture the main topic or outcome, never the date."
)


def generate_title(summary: str, transcript: str = "") -> str:
    """A concise, descriptive title (3-8 words) for a meeting, from its notes.

    Best-effort: returns "" if the model is unavailable or the meeting is empty,
    so the caller can fall back to a timestamp title without failing finalize.
    """
    source = (summary or "").strip() or (transcript or "").strip()
    if not source:
        return ""
    user = (
        "Give a short, specific title (3 to 8 words) for this meeting. Capture the "
        "main topic or decision. Use Title Case. No quotes, no date, no trailing "
        "punctuation, no 'Title:' prefix. Output the title only.\n\n" + source[:4000]
    )
    try:
        raw = complete(TITLE_SYSTEM, user, max_tokens=256, temperature=0.3)
    except Exception:  # best-effort: any API/network/key error -> fall back
        return ""
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned[:6].lower() == "title:":
            cleaned = cleaned[6:].strip()
        cleaned = cleaned.strip("\"'").rstrip(".")
        if cleaned:
            return cleaned[:80]
    return ""


def _split_on_lines(text: str, piece_chars: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > piece_chars and current:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        pieces.append("".join(current))
    return pieces


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def condense_if_long(text: str) -> str:
    """Map-reduce an over-long transcript into condensed minutes (one NIM pass per
    piece), or return it unchanged when it already fits the model window. Shared by
    summary generation and the text-transform tools."""
    if len(text) <= MAX_DIRECT_CHARS:
        return text
    return "\n\n".join(
        _chat(CONDENSE_PROMPT + piece, max_tokens=2000)
        for piece in _split_on_lines(text, PIECE_CHARS)
    )


def summarize_meeting(
    transcript: str,
    user_notes: str = "",
    title: str = "",
    date: str = "",
    duration: str = "",
    template: str | None = None,
) -> str:
    """One NIM round trip for normal meetings; map-reduce for marathon ones.

    `template` selects a meeting-type prompt ("standup", "one_on_one", …); None
    uses the default/general template.
    """
    transcript = condense_if_long(transcript)

    template_text = config.resolve_template(template or config.TEMPLATE).read_text()
    prompt = _fill(
        template_text,
        TITLE=title or "(untitled)",
        DATE=date or "(unknown)",
        DURATION=duration or "(unknown)",
        NOTES=user_notes.strip() or "(none)",
        TRANSCRIPT=transcript,
    )
    return _chat(prompt)


def ping() -> str:
    """Cheap check used by `mbot doctor` that the backend actually answers."""
    return llm.ping()
