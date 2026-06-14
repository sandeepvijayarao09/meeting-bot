"""Convert a meeting note (our Markdown dialect) to HTML or Google Docs requests.

Our notes use a small, predictable subset of Markdown: `##` headings, `-` and
`- [ ]` bullets, `**bold**`, and paragraphs. For Apple Notes we render HTML via
the `markdown` library. For Google Docs we build the full document text plus a
list of batchUpdate styling requests, because the Docs API has no HTML import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import markdown as _markdown

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$")

# Google Docs body indexing starts at 1 (index 0 is reserved).
_DOCS_BODY_START = 1


def to_html(markdown_text: str) -> str:
    """Render note Markdown to an HTML fragment (Apple Notes body)."""
    return str(_markdown.markdown(markdown_text, extensions=["sane_lists", "nl2br"]))


def _strip_inline(text: str) -> str:
    """Drop inline Markdown markers for plain-text targets (Docs)."""
    return _BOLD.sub(r"\1", text)


@dataclass
class DocsBuild:
    """The full document text plus the batchUpdate requests that style it.

    Usage: insertText(index=1, text=`text`) first, then batchUpdate(`requests`).
    All request indices are absolute Docs positions for that resulting document.
    """

    text: str
    requests: list[dict[str, Any]] = field(default_factory=list)


def _classify(line: str) -> tuple[str, str]:
    """Return (kind, rendered_text) for one Markdown line."""
    if not line.strip():
        return "body", ""
    m_check = _CHECKBOX.match(line)
    if m_check:
        checked, body = m_check.groups()
        box = "☑" if checked.lower() == "x" else "☐"
        return "checkbox", f"{box} {_strip_inline(body)}"
    m_bullet = _BULLET.match(line)
    if m_bullet:
        return "bullet", _strip_inline(m_bullet.group(1))
    m_head = _HEADING.match(line)
    if m_head:
        return f"h{min(len(m_head.group(1)), 3)}", _strip_inline(m_head.group(2))
    return "body", _strip_inline(line)


def to_docs_requests(markdown_text: str, *, title: str) -> DocsBuild:
    """Build the full Docs body text and its styling requests.

    The title becomes the first line (HEADING_1); the note body follows. Indices
    are computed against the emitted text, offset by the Docs body start (1).
    """
    blocks: list[tuple[str, str]] = [("h1", title.strip() or "Meeting notes")]
    blocks.append(("body", ""))  # spacer paragraph below the title
    for raw in markdown_text.splitlines():
        blocks.append(_classify(raw.rstrip()))

    lines = [text for _, text in blocks]
    full_text = "\n".join(lines) + "\n"  # trailing newline closes the last paragraph

    heading_named = {"h1": "HEADING_1", "h2": "HEADING_2", "h3": "HEADING_3"}
    requests: list[dict[str, Any]] = []
    cursor = _DOCS_BODY_START
    for kind, text in blocks:
        start = cursor
        end = start + len(text)  # paragraph content [start, end); newline at end
        cursor = end + 1  # advance past the newline
        if not text:
            continue
        if kind in heading_named:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end + 1},
                        "paragraphStyle": {"namedStyleType": heading_named[kind]},
                        "fields": "namedStyleType",
                    }
                }
            )
        elif kind in ("bullet", "checkbox"):
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": start, "endIndex": end + 1},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                }
            )
    return DocsBuild(text=full_text, requests=requests)
