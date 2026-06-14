"""Ask-my-meetings: answer questions across your meeting notes (local RAG).

Retrieves the most relevant notes via SQLite FTS, feeds their text to NIM as
context, and returns an answer grounded in your meetings plus the sources used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import notes, summarize

ASK_SYSTEM = (
    "You answer questions using ONLY the provided meeting notes. Cite which meeting(s) "
    "support your answer by title. If the notes do not contain the answer, say so "
    "plainly rather than guessing."
)

# Keep the context well within the model window; notes are small but transcripts add up.
MAX_CONTEXT_CHARS = 60_000
PER_NOTE_CHARS = 12_000


@dataclass
class AskResult:
    answer: str
    sources: list[dict[str, str]] = field(default_factory=list)


def build_context(hits: list[dict[str, str]]) -> str:
    """Concatenate the matched note bodies into a bounded context block."""
    blocks: list[str] = []
    total = 0
    for hit in hits:
        path = Path(hit["path"])
        if not path.exists():
            continue
        body = path.read_text()[:PER_NOTE_CHARS]
        block = f"# Meeting: {hit['title']} ({hit['date'][:10]})\n{body}"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks)


def ask(question: str, limit: int = 5) -> AskResult:
    """Answer a question over the meeting corpus. Requires the NIM API key."""
    if not summarize.have_key():
        raise summarize.MissingAPIKeyError(
            "Answering questions needs the NVIDIA API key. Get a free one at "
            "https://build.nvidia.com and put it in ~/.config/meetingbot/.env"
        )
    hits = notes.search(question, limit=limit)
    if not hits:
        return AskResult(answer="No meetings matched that question yet.", sources=[])
    context = build_context(hits)
    prompt = f"Meeting notes:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"
    answer = summarize.complete(ASK_SYSTEM, prompt, max_tokens=800)
    sources = [{"title": h["title"], "date": h["date"][:10], "path": h["path"]} for h in hits]
    return AskResult(answer=answer, sources=sources)
