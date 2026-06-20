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
Every task someone committed to or was asked to do, INCLUDING soft commitments
("I'll look into it", "can you follow up"). Always capture the task; set the owner
to whoever took it on (a name, or Me/Them), or leave blank if unclear — never
invent an owner or date. Add a due/timeframe only if stated.
- [ ] task — owner — due
If none, write "None."

## Blockers to resolve
Cross-team blockers or decisions needed. If none, write "None."

Rules:
- Use only facts from the transcript and rough notes; never invent details.
- Fix obvious transcription errors silently using context.
- Output only the Markdown note. No preamble, no top-level title heading.
