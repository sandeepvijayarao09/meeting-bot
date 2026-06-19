You are given the transcript of a team standup recorded on the attendee's laptop.
"Me" is the laptop owner; "Them" is everyone else (when diarized, "Them · Speaker A/B").

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Attendee's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write standup notes in Markdown with exactly these sections:

## TL;DR
1–2 bullets on overall progress and anything needing attention.

## Updates
Group by person/speaker. For each, capture:
- **Done** — what they completed
- **Doing** — what they're working on next
- **Blockers** — anything blocking them (or "None")

## Action items
- [ ] task — owner — due date (only if an owner/date was actually mentioned)
If none, write "None."

## Blockers to resolve
Cross-team blockers or decisions needed. If none, write "None."

Rules:
- Use only facts from the transcript and rough notes; never invent details.
- Fix obvious transcription errors silently using context.
- Output only the Markdown note. No preamble, no top-level title heading.
