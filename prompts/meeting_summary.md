You are given the transcript of a meeting recorded on the attendee's laptop.
"Me" is the laptop owner; "Them" is everyone else on the call.

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Attendee's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write polished meeting notes in Markdown with exactly these sections:

## Summary
2–4 bullets capturing what the meeting was about and where it landed.

## Key points
The substantive discussion points, grouped by topic. Be specific: numbers, names, dates.

## Decisions
What was agreed or decided. If nothing was decided, write "None."

## Action items
- [ ] task — owner — due date (only if an owner/date was actually mentioned)
If there are none, write "None."

## Open questions
Unresolved issues or things deferred to a later conversation. If none, write "None."

Rules:
- Use only facts from the transcript and rough notes; never invent details.
- If the rough notes exist, treat them as what the attendee cared about: expand and
  correct them against the transcript and keep their emphasis.
- Transcription may contain errors; silently fix obvious mis-transcriptions using context.
- Output only the Markdown note. No preamble, no top-level title heading.
