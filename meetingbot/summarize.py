"""Meeting summarization via NVIDIA NIM (OpenAI-compatible API).

The only network/AI-credit-consuming module. Everything else runs locally.
Long transcripts are map-reduced; normal meetings cost a single request.
"""

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

from . import config

if TYPE_CHECKING:
    from openai import OpenAI

# llama-3.3-70b takes 128k tokens; stay far below to leave room for output.
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


class MissingAPIKeyError(RuntimeError):
    pass


def have_key() -> bool:
    return bool(config.NVIDIA_API_KEY)


def _client() -> "OpenAI":
    if not have_key():
        raise MissingAPIKeyError(
            "NVIDIA_API_KEY is not set. Get a free key at https://build.nvidia.com "
            "and put it in ~/.config/meetingbot/.env"
        )
    from openai import OpenAI

    return OpenAI(base_url=config.NIM_BASE_URL, api_key=config.NVIDIA_API_KEY)


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


def _chat(user_content: str, max_tokens: int = 3000) -> str:
    client = _client()
    resp = client.chat.completions.create(
        model=config.NIM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    if resp.usage:
        _log_usage(config.NIM_MODEL, resp.usage)
    return (resp.choices[0].message.content or "").strip()


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


def summarize_meeting(
    transcript: str,
    user_notes: str = "",
    title: str = "",
    date: str = "",
    duration: str = "",
) -> str:
    """One NIM round trip for normal meetings; map-reduce for marathon ones."""
    if len(transcript) > MAX_DIRECT_CHARS:
        condensed = [
            _chat(CONDENSE_PROMPT + piece, max_tokens=2000)
            for piece in _split_on_lines(transcript, PIECE_CHARS)
        ]
        transcript = "\n\n".join(condensed)

    template = config.PROMPT_TEMPLATE.read_text()
    prompt = _fill(
        template,
        TITLE=title or "(untitled)",
        DATE=date or "(unknown)",
        DURATION=duration or "(unknown)",
        NOTES=user_notes.strip() or "(none)",
        TRANSCRIPT=transcript,
    )
    return _chat(prompt)


def ping() -> str:
    """Cheap connectivity check used by `mbot doctor`."""
    client = _client()
    resp = client.chat.completions.create(
        model=config.NIM_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=5,
    )
    return (resp.choices[0].message.content or "").strip()
