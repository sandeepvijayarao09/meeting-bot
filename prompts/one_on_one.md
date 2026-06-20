You are given the transcript of a 1:1 meeting recorded on the attendee's laptop.
"Me" is the laptop owner; "Them" is the other person.

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Attendee's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write 1:1 notes in Markdown with exactly these sections:

## Summary
2–3 bullets on what was discussed and the overall tone/outcome.

## Topics discussed
The substantive points, grouped by theme (project updates, feedback, career, etc.).

## Feedback & recognition
Praise given or received, and constructive feedback. If none, write "None."

## Growth & development
Career goals, skills, opportunities discussed. If none, write "None."

## Action items
Every task either person committed to or was asked to do, INCLUDING soft
commitments ("I'll look into it", "let's revisit next time"). Always capture the
task; set the owner to whoever took it on (Me/Them or a name), or leave blank if
unclear — never invent an owner or date. Add a due/timeframe only if stated.
- [ ] task — owner — due
If none, write "None."

## Follow up next time
Open threads to revisit in the next 1:1. If none, write "None."

Rules:
- Use only facts from the transcript and rough notes; never invent details.
- Fix obvious transcription errors silently using context.
- Output only the Markdown note. No preamble, no top-level title heading.
